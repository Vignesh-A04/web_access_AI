"""Background monitoring and automated reply service for WhatsApp Incoming Messages."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.api.schemas import (
    ChatbotConfigModel,
    ChatbotConfigUpdateRequest,
    ChatbotContactItem,
    ChatbotMessageRecord,
    ChatbotMessageStatusEnum,
    ChatbotStatusResponse,
)
from app.config import settings
from app.logging.setup import get_logger
from app.services.chatbot_reply_service import ChatbotReplyResult, chatbot_reply_service
from app.services.chatbot_store import chatbot_store
from app.services.whatsapp_service import (
    WhatsAppAutomationError,
    check_cdp_preflight,
    whatsapp_service,
)

logger = get_logger("chatbot_service")

# Regex pattern to sanitize any potential API keys in log text
API_KEY_REGEX = re.compile(r"AIza[0-9A-Za-z-_]{35}")


class WhatsAppChatbotService:
    """Manages the background loop monitoring WhatsApp Web for incoming messages and dispatching automated replies."""

    def __init__(self):
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._processing_lock = asyncio.Lock()
        self._processing_fingerprints: Set[str] = set()
        self._contact_locks: Dict[str, asyncio.Lock] = {}
        self._browser_send_lock = asyncio.Lock()
        self._active_tasks: Set[asyncio.Task] = set()
        self._last_check_timestamp: Optional[str] = None
        self._last_error: Optional[str] = None

        # Reusable browser references
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self._monitor_task is not None and not self._monitor_task.done()

    def _get_contact_lock(self, contact_name: str) -> asyncio.Lock:
        """Retrieve or create a serialized concurrency lock for a specific contact."""
        key = contact_name.strip().lower()
        if key not in self._contact_locks:
            self._contact_locks[key] = asyncio.Lock()
        return self._contact_locks[key]

    @staticmethod
    def _sanitize_error(error_str: Optional[str]) -> str:
        """Sanitize error strings to avoid logging API keys or huge traces."""
        if not error_str:
            return ""
        clean = API_KEY_REGEX.sub("[REDACTED_API_KEY]", str(error_str))
        return clean[:200]

    @staticmethod
    def _sanitize_text(text: Optional[str], max_len: int = 40) -> str:
        """Privacy-safe snippet of user message text for diagnostic logging."""
        if not text:
            return ""
        sanitized = API_KEY_REGEX.sub("[REDACTED_API_KEY]", text.strip())
        return f"{sanitized[:max_len]}..." if len(sanitized) > max_len else sanitized

    def _log_event(self, event: str, message: str, **kwargs: Any) -> None:
        """Emit structured, privacy-safe diagnostic log for auditing and monitoring."""
        now_iso = datetime.now(timezone.utc).isoformat()
        safe_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        logger.info(
            f"[ChatbotEvent:{event}] {message} | {json.dumps(safe_kwargs, default=str)}",
            extra={
                "chatbot_event": event,
                "event_timestamp": now_iso,
                "event_data": safe_kwargs,
            }
        )

    def _log_stage_timing(
        self,
        stage: str,
        status: str,
        elapsed_ms: Optional[float] = None,
        message_id: Optional[str] = None,
        contact_name: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log granular stage timing metrics safely."""
        data: Dict[str, Any] = {
            "stage": stage,
            "status": status,
            "message_id": message_id,
            "contact_name": contact_name,
        }
        if elapsed_ms is not None:
            data["elapsed_ms"] = round(elapsed_ms, 2)
        if error:
            data["error"] = self._sanitize_error(error)

        msg = f"Stage '{stage}' {status}"
        if elapsed_ms is not None:
            msg += f" in {elapsed_ms:.1f}ms"
        self._log_event("stage_timing", msg, **data)

    def _log_processing_summary(
        self,
        message_id: str,
        contact_name: str,
        final_status: str,
        total_duration_ms: float,
        stage_timings: Dict[str, float],
    ) -> None:
        """Log final end-to-end processing lifecycle summary with all stage timings."""
        self._log_event(
            "processing_lifecycle_summary",
            f"Message {message_id} completed with status '{final_status}' in {total_duration_ms:.1f}ms",
            message_id=message_id,
            contact_name=contact_name,
            final_status=final_status,
            total_duration_ms=round(total_duration_ms, 2),
            stage_timings=stage_timings,
        )

    # =========================================================================
    # Lifecycle Controls
    # =========================================================================

    async def start(self) -> Dict[str, Any]:
        """Start the background incoming-message monitor."""
        async with self._lifecycle_lock:
            if self.is_running:
                return {"status": "already_running", "message": "Chatbot monitor is already running."}

            # Safety guarantee: immediately clean up any lingering GENERATING records
            chatbot_store.recover_stale_in_progress_messages()

            self._stop_event.clear()
            self._is_running = True
            self._last_error = None

            # Ensure config.enabled is True
            config = chatbot_store.get_config()
            if not config.enabled:
                config.enabled = True
                chatbot_store.save_config(config)

            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self._log_event("monitor_started", "WhatsApp incoming chatbot background monitor started.")
            return {"status": "started", "message": "Chatbot monitor started successfully."}

    async def stop(self) -> Dict[str, Any]:
        """Stop the background incoming-message monitor safely."""
        async with self._lifecycle_lock:
            if not self.is_running and not self._is_running:
                return {"status": "not_running", "message": "Chatbot monitor is not currently running."}

            self._log_event("monitor_stopped", "Stopping WhatsApp incoming chatbot background monitor.")
            self._is_running = False
            self._stop_event.set()

            config = chatbot_store.get_config()
            config.enabled = False
            chatbot_store.save_config(config)

            if self._monitor_task:
                try:
                    self._monitor_task.cancel()
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
                self._monitor_task = None

            # Cancel and drain in-flight processing tasks
            if self._active_tasks:
                for task in list(self._active_tasks):
                    if not task.done():
                        task.cancel()
                try:
                    await asyncio.gather(*self._active_tasks, return_exceptions=True)
                except Exception:
                    pass
                self._active_tasks.clear()

            # Safe detachment from CDP
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
                self._page = None

            return {"status": "stopped", "message": "Chatbot monitor stopped successfully."}

    def get_status(self) -> ChatbotStatusResponse:
        """Retrieve current monitor status, configuration, contacts, and recent messages."""
        config = chatbot_store.get_config()
        contacts = chatbot_store.list_contacts()
        recent = chatbot_store.list_recent_messages(limit=50)

        return ChatbotStatusResponse(
            is_running=self.is_running,
            config=config,
            contacts=contacts,
            processed_messages_count=len(recent),
            recent_messages=recent,
            last_check_timestamp=self._last_check_timestamp,
            last_error=self._last_error,
        )

    def update_config(self, update: ChatbotConfigUpdateRequest) -> ChatbotConfigModel:
        """Update runtime configuration."""
        current = chatbot_store.get_config()
        data = current.model_dump()
        update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
        data.update(update_dict)
        new_config = ChatbotConfigModel(**data)
        chatbot_store.save_config(new_config)
        return new_config

    # =========================================================================
    # Background Monitoring Loop
    # =========================================================================

    async def _monitor_loop(self) -> None:
        """Main monitoring loop executing every poll_interval_seconds."""
        self._log_event("monitor_started", "Entering _monitor_loop")

        try:
            async with async_playwright() as p:
                while not self._stop_event.is_set():
                    config = chatbot_store.get_config()
                    if not config.enabled:
                        self._log_event("monitor_stopped", "Chatbot disabled in config. Halting monitor loop.")
                        break

                    poll_interval = max(config.poll_interval_seconds, 1.0)
                    self._last_check_timestamp = datetime.now(timezone.utc).isoformat()
                    self._log_event("monitor_scan_started", "Starting monitoring cycle scan.", poll_interval=poll_interval)

                    try:
                        # 1. Ensure CDP Browser & Authenticated Page Connection
                        page = await self._ensure_browser_page(p, config)
                        if page:
                            # 2. Check each active allowed contact
                            await self._scan_allowed_contacts(page, config)
                    except asyncio.CancelledError:
                        self._log_event("monitor_stopped", "Monitor loop cancelled.")
                        break
                    except Exception as e:
                        logger.error(f"Error in chatbot monitoring cycle: {e}", exc_info=True)
                        self._last_error = str(e)
                        self._log_event("monitor_scan_failed", f"Monitoring scan cycle failed: {e}", error=str(e))

                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
                    except asyncio.TimeoutError:
                        pass  # Continue to next poll cycle
        except asyncio.CancelledError:
            self._log_event("monitor_stopped", "Monitor loop received CancelledError.")
        except Exception as e:
            logger.error(f"Fatal error in chatbot monitor loop: {e}", exc_info=True)
            self._last_error = str(e)
            self._log_event("monitor_scan_failed", f"Fatal error in monitor loop: {e}", error=str(e))
        finally:
            self._is_running = False
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
                self._page = None
            self._log_event("monitor_stopped", "Exited _monitor_loop cleanly.")

    async def _ensure_browser_page(self, p: Any, config: ChatbotConfigModel) -> Optional[Page]:
        """Connect or reuse active WhatsApp Web tab via CDP without redundant HTTP preflights."""
        cdp_url = config.cdp_url or settings.chrome_cdp_url
        target_url = config.target_url or "https://web.whatsapp.com"

        # Fast path: Browser and Page already connected and active
        if self._browser is not None and self._browser.is_connected() and self._page is not None and not self._page.is_closed():
            try:
                curr_url = self._page.url.lower()
                if "whatsapp.com" in curr_url or target_url.lower() in curr_url:
                    self._last_error = None
                    return self._page
            except Exception:
                pass

        # Cold / Reconnect path: Check preflight only when connecting or recovering
        ok, msg, _ = await check_cdp_preflight(cdp_url, timeout_seconds=2.0)
        if not ok:
            self._last_error = f"CDP unavailable: {msg}"
            self._log_event("monitor_scan_failed", f"CDP unavailable: {msg}", error=msg)
            return None

        if self._browser is None or not self._browser.is_connected():
            try:
                self._browser = await p.chromium.connect_over_cdp(cdp_url)
            except Exception as e:
                self._last_error = f"Failed to connect over CDP: {e}"
                self._log_event("monitor_scan_failed", f"Failed to connect over CDP: {e}", error=str(e))
                return None

        contexts = self._browser.contexts
        if not contexts:
            self._last_error = "No browser context found in Chrome."
            self._log_event("monitor_scan_failed", "No browser context found in Chrome.")
            return None
        context = contexts[0]

        # Verify existing page reference or find/open WhatsApp page
        needs_page = False
        if self._page is None or self._page.is_closed():
            needs_page = True
        else:
            try:
                curr_url = self._page.url.lower()
                if "whatsapp.com" not in curr_url and target_url.lower() not in curr_url:
                    needs_page = True
            except Exception:
                needs_page = True

        if needs_page:
            try:
                self._page = await whatsapp_service._find_or_open_whatsapp_page(context, target_url, timeout_seconds=10)
            except Exception as e:
                self._last_error = f"Failed to find or open WhatsApp page: {e}"
                self._log_event("monitor_scan_failed", f"Failed to find or open WhatsApp page: {e}", error=str(e))
                return None

        # Check authentication status
        try:
            is_logged_in = await whatsapp_service._check_login_status(self._page, timeout=3)
            if not is_logged_in:
                self._last_error = "WhatsApp Web is not authenticated (QR code or login screen detected)."
                return None
        except Exception as e:
            self._last_error = f"Failed to check login status: {e}"
            return None

        self._last_error = None
        self._log_event("whatsapp_page_authenticated", "WhatsApp Web authenticated and ready.")
        return self._page

    # =========================================================================
    # Contact Inspection & Incoming Detection
    # =========================================================================

    async def _get_side_unread_contacts(self, page: Page) -> Set[str]:
        """Single DOM evaluation pass to find all contacts in #side with unread badges."""
        try:
            unread_names = await page.evaluate("""
                () => {
                    const unread = [];
                    const items = document.querySelectorAll(
                        '#side div[data-testid^="list-item-"], #side div[data-testid="cell-frame-container"], #side div[role="listitem"], #side div[role="row"], .contact-item'
                    );
                    for (const item of items) {
                        const badge = item.querySelector(
                            '[aria-label*="unread" i], [data-testid="unread-count"], [data-testid="icon-unread-count"], .unread-badge, .unread'
                        );
                        if (!badge) continue;
                        const aria = (badge.getAttribute('aria-label') || '').toLowerCase();
                        const txt = (badge.innerText || '').trim();
                        if (aria.includes('unread') || (txt && parseInt(txt, 10) > 0)) {
                            const titleEl = item.querySelector(
                                'span[data-testid="cell-frame-title"] span, span[dir="auto"], span[title], .chat-title, .contact-name'
                            );
                            const name = titleEl ? (titleEl.getAttribute('title') || titleEl.innerText || '').trim().toLowerCase() : '';
                            if (name) {
                                unread.push(name);
                            }
                        }
                    }
                    return unread;
                }
            """)
            return set(unread_names or [])
        except Exception as e:
            logger.debug(f"Error querying side unread badges: {e}")
            return set()

    async def _scan_allowed_contacts(self, page: Page, config: ChatbotConfigModel) -> None:
        """Inspect allowed contacts for newly arrived incoming messages with optimized DOM evaluations."""
        contacts = chatbot_store.list_contacts()
        active_contacts = [c for c in contacts if not c.is_paused]

        self._log_event(
            "allowlist_loaded",
            f"Loaded {len(active_contacts)} active contact(s) from allowlist.",
            active_count=len(active_contacts),
            contacts=[c.contact_name for c in active_contacts]
        )

        if not active_contacts:
            return

        # 1. First, check if the currently open conversation in #main matches an active allowlisted contact
        current_header = await whatsapp_service._get_active_chat_header_name(page, timeout=1)
        active_open_contact: Optional[ChatbotContactItem] = None
        if current_header:
            clean_header = current_header.strip().lower()
            for c in active_contacts:
                if c.contact_name.strip().lower() == clean_header:
                    active_open_contact = c
                    break

        if active_open_contact:
            # Currently active chat is an allowlisted contact -> scan incoming messages directly in #main
            await self._process_active_conversation_messages(page, active_open_contact.contact_name.strip(), config)

        # 2. Check remaining active allowlisted contacts in #side using a SINGLE DOM evaluate pass
        unread_contacts = await self._get_side_unread_contacts(page)

        for contact in active_contacts:
            if self._stop_event.is_set():
                break

            contact_name = contact.contact_name.strip()
            # If already processed as the open contact, skip
            if active_open_contact and active_open_contact.contact_name.strip().lower() == contact_name.lower():
                continue

            clean_name = contact_name.lower()
            has_unread = any(clean_name == u or clean_name in u or u in clean_name for u in unread_contacts)

            if has_unread:
                logger.info(f"Unread badge observed for allowlisted contact '{contact_name}'. Opening conversation.")
                try:
                    await whatsapp_service._click_contact_item(page, contact_name, timeout=5)
                    opened_header = await whatsapp_service._get_active_chat_header_name(page, timeout=5)
                    if opened_header and opened_header.strip().lower() == contact_name.lower():
                        await self._process_active_conversation_messages(page, contact_name, config)
                    else:
                        logger.warning(f"Opened header '{opened_header}' does not match expected '{contact_name}'. Skipping message processing.")
                except Exception as e:
                    logger.warning(f"Could not open chat for allowlisted contact '{contact_name}': {e}")

    async def _process_active_conversation_messages(self, page: Page, contact_name: str, config: ChatbotConfigModel) -> None:
        """Extract visible messages from active chat and dispatch async background processing pipelines."""
        t_detect_start = time.perf_counter()

        # 1. Discover incoming bubbles in DOM
        messages_data = await self._extract_visible_incoming_messages(page)
        if not messages_data:
            return

        # 2. Iterate through incoming messages
        for item in messages_data:
            if self._stop_event.is_set():
                break

            sender = item.get("sender") or contact_name
            if sender and sender.strip().lower() != contact_name.strip().lower():
                self._log_event(
                    "message_skipped",
                    f"Message skipped: sender '{sender}' does not match allowlisted contact '{contact_name}'",
                    sender=sender,
                    expected=contact_name,
                    reason="sender_mismatch"
                )
                continue

            incoming_text = (item.get("text") or "").strip()
            timestamp_str = (item.get("timestamp") or "").strip()
            dom_id = item.get("id") or ""
            whatsapp_msg_id = (item.get("whatsapp_msg_id") or "").strip()
            if not whatsapp_msg_id and dom_id and not dom_id.startswith("msg-"):
                whatsapp_msg_id = dom_id
            has_media = item.get("hasMedia", False)

            # Check if non-text or unsupported media
            if not incoming_text or has_media:
                fingerprint = chatbot_store.compute_fingerprint(
                    contact_name=contact_name,
                    text=incoming_text or "[media_attachment]",
                    timestamp_str=timestamp_str,
                    dom_context=dom_id if not whatsapp_msg_id else "",
                    whatsapp_msg_id=whatsapp_msg_id,
                )
                async with self._processing_lock:
                    if fingerprint in self._processing_fingerprints or chatbot_store.is_message_known(fingerprint):
                        continue
                    self._processing_fingerprints.add(fingerprint)

                try:
                    rec = chatbot_store.record_detected_message(
                        fingerprint=fingerprint,
                        contact_name=contact_name,
                        incoming_text=incoming_text or "[Unsupported non-text content or media attachment]",
                        timestamp_str=timestamp_str,
                    )
                    if rec:
                        det_latency = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
                        chatbot_store.update_message_status(
                            rec.id,
                            ChatbotMessageStatusEnum.SKIPPED,
                            skip_reason="Unsupported non-text message or media attachment; skipped for safety.",
                            total_duration_ms=det_latency,
                            stage_timings={"detection_latency_ms": det_latency}
                        )
                        self._log_event(
                            "message_skipped",
                            f"Message {rec.id} skipped: unsupported content",
                            message_id=rec.id,
                            reason="unsupported_content"
                        )
                finally:
                    async with self._processing_lock:
                        self._processing_fingerprints.discard(fingerprint)
                continue

            fingerprint = chatbot_store.compute_fingerprint(
                contact_name=contact_name,
                text=incoming_text,
                timestamp_str=timestamp_str,
                dom_context=dom_id if not whatsapp_msg_id else "",
                whatsapp_msg_id=whatsapp_msg_id,
            )

            # Concurrency & durable duplicate check
            async with self._processing_lock:
                if fingerprint in self._processing_fingerprints or chatbot_store.is_message_known(fingerprint):
                    continue
                self._processing_fingerprints.add(fingerprint)

            try:
                # Atomic record insertion
                record = chatbot_store.record_detected_message(
                    fingerprint=fingerprint,
                    contact_name=contact_name,
                    incoming_text=incoming_text,
                    timestamp_str=timestamp_str,
                )
                if not record:
                    async with self._processing_lock:
                        self._processing_fingerprints.discard(fingerprint)
                    continue

                t_detect_end = time.perf_counter()
                detection_latency_ms = round((t_detect_end - t_detect_start) * 1000.0, 2)

                self._log_event(
                    "incoming_message_detected",
                    f"New incoming message detected from '{contact_name}': '{self._sanitize_text(incoming_text)}'",
                    message_id=record.id,
                    contact_name=contact_name,
                    text_length=len(incoming_text)
                )

                self._log_stage_timing(
                    stage="detection",
                    status="completed",
                    elapsed_ms=detection_latency_ms,
                    message_id=record.id,
                    contact_name=contact_name
                )

                # Asynchronously dispatch workflow pipeline without blocking the monitor scan loop
                task = asyncio.create_task(
                    self._process_message_workflow(
                        record=record,
                        config=config,
                        t_detect_start=t_detect_start,
                        detection_latency_ms=detection_latency_ms,
                        fingerprint=fingerprint,
                    )
                )
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

            except Exception as e:
                async with self._processing_lock:
                    self._processing_fingerprints.discard(fingerprint)
                logger.error(f"Error initiating message workflow for '{contact_name}': {e}", exc_info=True)

    async def _process_message_workflow(
        self,
        record: ChatbotMessageRecord,
        config: ChatbotConfigModel,
        t_detect_start: float,
        detection_latency_ms: float,
        fingerprint: str,
    ) -> None:
        """Asynchronously process a detected message with per-contact serialization."""
        contact_name = record.contact_name
        message_id = record.id
        t_enqueued = time.perf_counter()

        stage_timings: Dict[str, float] = {
            "detection_latency_ms": detection_latency_ms,
            "queue_wait_ms": 0.0,
            "gemini_request_ms": 0.0,
            "safety_validation_ms": 0.0,
            "playwright_send_ms": 0.0,
            "verification_ms": 0.0,
        }

        contact_lock = self._get_contact_lock(contact_name)
        try:
            # Serialized execution per contact: ensures no race conditions or duplicate sends to the same contact
            async with contact_lock:
                t_work_start = time.perf_counter()
                stage_timings["queue_wait_ms"] = round((t_work_start - t_enqueued) * 1000.0, 2)
                self._log_stage_timing(
                    stage="queue_wait",
                    status="completed",
                    elapsed_ms=stage_timings["queue_wait_ms"],
                    message_id=message_id,
                    contact_name=contact_name
                )

                await self._handle_message_reply_pipeline(
                    record=record,
                    config=config,
                    t_detect_start=t_detect_start,
                    stage_timings=stage_timings
                )
        except asyncio.CancelledError:
            logger.info(f"Processing cancelled for message {message_id}")
            rec = chatbot_store.get_message_by_id(message_id)
            if rec and rec.status == ChatbotMessageStatusEnum.GENERATING:
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.FAILED,
                    skip_reason="Processing task cancelled while generating reply.",
                    stage_timings=stage_timings
                )
            raise
        except Exception as exc:
            sanitized_err = self._sanitize_error(str(exc))
            logger.error(f"Unexpected error processing message {message_id}: {sanitized_err}", exc_info=True)
            rec = chatbot_store.get_message_by_id(message_id)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            if rec and rec.status == ChatbotMessageStatusEnum.GENERATING:
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.FAILED,
                    skip_reason=f"Processing error during generation: {sanitized_err}",
                    total_duration_ms=total_ms,
                    stage_timings=stage_timings
                )
            elif rec and rec.status == ChatbotMessageStatusEnum.SENDING:
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                    skip_reason=f"Processing error during send: {sanitized_err}",
                    total_duration_ms=total_ms,
                    stage_timings=stage_timings
                )
        finally:
            async with self._processing_lock:
                self._processing_fingerprints.discard(fingerprint)

    async def _extract_visible_incoming_messages(self, page: Page) -> List[Dict[str, Any]]:
        """Extract incoming message texts and metadata from the active chat panel."""
        return await page.evaluate("""
            () => {
                const results = [];
                let elements = document.querySelectorAll(
                    '#main [role="row"], #main div.message-bubble, #main div.message-in, #main div.message-out'
                );
                if (!elements || elements.length === 0) {
                    elements = document.querySelectorAll('#main div[data-testid="msg-container"]');
                }

                let lastSender = '';

                elements.forEach((el, index) => {
                    const isSystem = el.querySelector('[data-testid="system-message"], [data-testid="chat-history-banner"]') !== null ||
                                     (el.innerText && el.innerText.includes('Messages and calls are end-to-end encrypted')) ||
                                     (el.innerText && el.innerText.includes('Welcome to WhatsApp Web simulation'));
                    if (isSystem) return;

                    const isOutgoing = (
                        el.classList.contains('message-out') ||
                        el.querySelector('.message-out') !== null ||
                        el.querySelector('[data-testid="tail-out"]') !== null ||
                        el.querySelector('[data-icon="tail-out"]') !== null ||
                        el.querySelector('[aria-label="You:"]') !== null ||
                        el.querySelector('[aria-label="You"]') !== null ||
                        el.querySelector('[data-testid="msg-check"]') !== null ||
                        el.querySelector('[data-testid="msg-dblcheck"]') !== null ||
                        el.querySelector('[data-testid="msg-dblcheck-ack"]') !== null ||
                        (el.querySelector('[data-pre-plain-text]') && (
                            el.querySelector('[data-pre-plain-text]').getAttribute('data-pre-plain-text').includes('You:')
                        ))
                    );

                    if (isOutgoing) {
                        return;
                    }

                    let sender = '';
                    let timestamp = '';
                    const prePlainEl = el.querySelector('[data-pre-plain-text]');
                    const prePlainText = prePlainEl ? prePlainEl.getAttribute('data-pre-plain-text') : '';

                    if (prePlainText) {
                        const match = prePlainText.match(/\\[([^,]+),\\s*([^\\]]+)\\]\\s*([^:]+):/);
                        if (match) {
                            timestamp = match[1].trim();
                            sender = match[3].trim();
                        }
                    }

                    if (!sender) {
                        const labelSpan = el.querySelector('span[aria-label$=":"]');
                        if (labelSpan) {
                            const rawLabel = labelSpan.getAttribute('aria-label') || '';
                            if (!rawLabel.toLowerCase().startsWith('you:')) {
                                sender = rawLabel.replace(/:$/, '').trim();
                            }
                        }
                    }

                    if (!sender) {
                        sender = lastSender;
                    }
                    if (sender) {
                        lastSender = sender;
                    }

                    const textEl = el.querySelector(
                        'span.selectable-text, .copyable-text span, [data-testid="selectable-text"], span[dir="ltr"], span[dir="auto"]'
                    );
                    let text = textEl ? (textEl.innerText || textEl.textContent || '').trim() : '';
                    if (!textEl && !text) {
                        text = '';
                    }

                    if (!timestamp) {
                        const timeEl = el.querySelector('[data-testid="msg-meta"], .copyable-text, .msg-time');
                        if (timeEl) timestamp = (timeEl.innerText || '').trim();
                    }

                    let whatsappMsgId = '';
                    if (el.hasAttribute && el.hasAttribute('data-id')) {
                        whatsappMsgId = el.getAttribute('data-id') || '';
                    } else if (el.querySelector && el.querySelector('[data-id]')) {
                        whatsappMsgId = el.querySelector('[data-id]').getAttribute('data-id') || '';
                    }
                    if (!whatsappMsgId) {
                        const testIdEl = el.querySelector ? el.querySelector('[data-testid^="conv-msg-"]') : null;
                        if (testIdEl) {
                            const tid = testIdEl.getAttribute('data-testid') || '';
                            whatsappMsgId = tid.replace(/^conv-msg-/, '');
                        } else if (el.getAttribute && el.getAttribute('data-testid')?.startsWith('conv-msg-')) {
                            whatsappMsgId = el.getAttribute('data-testid').replace(/^conv-msg-/, '');
                        }
                    }

                    const dataId = (
                        whatsappMsgId ||
                        (el.id ? el.id : '') ||
                        ('msg-' + index)
                    );

                    const hasMedia = el.querySelector(
                        '[data-testid="image-thumb"], [data-testid="audio-player"], [data-testid="sticker"], [data-testid="video-thumb"], [data-testid="document-thumb"]'
                    ) !== null;

                    const isIncoming = (
                        el.classList.contains('message-in') ||
                        el.querySelector('.message-in') !== null ||
                        el.querySelector('[data-testid="tail-in"]') !== null ||
                        el.querySelector('[data-icon="tail-in"]') !== null ||
                        (sender && sender.toLowerCase() !== 'you') ||
                        Boolean(prePlainText && !prePlainText.includes('You:'))
                    );

                    if (isIncoming) {
                        results.push({
                            id: dataId,
                            whatsapp_msg_id: whatsappMsgId,
                            sender: sender,
                            text: text,
                            timestamp: timestamp,
                            hasMedia: hasMedia
                        });
                    }
                });

                const unique = [];
                const seenIds = new Set();
                for (const r of results) {
                    if (!seenIds.has(r.id)) {
                        seenIds.add(r.id);
                        unique.push(r);
                    }
                }
                return unique;
            }
        """)

    # =========================================================================
    # Generation & Safety Sending Pipeline
    # =========================================================================

    async def _handle_message_reply_pipeline(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Run message through Gemini generation, safety checks, rate limiting, and dispatch with stage timings.
        Supports both legacy (page, record, config) and (record, config, t_detect_start, stage_timings) signatures.
        """
        page_arg: Optional[Page] = None
        record: Optional[ChatbotMessageRecord] = None
        config: Optional[ChatbotConfigModel] = None
        t_detect_start: Optional[float] = None
        stage_timings: Optional[Dict[str, float]] = None

        if len(args) == 3 and not isinstance(args[0], ChatbotMessageRecord):
            page_arg, record, config = args
        elif len(args) >= 2 and isinstance(args[0], ChatbotMessageRecord):
            record = args[0]
            config = args[1]
            if len(args) >= 3:
                t_detect_start = args[2]
            if len(args) >= 4:
                stage_timings = args[3]
        else:
            page_arg = kwargs.get("page")
            record = kwargs.get("record")
            config = kwargs.get("config")
            t_detect_start = kwargs.get("t_detect_start")
            stage_timings = kwargs.get("stage_timings")

        if record is None or config is None:
            raise ValueError("record and config are required arguments for _handle_message_reply_pipeline")

        if t_detect_start is None:
            t_detect_start = time.perf_counter()

        if stage_timings is None:
            stage_timings = {
                "detection_latency_ms": 0.0,
                "queue_wait_ms": 0.0,
                "gemini_request_ms": 0.0,
                "safety_validation_ms": 0.0,
                "playwright_send_ms": 0.0,
                "verification_ms": 0.0,
            }

        message_id = record.id
        contact_name = record.contact_name
        incoming_text = record.incoming_text

        # Stage: Safety Validation (Pre-generation)
        t_safety_start = time.perf_counter()

        # Safety Check 1: Chatbot global toggle
        if not config.enabled:
            stage_timings["safety_validation_ms"] = round((time.perf_counter() - t_safety_start) * 1000.0, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                skip_reason="Chatbot is currently disabled.",
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_skipped", f"Message {message_id} skipped: chatbot disabled", message_id=message_id, reason="chatbot_disabled")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        # Safety Check 2: Check contact is allowlisted and not paused
        contact_entry = chatbot_store.get_contact(contact_name)
        if not contact_entry or contact_entry.is_paused:
            stage_timings["safety_validation_ms"] = round((time.perf_counter() - t_safety_start) * 1000.0, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            reason = f"Contact '{contact_name}' is paused or not in allowlist."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                skip_reason=reason,
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_skipped", f"Message {message_id} skipped: {reason}", message_id=message_id, reason="contact_paused_or_missing")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        # Safety Check 3: Rate limit check per contact
        recent_count = chatbot_store.count_recent_replies(contact_name, config.rate_limit_window_minutes)
        if recent_count >= config.max_replies_per_contact_window:
            stage_timings["safety_validation_ms"] = round((time.perf_counter() - t_safety_start) * 1000.0, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            reason = f"Rate limit reached ({recent_count}/{config.max_replies_per_contact_window} in {config.rate_limit_window_minutes}m)."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                skip_reason=reason,
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_skipped", f"Message {message_id} skipped: {reason}", message_id=message_id, reason="rate_limit_exceeded")
            logger.warning(f"Rate limit triggered for {contact_name}: {reason}")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        safety_ms_acc = (time.perf_counter() - t_safety_start) * 1000.0

        # Stage: Gemini Generation
        # Transition immediately to GENERATING so audit log accurately reflects in-progress state
        chatbot_store.update_message_status(
            message_id,
            ChatbotMessageStatusEnum.GENERATING,
            stage_timings=stage_timings,
        )
        self._log_stage_timing(
            stage="gemini_request",
            status="started",
            message_id=message_id,
            contact_name=contact_name,
        )

        t_gemini_start = time.perf_counter()
        try:
            # 25.0s explicit timeout accommodating live Gemini latency (12-16s) without leaving message stuck
            reply_result: ChatbotReplyResult = await chatbot_reply_service.generate_reply(
                sender_name=contact_name,
                incoming_text=incoming_text,
                context_messages=[incoming_text],
                system_instructions=config.system_instructions,
                timeout_seconds=25.0,
            )
        except Exception as e:
            t_gemini_end = time.perf_counter()
            stage_timings["gemini_request_ms"] = round((t_gemini_end - t_gemini_start) * 1000.0, 2)
            stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

            sanitized_err = self._sanitize_error(str(e))
            self._log_stage_timing(
                stage="gemini_request",
                status="failed",
                elapsed_ms=stage_timings["gemini_request_ms"],
                message_id=message_id,
                contact_name=contact_name,
                error=sanitized_err,
            )
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.FAILED,
                skip_reason=f"LLM generation failed: {sanitized_err}",
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_failed", f"Gemini reply failed for {message_id}: {sanitized_err}", message_id=message_id, reason="llm_generation_failed")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.FAILED.value, total_ms, stage_timings)
            return

        t_gemini_end = time.perf_counter()
        stage_timings["gemini_request_ms"] = round((t_gemini_end - t_gemini_start) * 1000.0, 2)

        # Check if Gemini API returned an error (fail fast, never fallback or mock)
        if reply_result.is_error:
            stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            reason = self._sanitize_error(reply_result.reason or "Gemini API error during generation.")

            self._log_stage_timing(
                stage="gemini_request",
                status="failed",
                elapsed_ms=stage_timings["gemini_request_ms"],
                message_id=message_id,
                contact_name=contact_name,
                error=reason,
            )
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.FAILED,
                skip_reason=reason,
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event(
                "gemini_generation_failed",
                f"Gemini API failure for message {message_id}: {reason}",
                message_id=message_id,
                reason="gemini_api_error",
                error_code=reply_result.error_code
            )
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.FAILED.value, total_ms, stage_timings)
            return

        self._log_stage_timing(
            stage="gemini_request",
            status="completed",
            elapsed_ms=stage_timings["gemini_request_ms"],
            message_id=message_id,
            contact_name=contact_name,
        )

        self._log_event(
            "gemini_generation_completed",
            f"Gemini reply generated for {message_id}",
            message_id=message_id,
            intent=reply_result.intent,
            confidence=reply_result.confidence,
            safety_passed=reply_result.safety_passed
        )

        # Stage: Post-generation Safety Validation
        t_safety2_start = time.perf_counter()

        # Safety Check 5: Gemini Safety Policy
        if reply_result.requires_manual_review or not reply_result.safety_passed:
            safety_ms_acc += (time.perf_counter() - t_safety2_start) * 1000.0
            stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

            reason = reply_result.reason or f"Flagged by safety policy (intent: '{reply_result.intent}')."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason=reason,
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("reply_blocked_by_safety_policy", f"Safety policy blocked reply for {message_id}: {reason}", message_id=message_id, reason=reason)
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        reply_text = reply_result.reply.strip()
        if not reply_text:
            safety_ms_acc += (time.perf_counter() - t_safety2_start) * 1000.0
            stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason="Gemini produced an empty reply.",
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_skipped", f"Message {message_id} skipped: empty reply", message_id=message_id, reason="empty_reply")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        # Safety Check 6: Maximum length constraint
        if len(reply_text) > config.max_reply_length:
            safety_ms_acc += (time.perf_counter() - t_safety2_start) * 1000.0
            stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

            reason = f"Generated reply length ({len(reply_text)} chars) exceeds maximum limit ({config.max_reply_length} chars)."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                reply_text=reply_text,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason=reason,
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event("message_skipped", f"Message {message_id} skipped: length exceeded", message_id=message_id, reason="length_exceeded")
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
            return

        safety_ms_acc += (time.perf_counter() - t_safety2_start) * 1000.0
        stage_timings["safety_validation_ms"] = round(safety_ms_acc, 2)
        self._log_stage_timing(
            stage="safety_validation",
            status="completed",
            elapsed_ms=stage_timings["safety_validation_ms"],
            message_id=message_id,
            contact_name=contact_name,
        )

        # Transition to READY_TO_SEND
        chatbot_store.update_message_status(
            message_id,
            ChatbotMessageStatusEnum.READY_TO_SEND,
            reply_text=reply_text,
            intent=reply_result.intent,
            confidence=reply_result.confidence,
            stage_timings=stage_timings,
        )

        # Safety Check 7: Auto-reply explicit user toggle
        if not config.auto_reply_enabled:
            total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.READY_TO_SEND,
                skip_reason="Automatic sending mode is disabled. Reply candidate generated and ready for approval.",
                total_duration_ms=total_ms,
                stage_timings=stage_timings,
            )
            self._log_event(
                "message_skipped",
                f"Automatic sending is disabled. Candidate reply ready for {message_id}.",
                message_id=message_id,
                reason="auto_reply_disabled"
            )
            self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.READY_TO_SEND.value, total_ms, stage_timings)
            return

        # Stage: Browser Send & Outgoing Verification
        # Serialize browser interactions to prevent race conditions across concurrent contacts
        async with self._browser_send_lock:
            page = page_arg or self._page
            if not page or page.is_closed():
                # Re-verify page availability
                async with async_playwright() as p:
                    page = await self._ensure_browser_page(p, config)
            if not page:
                total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
                reason = "Browser page unavailable for sending."
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.READY_TO_SEND,
                    skip_reason=reason,
                    total_duration_ms=total_ms,
                    stage_timings=stage_timings,
                )
                self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.READY_TO_SEND.value, total_ms, stage_timings)
                return

            # Pre-Send Active Header Strict Re-Verification
            header_name = await whatsapp_service._get_active_chat_header_name(page, timeout=3)
            if not header_name or header_name.strip().lower() != contact_name.lower():
                try:
                    await whatsapp_service._click_contact_item(page, contact_name, timeout=5)
                    header_name = await whatsapp_service._get_active_chat_header_name(page, timeout=3)
                except Exception as e:
                    logger.warning(f"Could not switch conversation to '{contact_name}': {e}")

            if not header_name or header_name.strip().lower() != contact_name.lower():
                total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
                reason = f"Conversation changed before sending (active: '{header_name}', expected: '{contact_name}'). Send aborted."
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SKIPPED,
                    skip_reason=reason,
                    total_duration_ms=total_ms,
                    stage_timings=stage_timings,
                )
                self._log_event("message_skipped", f"Send aborted for {message_id}: conversation changed", message_id=message_id, reason="conversation_changed")
                self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
                return

            # Pre-send rate limit verification under browser send lock
            recent_count = chatbot_store.count_recent_replies(contact_name, config.rate_limit_window_minutes)
            if recent_count >= config.max_replies_per_contact_window:
                total_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)
                reason = f"Rate limit reached before sending ({recent_count}/{config.max_replies_per_contact_window} in {config.rate_limit_window_minutes}m)."
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SKIPPED,
                    skip_reason=reason,
                    total_duration_ms=total_ms,
                    stage_timings=stage_timings,
                )
                self._log_event("message_skipped", f"Send aborted for {message_id}: rate limit reached", message_id=message_id, reason="rate_limit_exceeded")
                self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SKIPPED.value, total_ms, stage_timings)
                return

            # Transition to SENDING
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SENDING)
            self._log_stage_timing(
                stage="playwright_send",
                status="started",
                message_id=message_id,
                contact_name=contact_name,
            )

            t_send_start = time.perf_counter()
            try:
                # Draft in composer
                await whatsapp_service._draft_message_in_composer(page, reply_text, timeout=5)

                # Click Send button ONCE
                await whatsapp_service._click_send_button_once(page, timeout=5)
                t_send_end = time.perf_counter()
                stage_timings["playwright_send_ms"] = round((t_send_end - t_send_start) * 1000.0, 2)

                self._log_stage_timing(
                    stage="playwright_send",
                    status="completed",
                    elapsed_ms=stage_timings["playwright_send_ms"],
                    message_id=message_id,
                    contact_name=contact_name,
                )

                # Verification Stage
                self._log_stage_timing(
                    stage="verification",
                    status="started",
                    message_id=message_id,
                    contact_name=contact_name,
                )
                t_verify_start = time.perf_counter()
                verified, verify_msg = await whatsapp_service._verify_message_sent_in_chat(page, reply_text, timeout=10)
                t_verify_end = time.perf_counter()
                stage_timings["verification_ms"] = round((t_verify_end - t_verify_start) * 1000.0, 2)

                self._log_stage_timing(
                    stage="verification",
                    status="completed" if verified else "uncertain",
                    elapsed_ms=stage_timings["verification_ms"],
                    message_id=message_id,
                    contact_name=contact_name,
                )

                total_duration_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

                if verified:
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.SENT,
                        skip_reason=f"Verified: {verify_msg}",
                        total_duration_ms=total_duration_ms,
                        stage_timings=stage_timings,
                    )
                    self._log_event("reply_verified", f"Automated reply successfully sent and verified for '{contact_name}'.", message_id=message_id, contact_name=contact_name)
                    self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SENT.value, total_duration_ms, stage_timings)
                else:
                    # Inconclusive / Timeout outcome -> SEND_UNCONFIRMED (never blindly retry)
                    unconfirmed_reason = f"Send verification inconclusive: {verify_msg}. Requires manual reconciliation."
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                        skip_reason=unconfirmed_reason,
                        total_duration_ms=total_duration_ms,
                        stage_timings=stage_timings,
                    )
                    self._log_event("reply_send_unconfirmed", f"Message {message_id} marked SEND_UNCONFIRMED: {unconfirmed_reason}", message_id=message_id, reason="verification_timeout")
                    self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SEND_UNCONFIRMED.value, total_duration_ms, stage_timings)

            except Exception as e:
                t_err = time.perf_counter()
                sanitized_err = self._sanitize_error(str(e))
                if stage_timings["playwright_send_ms"] == 0.0:
                    stage_timings["playwright_send_ms"] = round((t_err - t_send_start) * 1000.0, 2)
                total_duration_ms = round((time.perf_counter() - t_detect_start) * 1000.0, 2)

                logger.error(f"Error during browser send execution for {message_id}: {sanitized_err}", exc_info=True)
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                    skip_reason=f"Send action encountered browser error: {sanitized_err}. Marked unconfirmed to prevent duplicates.",
                    total_duration_ms=total_duration_ms,
                    stage_timings=stage_timings,
                )
                self._log_event("reply_send_unconfirmed", f"Browser send error for {message_id}: {sanitized_err}", message_id=message_id, reason="browser_send_error")
                self._log_processing_summary(message_id, contact_name, ChatbotMessageStatusEnum.SEND_UNCONFIRMED.value, total_duration_ms, stage_timings)

    async def send_approved_reply(self, message_id: str) -> Optional[ChatbotMessageRecord]:
        """Explicitly approve and send a single READY_TO_SEND candidate proposal."""
        record = chatbot_store.get_message_by_id(message_id)
        if not record:
            return None

        if record.status != ChatbotMessageStatusEnum.READY_TO_SEND:
            logger.warning(f"Cannot send message {message_id} in status '{record.status}'. Must be READY_TO_SEND.")
            return record

        reply_text = record.reply_text
        if not reply_text:
            logger.warning(f"Message {message_id} has no reply_text to send.")
            return record

        contact_name = record.contact_name
        config = chatbot_store.get_config()
        t_start = time.perf_counter()

        timings: Dict[str, float] = record.stage_timings.copy() if record.stage_timings else {}

        async with self._browser_send_lock:
            async with async_playwright() as p:
                page = await self._ensure_browser_page(p, config)
                if not page:
                    err_msg = f"Browser page not available to send reply: {self._last_error or 'CDP connection failed'}"
                    logger.error(err_msg)
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.READY_TO_SEND,
                        skip_reason=f"Send attempt aborted: {err_msg}"
                    )
                    return chatbot_store.get_message_by_id(message_id)

                # Revalidate active chat header
                header_name = await whatsapp_service._get_active_chat_header_name(page, timeout=3)
                if not header_name or header_name.strip().lower() != contact_name.lower():
                    logger.info(f"Active header '{header_name}' does not match target contact '{contact_name}'. Clicking contact item.")
                    try:
                        await whatsapp_service._click_contact_item(page, contact_name, timeout=5)
                        header_name = await whatsapp_service._get_active_chat_header_name(page, timeout=3)
                    except Exception as e:
                        logger.warning(f"Could not open contact '{contact_name}': {e}")

                if not header_name or header_name.strip().lower() != contact_name.lower():
                    abort_reason = f"Active conversation '{header_name}' does not match recipient '{contact_name}'. Send aborted for safety."
                    logger.warning(abort_reason)
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.READY_TO_SEND,
                        skip_reason=abort_reason
                    )
                    return chatbot_store.get_message_by_id(message_id)

                # Revalidate rate limit under browser send lock
                recent_count = chatbot_store.count_recent_replies(contact_name, config.rate_limit_window_minutes)
                if recent_count >= config.max_replies_per_contact_window:
                    abort_reason = f"Rate limit reached ({recent_count}/{config.max_replies_per_contact_window} in {config.rate_limit_window_minutes}m). Approved send aborted."
                    logger.warning(abort_reason)
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.READY_TO_SEND,
                        skip_reason=abort_reason
                    )
                    return chatbot_store.get_message_by_id(message_id)

                # Transition to SENDING
                chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SENDING)
                self._log_event("approved_send_started", f"Sending approved reply for message {message_id} to '{contact_name}'", message_id=message_id, contact_name=contact_name)

                t_send_start = time.perf_counter()
                try:
                    # Draft in composer
                    await whatsapp_service._draft_message_in_composer(page, reply_text, timeout=5)

                    # Click Send ONCE
                    await whatsapp_service._click_send_button_once(page, timeout=5)
                    t_send_end = time.perf_counter()
                    timings["playwright_send_ms"] = round((t_send_end - t_send_start) * 1000.0, 2)

                    # Verify outgoing message bubble
                    t_verify_start = time.perf_counter()
                    verified, verify_msg = await whatsapp_service._verify_message_sent_in_chat(page, reply_text, timeout=10)
                    t_verify_end = time.perf_counter()
                    timings["verification_ms"] = round((t_verify_end - t_verify_start) * 1000.0, 2)

                    total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

                    if verified:
                        chatbot_store.update_message_status(
                            message_id,
                            ChatbotMessageStatusEnum.SENT,
                            skip_reason=f"Verified: {verify_msg}",
                            total_duration_ms=total_ms,
                            stage_timings=timings,
                        )
                        self._log_event("reply_verified", f"Approved reply successfully sent and verified for '{contact_name}'.", message_id=message_id, contact_name=contact_name)
                    else:
                        unconfirmed_reason = f"Send verification inconclusive: {verify_msg}. Requires manual reconciliation."
                        chatbot_store.update_message_status(
                            message_id,
                            ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                            skip_reason=unconfirmed_reason,
                            total_duration_ms=total_ms,
                            stage_timings=timings,
                        )
                        self._log_event("reply_send_unconfirmed", f"Message {message_id} marked SEND_UNCONFIRMED: {unconfirmed_reason}", message_id=message_id, reason="verification_timeout")

                except Exception as e:
                    sanitized_err = self._sanitize_error(str(e))
                    logger.error(f"Error during approved send execution for {message_id}: {sanitized_err}", exc_info=True)
                    total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                    chatbot_store.update_message_status(
                        message_id,
                        ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                        skip_reason=f"Send action encountered browser error: {sanitized_err}. Marked unconfirmed to prevent duplicate sends.",
                        total_duration_ms=total_ms,
                        stage_timings=timings,
                    )
                    self._log_event("reply_send_unconfirmed", f"Browser send error for {message_id}: {sanitized_err}", message_id=message_id, reason="browser_send_error")

                return chatbot_store.get_message_by_id(message_id)


# Global singleton chatbot service
chatbot_service = WhatsAppChatbotService()

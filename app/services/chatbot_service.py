"""Background monitoring and automated reply service for WhatsApp Incoming Messages."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
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


class WhatsAppChatbotService:
    """Manages the background loop monitoring WhatsApp Web for incoming messages and dispatching automated replies."""

    def __init__(self):
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_check_timestamp: Optional[str] = None
        self._last_error: Optional[str] = None

        # Reusable browser references
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self._monitor_task is not None and not self._monitor_task.done()

    # =========================================================================
    # Lifecycle Controls
    # =========================================================================

    async def start(self) -> Dict[str, Any]:
        """Start the background incoming-message monitor."""
        if self.is_running:
            return {"status": "already_running", "message": "Chatbot monitor is already running."}

        self._stop_event.clear()
        self._is_running = True
        self._last_error = None

        # Ensure config.enabled is True
        config = chatbot_store.get_config()
        if not config.enabled:
            config.enabled = True
            chatbot_store.save_config(config)

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("WhatsApp incoming chatbot background monitor started.")
        return {"status": "started", "message": "Chatbot monitor started successfully."}

    async def stop(self) -> Dict[str, Any]:
        """Stop the background incoming-message monitor safely."""
        if not self.is_running:
            self._is_running = False
            return {"status": "not_running", "message": "Chatbot monitor is not currently running."}

        logger.info("Stopping WhatsApp incoming chatbot background monitor...")
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

        # Safe detachment from CDP
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None

        logger.info("WhatsApp incoming chatbot monitor stopped.")
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
        logger.info("Entering _monitor_loop")
        playwright_instance = None

        try:
            async with async_playwright() as p:
                playwright_instance = p

                while not self._stop_event.is_set():
                    config = chatbot_store.get_config()
                    if not config.enabled:
                        logger.info("Chatbot is disabled in config. Halting monitor loop.")
                        break

                    poll_interval = max(config.poll_interval_seconds, 1.0)
                    self._last_check_timestamp = datetime.now(timezone.utc).isoformat()

                    try:
                        # 1. Ensure CDP Browser & Authenticated Page Connection
                        page = await self._ensure_browser_page(p, config)
                        if page:
                            # 2. Check each active allowed contact
                            await self._scan_allowed_contacts(page, config)
                    except asyncio.CancelledError:
                        logger.info("Monitor loop cancelled.")
                        break
                    except Exception as e:
                        logger.error(f"Error in chatbot monitoring cycle: {e}", exc_info=True)
                        self._last_error = str(e)

                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
                    except asyncio.TimeoutError:
                        pass  # Continue to next poll cycle
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Fatal error in chatbot monitor loop: {e}", exc_info=True)
            self._last_error = str(e)
        finally:
            self._is_running = False
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
                self._page = None
            logger.info("Exited _monitor_loop cleanly.")

    async def _ensure_browser_page(self, p: Any, config: ChatbotConfigModel) -> Optional[Page]:
        """Connect or reuse active WhatsApp Web tab via CDP."""
        cdp_url = config.cdp_url or settings.chrome_cdp_url
        target_url = config.target_url or "https://web.whatsapp.com"

        # Check preflight first
        ok, msg, _ = await check_cdp_preflight(cdp_url, timeout_seconds=2.0)
        if not ok:
            self._last_error = f"CDP unavailable: {msg}"
            return None

        if self._browser is None or not self._browser.is_connected():
            try:
                self._browser = await p.chromium.connect_over_cdp(cdp_url)
            except Exception as e:
                self._last_error = f"Failed to connect over CDP: {e}"
                return None

        contexts = self._browser.contexts
        if not contexts:
            self._last_error = "No browser context found in Chrome."
            return None
        context = contexts[0]

        # Locate page
        if self._page is None or self._page.is_closed():
            self._page = await whatsapp_service._find_or_open_whatsapp_page(context, target_url, timeout_seconds=10)

        # Check authentication status
        is_logged_in = await whatsapp_service._check_login_status(self._page, timeout=3)
        if not is_logged_in:
            self._last_error = "WhatsApp Web is not authenticated (QR code or login screen detected)."
            return None

        self._last_error = None
        return self._page

    # =========================================================================
    # Contact Inspection & Incoming Detection
    # =========================================================================

    async def _scan_allowed_contacts(self, page: Page, config: ChatbotConfigModel) -> None:
        """Inspect allowed contacts for newly arrived incoming messages."""
        contacts = chatbot_store.list_contacts()
        active_contacts = [c for c in contacts if not c.is_paused]

        if not active_contacts:
            # Empty allowlist means NO automated inspection or replies
            return

        for contact in active_contacts:
            if self._stop_event.is_set():
                break

            contact_name = contact.contact_name.strip()

            # Check if active chat already matches this contact
            current_header = await whatsapp_service._get_active_chat_header_name(page, timeout=1)
            is_currently_open = (
                current_header is not None
                and current_header.strip().lower() == contact_name.lower()
            )

            # If not open, check if there is an unread badge or click to open
            if not is_currently_open:
                has_unread = await self._contact_has_unread_badge(page, contact_name)
                if has_unread:
                    try:
                        await whatsapp_service._click_contact_item(page, contact_name, timeout=5)
                        current_header = await whatsapp_service._get_active_chat_header_name(page, timeout=5)
                        is_currently_open = (
                            current_header is not None
                            and current_header.strip().lower() == contact_name.lower()
                        )
                    except Exception as e:
                        logger.warning(f"Could not open chat for '{contact_name}': {e}")
                        continue
                else:
                    # No unread badge, skip opening to avoid disruptive tab switching
                    continue

            if is_currently_open:
                await self._process_active_conversation_messages(page, contact_name, config)

    async def _contact_has_unread_badge(self, page: Page, contact_name: str) -> bool:
        """Check whether a contact in the side list has an unread message indicator."""
        try:
            return await page.evaluate("""
                (targetName) => {
                    const items = document.querySelectorAll(
                        '#side div[data-testid="cell-frame-container"], #side div[role="listitem"], .contact-item'
                    );
                    for (const item of items) {
                        const titleEl = item.querySelector(
                            'span[data-testid="cell-frame-title"] span, span[dir="auto"], span[title], .contact-name'
                        );
                        const name = titleEl ? (titleEl.getAttribute('title') || titleEl.innerText || '').trim() : '';
                        if (name.toLowerCase() === targetName.toLowerCase()) {
                            const badge = item.querySelector(
                                'span[data-testid="unread-count"], [aria-label*="unread"], .unread-badge, .unread'
                            );
                            if (badge && badge.innerText && parseInt(badge.innerText.trim(), 10) > 0) {
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """, contact_name)
        except Exception:
            return False

    async def _process_active_conversation_messages(self, page: Page, contact_name: str, config: ChatbotConfigModel) -> None:
        """Extract and process newly arrived incoming messages in the open chat."""
        # 1. Discover incoming bubbles in DOM
        messages_data = await self._extract_visible_incoming_messages(page)
        if not messages_data:
            return

        # 2. Check the most recent incoming message
        latest = messages_data[-1]
        incoming_text = latest["text"]
        timestamp_str = latest.get("timestamp") or datetime.now(timezone.utc).strftime("%H:%M")
        dom_id = latest.get("id") or ""

        fingerprint = chatbot_store.compute_fingerprint(
            contact_name=contact_name,
            text=incoming_text,
            timestamp_str=timestamp_str,
            dom_context=dom_id,
        )

        # 3. Durable duplicate check
        if chatbot_store.is_message_known(fingerprint):
            return  # Already processed or detected

        # 4. Atomic record insertion (Phase 4)
        record = chatbot_store.record_detected_message(
            fingerprint=fingerprint,
            contact_name=contact_name,
            incoming_text=incoming_text,
            timestamp_str=timestamp_str,
        )
        if not record:
            return  # Concurrently detected by another routine

        logger.info(f"New incoming message detected from '{contact_name}': '{incoming_text[:60]}...'")

        # 5. Execute Reply Generation & Safety Dispatch Pipeline
        await self._handle_message_reply_pipeline(page, record, config)

    async def _extract_visible_incoming_messages(self, page: Page) -> List[Dict[str, str]]:
        """Extract incoming message texts and metadata from the active chat panel."""
        return await page.evaluate("""
            () => {
                const results = [];
                // Target incoming message bubbles only (#main message-in)
                const bubbles = document.querySelectorAll(
                    '#main div.message-in, #main div[data-testid="msg-container"]:has(div.message-in), #main .msg-incoming, .message-bubble-in'
                );

                bubbles.forEach((b, index) => {
                    // Extract text content
                    const textEl = b.querySelector(
                        'span.selectable-text, .copyable-text span, span[dir="ltr"], span[dir="auto"], span'
                    );
                    const text = textEl ? (textEl.innerText || textEl.textContent || '').trim() : (b.innerText || '').trim();

                    // Extract timestamp or metadata if available
                    const timeEl = b.querySelector('span[data-testid="msg-meta"], .copyable-text, .msg-time');
                    const time = timeEl ? (timeEl.innerText || '').trim() : '';

                    const idAttr = b.getAttribute('data-id') || ('msg-in-' + index);

                    if (text && !text.includes('Welcome to WhatsApp Web simulation')) {
                        results.push({
                            id: idAttr,
                            text: text,
                            timestamp: time
                        });
                    }
                });
                return results;
            }
        """)

    # =========================================================================
    # Phase 5 & 6: Generation & Safety Sending Pipeline
    # =========================================================================

    async def _handle_message_reply_pipeline(self, page: Page, record: ChatbotMessageRecord, config: ChatbotConfigModel) -> None:
        """Run message through Gemini generation, safety checks, rate limiting, and dispatch."""
        message_id = record.id
        contact_name = record.contact_name
        incoming_text = record.incoming_text

        # Safety Check 1: Chatbot global toggle
        if not config.enabled:
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SKIPPED, skip_reason="Chatbot is currently disabled.")
            return

        # Safety Check 2: Auto-reply explicit user toggle
        if not config.auto_reply_enabled:
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                skip_reason="Automatic replies are disabled. Explicit user action is required to enable auto-replies."
            )
            return

        # Safety Check 3: Check contact is allowlisted and not paused
        contact_entry = chatbot_store.get_contact(contact_name)
        if not contact_entry or contact_entry.is_paused:
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SKIPPED, skip_reason=f"Contact '{contact_name}' is paused or not in allowlist.")
            return

        # Safety Check 4: Rate limit check per contact
        recent_count = chatbot_store.count_recent_replies(contact_name, config.rate_limit_window_minutes)
        if recent_count >= config.max_replies_per_contact_window:
            reason = f"Rate limit reached ({recent_count}/{config.max_replies_per_contact_window} in {config.rate_limit_window_minutes}m)."
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SKIPPED, skip_reason=reason)
            logger.warning(f"Rate limit triggered for {contact_name}: {reason}")
            return

        # Transition to GENERATING
        chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.GENERATING)

        # 6. Call Gemini Reply Service (Phase 5)
        try:
            reply_result: ChatbotReplyResult = await chatbot_reply_service.generate_reply(
                sender_name=contact_name,
                incoming_text=incoming_text,
                context_messages=[incoming_text],
                system_instructions=config.system_instructions,
                timeout_seconds=15.0,
            )
        except Exception as e:
            logger.error(f"Error generating Gemini reply for {message_id}: {e}")
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.FAILED, skip_reason=f"LLM generation failed: {e}")
            return

        # Safety Check 5: Gemini Safety Policy
        if reply_result.requires_manual_review or not reply_result.safety_passed:
            reason = reply_result.reason or f"Flagged by safety policy (intent: '{reply_result.intent}')."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason=reason
            )
            logger.info(f"Message {message_id} skipped: {reason}")
            return

        reply_text = reply_result.reply.strip()
        if not reply_text:
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason="Gemini produced an empty reply."
            )
            return

        # Safety Check 6: Maximum length constraint
        if len(reply_text) > config.max_reply_length:
            reason = f"Generated reply length ({len(reply_text)} chars) exceeds maximum limit ({config.max_reply_length} chars)."
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SKIPPED,
                reply_text=reply_text,
                intent=reply_result.intent,
                confidence=reply_result.confidence,
                skip_reason=reason
            )
            return

        # Transition to READY_TO_SEND
        chatbot_store.update_message_status(
            message_id,
            ChatbotMessageStatusEnum.READY_TO_SEND,
            reply_text=reply_text,
            intent=reply_result.intent,
            confidence=reply_result.confidence
        )

        # 7. Pre-Send Active Header Strict Re-Verification
        header_name = await whatsapp_service._get_active_chat_header_name(page, timeout=3)
        if not header_name or header_name.strip().lower() != contact_name.lower():
            reason = f"Conversation changed before sending (active: '{header_name}', expected: '{contact_name}'). Send aborted."
            chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SKIPPED, skip_reason=reason)
            logger.warning(reason)
            return

        # Transition to SENDING
        chatbot_store.update_message_status(message_id, ChatbotMessageStatusEnum.SENDING)
        logger.info(f"Sending automated reply to '{contact_name}': '{reply_text}'")

        try:
            # 8. Draft in composer
            await whatsapp_service._draft_message_in_composer(page, reply_text, timeout=5)

            # 9. Click Send button ONCE
            await whatsapp_service._click_send_button_once(page, timeout=5)

            # 10. Verify outgoing message bubble
            verified, verify_msg = await whatsapp_service._verify_message_sent_in_chat(page, reply_text, timeout=10)

            if verified:
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SENT,
                    skip_reason=f"Verified: {verify_msg}"
                )
                logger.info(f"Automated reply successfully sent and verified for '{contact_name}'.")
            else:
                # Inconclusive / Timeout outcome -> SEND_UNCONFIRMED
                # NEVER resend automatically!
                unconfirmed_reason = f"Send verification inconclusive: {verify_msg}. Requires manual reconciliation."
                chatbot_store.update_message_status(
                    message_id,
                    ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                    skip_reason=unconfirmed_reason
                )
                logger.warning(f"Message {message_id} marked SEND_UNCONFIRMED: {unconfirmed_reason}")

        except Exception as e:
            logger.error(f"Error during browser send execution for {message_id}: {e}", exc_info=True)
            # Timeout / failure during send -> mark SEND_UNCONFIRMED, never blindly retry!
            chatbot_store.update_message_status(
                message_id,
                ChatbotMessageStatusEnum.SEND_UNCONFIRMED,
                skip_reason=f"Send action encountered browser error: {e}. Marked unconfirmed to prevent duplicates."
            )


# Global singleton chatbot service
chatbot_service = WhatsAppChatbotService()

"""WhatsApp Web automation workflow service using Playwright CDP connection."""

import asyncio
import datetime
import os
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.async_api import Browser, BrowserContext, Page, async_playwright, Playwright

from app.api.schemas import (
    WhatsAppCandidateItem,
    WhatsAppStateEnum,
    WhatsAppTaskRequest,
    WhatsAppTaskResponse,
)
from app.config import settings
from app.logging.setup import get_logger, sanitize_data

logger = get_logger("whatsapp_service")


class WhatsAppAutomationError(Exception):
    """Raised when an automation step on WhatsApp Web fails."""
    pass


class WhatsAppVerificationError(WhatsAppAutomationError):
    """Raised when verification of contact header or sent message fails."""
    pass


class WhatsAppWorkflowTask:
    """Manages the full lifecycle of an autonomous WhatsApp message task."""

    def __init__(self, task_id: str, request: WhatsAppTaskRequest):
        self.task_id = task_id
        self.contact_name = request.contact_name.strip()
        self.message_text = request.message
        self.cdp_url = request.cdp_url or settings.chrome_cdp_url
        self.target_url = request.target_url or "https://web.whatsapp.com"
        self.status = WhatsAppStateEnum.QUEUED
        self.selected_contact: Optional[str] = None
        self.candidates: List[WhatsAppCandidateItem] = []
        self.verified_header_name: Optional[str] = None
        self.screenshot_path: Optional[str] = None
        self.preview_data: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.completed_at: Optional[str] = None
        self.logs: List[str] = []

        # Lifecycle synchronization events
        self._cancel_requested = False
        self._candidate_selected_event = asyncio.Event()
        self._send_approval_event = asyncio.Event()
        self._send_approved: Optional[bool] = None
        self._approval_reason: Optional[str] = None

        # Playwright resources
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    def add_log(self, message: str) -> None:
        """Add a timestamped log entry."""
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.logs.append(entry)
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logger.info(f"WhatsAppTask[{self.task_id}]: {message}")

    def set_status(self, new_status: WhatsAppStateEnum, error: Optional[str] = None) -> None:
        """Update task state."""
        self.status = new_status
        if error:
            self.error = error
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if new_status in {WhatsAppStateEnum.COMPLETED, WhatsAppStateEnum.FAILED, WhatsAppStateEnum.CANCELLED}:
            self.completed_at = self.updated_at

    def cancel(self, reason: str = "User cancelled task") -> None:
        """Request safe cancellation."""
        self._cancel_requested = True
        self.add_log(f"Cancellation requested: {reason}")
        self._candidate_selected_event.set()
        self._send_approval_event.set()

    def resolve_candidate_selection(self, selected_name: str) -> None:
        """User selected a contact from ambiguous candidates."""
        self.selected_contact = selected_name.strip()
        self.add_log(f"User selected contact: '{self.selected_contact}'")
        self._candidate_selected_event.set()

    def resolve_send_approval(self, approved: bool, reason: Optional[str] = None) -> None:
        """User approved or rejected the drafted message send."""
        self._send_approved = approved
        self._approval_reason = reason
        self.add_log(f"Send approval received: approved={approved}, reason='{reason or ''}'")
        self._send_approval_event.set()

    def to_response(self) -> WhatsAppTaskResponse:
        """Convert to Pydantic schema."""
        return WhatsAppTaskResponse(
            task_id=self.task_id,
            status=self.status,
            contact_name=self.contact_name,
            selected_contact=self.selected_contact,
            candidates=self.candidates,
            verified_header_name=self.verified_header_name,
            message_text=self.message_text,
            screenshot_path=self.screenshot_path,
            preview_data=self.preview_data,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
            completed_at=self.completed_at,
            logs=self.logs,
        )

    async def capture_screenshot(self, stage_name: str) -> Optional[str]:
        """Capture screenshot and store on task."""
        if not self._page:
            return None
        try:
            out_dir = Path(settings.screenshot_dir) / "whatsapp"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{self.task_id}_{stage_name}.png"
            await self._page.screenshot(path=str(path), full_page=False)
            self.screenshot_path = str(path)
            return str(path)
        except Exception as e:
            logger.warning(f"Failed to capture screenshot for {self.task_id}: {e}")
            return None


class WhatsAppAutomationService:
    """Service managing WhatsApp Web tasks and CDP browser interaction."""

    def __init__(self):
        self._tasks: Dict[str, WhatsAppWorkflowTask] = {}
        self._asyncio_tasks: Dict[str, asyncio.Task] = {}

    def get_task(self, task_id: str) -> Optional[WhatsAppWorkflowTask]:
        return self._tasks.get(task_id)

    async def start_task(self, request: WhatsAppTaskRequest) -> WhatsAppWorkflowTask:
        """Initialize and launch WhatsApp workflow task in background."""
        task_id = str(uuid.uuid4())
        task = WhatsAppWorkflowTask(task_id, request)
        self._tasks[task_id] = task

        bg_task = asyncio.create_task(self._run_workflow(task))
        self._asyncio_tasks[task_id] = bg_task
        return task

    async def select_contact(self, task_id: str, selected_contact: str) -> WhatsAppWorkflowTask:
        """Submit user selection for an ambiguous contact match."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")
        if task.status != WhatsAppStateEnum.AMBIGUOUS_CONTACT:
            raise ValueError(f"Task is in state '{task.status}', not awaiting contact selection")
        task.resolve_candidate_selection(selected_contact)
        return task

    async def approve_send(self, task_id: str, approved: bool, reason: Optional[str] = None) -> WhatsAppWorkflowTask:
        """Submit user approval/rejection for sending the drafted message."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")
        if task.status != WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL:
            raise ValueError(f"Task is in state '{task.status}', not awaiting send approval")
        task.resolve_send_approval(approved, reason)
        return task

    async def cancel_task(self, task_id: str) -> WhatsAppWorkflowTask:
        """Cancel an ongoing WhatsApp task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")
        task.cancel()
        return task

    async def _run_workflow(self, task: WhatsAppWorkflowTask) -> None:
        """Execute the WhatsApp contact message workflow end-to-end."""
        timeout = settings.whatsapp_timeout_seconds

        try:
            task.add_log(f"Starting WhatsApp workflow for contact: '{task.contact_name}'")
            task.set_status(WhatsAppStateEnum.CONNECTING_CDP)

            # 1. Connect to Chrome via CDP
            task.add_log(f"Connecting to Chrome via CDP endpoint: {task.cdp_url}")
            task._playwright = await async_playwright().start()

            try:
                task._browser = await task._playwright.chromium.connect_over_cdp(
                    task.cdp_url,
                    timeout=15000,
                )
            except Exception as e:
                err_msg = (
                    f"Could not connect to Chrome CDP endpoint ({task.cdp_url}). "
                    f"Make sure Chrome is running with '--remote-debugging-port=9222': {e}"
                )
                task.add_log(err_msg)
                task.set_status(WhatsAppStateEnum.FAILED, error=err_msg)
                return

            if not task._browser.contexts:
                err_msg = "No browser context found in CDP connection."
                task.set_status(WhatsAppStateEnum.FAILED, error=err_msg)
                return

            context = task._browser.contexts[0]

            # 2. Find or open WhatsApp Web tab
            task.set_status(WhatsAppStateEnum.CHECKING_LOGIN)
            page = await self._find_or_open_whatsapp_page(context, task.target_url, timeout)
            task._page = page
            await task.capture_screenshot("connected")

            # Check if logged in
            task.add_log("Verifying WhatsApp Web login session...")
            is_logged_in = await self._check_login_status(page, timeout=12)

            if not is_logged_in:
                task.add_log("WhatsApp Web is NOT logged in. QR code or login screen detected.")
                await task.capture_screenshot("login_required")
                task.set_status(
                    WhatsAppStateEnum.AWAITING_MANUAL_LOGIN,
                    error="WhatsApp Web is not logged in. Please scan the QR code and log in manually in your dedicated Chrome browser window, then retry."
                )
                return

            task.add_log("WhatsApp Web session confirmed logged in.")

            if task._cancel_requested:
                task.set_status(WhatsAppStateEnum.CANCELLED)
                return

            # 3. Search for contact
            task.set_status(WhatsAppStateEnum.SEARCHING_CONTACT)
            task.add_log(f"Searching for contact '{task.contact_name}' in search bar...")
            candidates = await self._search_contacts(page, task.contact_name, timeout=10)
            await task.capture_screenshot("search_results")

            if not candidates:
                err_msg = f"Contact '{task.contact_name}' was not found in WhatsApp chat list."
                task.add_log(err_msg)
                task.set_status(WhatsAppStateEnum.CONTACT_NOT_FOUND, error=err_msg)
                return

            task.candidates = candidates

            # Resolve contact ambiguity
            target_contact_to_open: str = ""

            # Check if there is an exact case-insensitive match
            exact_matches = [c for c in candidates if c.name.strip().lower() == task.contact_name.lower()]

            if len(candidates) == 1:
                target_contact_to_open = candidates[0].name
                task.selected_contact = target_contact_to_open
                task.add_log(f"Found unique matching contact: '{target_contact_to_open}'")
            elif len(exact_matches) == 1:
                target_contact_to_open = exact_matches[0].name
                task.selected_contact = target_contact_to_open
                task.add_log(f"Found single exact matching contact: '{target_contact_to_open}'")
            else:
                # Multiple candidates match! Do not guess
                task.add_log(f"Multiple contacts ({len(candidates)}) match '{task.contact_name}'. Pausing for user selection.")
                task.set_status(WhatsAppStateEnum.AMBIGUOUS_CONTACT)

                # Wait for user candidate selection
                task._candidate_selected_event.clear()
                await task._candidate_selected_event.wait()

                if task._cancel_requested:
                    task.set_status(WhatsAppStateEnum.CANCELLED)
                    return

                if not task.selected_contact:
                    err_msg = "No contact candidate was selected by user."
                    task.set_status(WhatsAppStateEnum.FAILED, error=err_msg)
                    return

                target_contact_to_open = task.selected_contact
                task.add_log(f"Proceeding with user-selected contact: '{target_contact_to_open}'")

            # 4. Open chat and verify header
            task.set_status(WhatsAppStateEnum.OPENING_CHAT)
            task.add_log(f"Opening chat conversation for '{target_contact_to_open}'...")
            await self._click_contact_item(page, target_contact_to_open, timeout=10)

            task.set_status(WhatsAppStateEnum.VERIFYING_CHAT_HEADER)
            task.add_log("Verifying active conversation header...")
            displayed_header = await self._get_active_chat_header_name(page, timeout=10)

            # Strict recipient verification: header must match selected contact name
            if not displayed_header or displayed_header.strip().lower() != target_contact_to_open.strip().lower():
                err_msg = (
                    f"Recipient verification failed: Active chat header '{displayed_header}' "
                    f"does not match selected contact '{target_contact_to_open}'."
                )
                task.add_log(err_msg)
                await task.capture_screenshot("header_mismatch")
                task.set_status(WhatsAppStateEnum.FAILED, error=err_msg)
                return

            task.verified_header_name = displayed_header
            task.add_log(f"Chat header successfully verified: '{displayed_header}'")

            if task._cancel_requested:
                task.set_status(WhatsAppStateEnum.CANCELLED)
                return

            # 5. Draft message in composer (DO NOT SEND)
            task.set_status(WhatsAppStateEnum.DRAFTING_MESSAGE)
            task.add_log(f"Drafting message ({len(task.message_text)} chars) into composer without sending...")
            await self._draft_message_in_composer(page, task.message_text, timeout=10)

            screenshot = await task.capture_screenshot("drafted_message")
            task.preview_data = {
                "recipient": displayed_header,
                "message": task.message_text,
                "chat_header": displayed_header,
                "char_count": len(task.message_text),
            }

            # 6. Require explicit user Send confirmation
            task.set_status(WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL)
            task.add_log(f"Message drafted. Waiting for explicit user confirmation to send to '{displayed_header}'.")

            task._send_approval_event.clear()
            await task._send_approval_event.wait()

            if task._cancel_requested or task._send_approved is False:
                task.add_log(f"Send cancelled by user: {task._approval_reason or 'No reason provided'}")
                # Clear composer to leave chat clean
                await self._clear_composer(page)
                task.set_status(WhatsAppStateEnum.CANCELLED)
                return

            if task._send_approved is not True:
                task.set_status(WhatsAppStateEnum.CANCELLED)
                return

            # 7. Explicit Send button click (ONCE)
            task.set_status(WhatsAppStateEnum.SENDING)
            task.add_log("User confirmed. Clicking Send button once...")
            await self._click_send_button_once(page, timeout=10)

            # 8. Sent message verification in conversation
            task.set_status(WhatsAppStateEnum.VERIFYING_SENT)
            task.add_log("Verifying outgoing message bubble in conversation...")
            verified, verify_msg = await self._verify_message_sent_in_chat(page, task.message_text, timeout=15)

            await task.capture_screenshot("final_result")

            if not verified:
                err_msg = f"Message send could not be verified in conversation: {verify_msg}"
                task.add_log(err_msg)
                task.set_status(WhatsAppStateEnum.FAILED, error=err_msg)
                return

            task.add_log(f"Verification successful: {verify_msg}")
            task.set_status(WhatsAppStateEnum.COMPLETED)
            task.add_log(f"WhatsApp workflow finished successfully for '{displayed_header}'.")

        except Exception as e:
            logger.error(f"Error in WhatsApp workflow task {task.task_id}: {e}", exc_info=True)
            task.set_status(WhatsAppStateEnum.FAILED, error=str(e))
            task.add_log(f"Workflow error: {e}")
        finally:
            # Clean up CDP browser connection safely
            if task._browser:
                try:
                    await task._browser.close()
                except Exception:
                    pass
            if task._playwright:
                try:
                    await task._playwright.stop()
                except Exception:
                    pass
            task.add_log("Cleaned up CDP connection resources.")

    # =========================================================================
    # Browser DOM Interaction & Inspection Helpers
    # =========================================================================

    async def _find_or_open_whatsapp_page(self, context: BrowserContext, target_url: str, timeout_seconds: int) -> Page:
        """Find an existing WhatsApp Web tab or create and navigate a new page."""
        parsed_target = urllib.parse.urlparse(target_url)
        target_domain = parsed_target.netloc or "web.whatsapp.com"

        # Check existing tabs
        for p in context.pages:
            try:
                curr_url = p.url
                if target_domain in curr_url or target_url in curr_url:
                    await p.bring_to_front()
                    return p
            except Exception:
                continue

        # None found, open new tab
        page = await context.new_page()
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
        return page

    async def _check_login_status(self, page: Page, timeout: int = 12) -> bool:
        """Check whether WhatsApp Web is logged in or displaying a QR code / login screen."""
        login_indicators = [
            "#side",
            "div[data-testid='chat-list']",
            "div[aria-label='Chat list']",
            "div[contenteditable='true'][data-tab='3']",
            "#side [role='textbox']",
            "div[data-testid='chat-list-search']",
            "[data-testid='conversation-panel-wrapper']",
        ]

        qr_indicators = [
            "canvas[aria-label*='Scan']",
            "[data-testid='qrcode']",
            "div[data-ref]",
            "div:has-text('Scan this QR code')",
            "div:has-text('To use WhatsApp on your computer')",
            "div:has-text('Link with phone number')",
        ]

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check for QR code first
            for qr_sel in qr_indicators:
                try:
                    loc = page.locator(qr_sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return False
                except Exception:
                    pass

            # Check for logged-in chat list
            for login_sel in login_indicators:
                try:
                    loc = page.locator(login_sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        return True
                except Exception:
                    pass

            await asyncio.sleep(0.5)

        # Final check
        for login_sel in login_indicators:
            try:
                loc = page.locator(login_sel)
                if await loc.count() > 0:
                    return True
            except Exception:
                pass

        return False

    async def _search_contacts(self, page: Page, contact_name: str, timeout: int = 10) -> List[WhatsAppCandidateItem]:
        """Type contact name in WhatsApp Web search bar and collect candidate results."""
        search_selectors = [
            "#side div[contenteditable='true'][data-tab='3']",
            "#side div[role='textbox']",
            "div[contenteditable='true'][data-tab='3']",
            "[data-testid='chat-list-search']",
            "input[placeholder*='Search']",
            "#side input[type='text']",
        ]

        search_input = None
        for sel in search_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                search_input = loc.first
                break

        if not search_input:
            raise WhatsAppAutomationError("Could not locate WhatsApp chat search input field.")

        await search_input.click()
        # Clear existing text
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)

        # Type contact query
        await page.keyboard.insert_text(contact_name)
        await asyncio.sleep(1.5)  # Allow search indexing and rendering

        # Extract contact results from DOM
        candidates_data = await page.evaluate("""
            (searchQuery) => {
                const results = [];
                // Look for chat item elements inside #side or chat-list
                const listItems = document.querySelectorAll(
                    '#side div[data-testid="cell-frame-container"], #side div[role="listitem"], [data-testid="chat-list"] > div, .chat-item, .contact-item'
                );

                listItems.forEach((el, index) => {
                    // Extract title/name
                    const titleEl = el.querySelector(
                        'span[data-testid="cell-frame-title"] span, span[dir="auto"], span[title], .chat-title, .contact-name'
                    );
                    const name = titleEl ? (titleEl.getAttribute('title') || titleEl.innerText || '').trim() : '';

                    // Extract preview/subtitle
                    const subEl = el.querySelector('span[data-testid="last-msg-status"], .last-msg, .chat-subtitle');
                    const subtitle = subEl ? (subEl.innerText || '').trim() : '';

                    if (name && name.toLowerCase().includes(searchQuery.toLowerCase())) {
                        results.push({
                            id: 'candidate-' + (index + 1),
                            name: name,
                            subtitle: subtitle
                        });
                    }
                });

                return results;
            }
        """, contact_name)

        candidates = [
            WhatsAppCandidateItem(id=item["id"], name=item["name"], subtitle=item.get("subtitle", ""))
            for item in candidates_data
        ]

        # Deduplicate candidates by name preserving order
        unique_candidates = []
        seen = set()
        for c in candidates:
            if c.name not in seen:
                seen.add(c.name)
                unique_candidates.append(c)

        return unique_candidates

    async def _click_contact_item(self, page: Page, contact_name: str, timeout: int = 10) -> None:
        """Click on the contact in the search results list."""
        contact_loc = page.locator(f"#side span[title='{contact_name}'], #side span:has-text('{contact_name}'), .contact-item:has-text('{contact_name}')").first
        if await contact_loc.count() == 0:
            # Fallback to broader selector
            contact_loc = page.locator(f"span[title='{contact_name}']").first

        if await contact_loc.count() == 0:
            raise WhatsAppAutomationError(f"Could not click contact element for '{contact_name}'.")

        await contact_loc.click()
        await asyncio.sleep(1.0)

    async def _get_active_chat_header_name(self, page: Page, timeout: int = 10) -> Optional[str]:
        """Extract the contact title displayed in the active conversation header (#main header)."""
        header_selectors = [
            "#main header [data-testid='conversation-info-header-chat-title'] span",
            "#main header span[dir='auto']",
            "#main header [role='button'] span[title]",
            "#main header .chat-title",
            "#chat-header-name",
        ]

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            for sel in header_selectors:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        txt = (await loc.first.inner_text() or "").strip()
                        if txt:
                            return txt
                except Exception:
                    pass
            await asyncio.sleep(0.4)

        return None

    async def _draft_message_in_composer(self, page: Page, message_text: str, timeout: int = 10) -> None:
        """Type message into WhatsApp message composer without sending."""
        composer_selectors = [
            "#main footer div[contenteditable='true'][data-tab='10']",
            "#main footer div[role='textbox']",
            "div[data-testid='conversation-compose-box-input']",
            "#main footer div[contenteditable='true']",
            "#message-composer",
        ]

        composer = None
        for sel in composer_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                composer = loc.first
                break

        if not composer:
            raise WhatsAppAutomationError("Could not locate message composer input field in active chat.")

        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)

        # Insert message text cleanly
        await page.keyboard.insert_text(message_text)
        await asyncio.sleep(0.5)

    async def _clear_composer(self, page: Page) -> None:
        """Clear composer text if user cancels."""
        try:
            loc = page.locator("#main footer div[contenteditable='true'], #message-composer").first
            if await loc.count() > 0:
                await loc.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
        except Exception:
            pass

    async def _click_send_button_once(self, page: Page, timeout: int = 10) -> None:
        """Locate and click the WhatsApp Send button exactly once."""
        send_selectors = [
            "#main footer button[aria-label='Send']",
            "#main footer span[data-icon='send']",
            "button[data-testid='compose-btn-send']",
            "button[data-testid='send']",
            "#send-button",
        ]

        send_button = None
        for sel in send_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                send_button = loc.first
                break

        if send_button:
            await send_button.click()
        else:
            # Fallback: Enter key in composer
            composer = page.locator("#main footer div[contenteditable='true'], #message-composer").first
            if await composer.count() > 0:
                await composer.press("Enter")
            else:
                raise WhatsAppAutomationError("Could not locate Send button or message composer.")

        await asyncio.sleep(1.0)

    async def _verify_message_sent_in_chat(self, page: Page, message_text: str, timeout: int = 15) -> Tuple[bool, str]:
        """Verify that the outgoing message bubble appears in the conversation history."""
        outgoing_selectors = [
            "#main div.message-out",
            "#main div[data-testid='msg-container']:has(div.message-out)",
            "#main .msg-outgoing",
            ".message-bubble-out",
        ]

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            for sel in outgoing_selectors:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    if count > 0:
                        # Inspect the last outgoing bubble
                        last_bubble = loc.nth(count - 1)
                        bubble_text = (await last_bubble.inner_text() or "").strip()
                        if message_text in bubble_text or message_text.strip() == bubble_text:
                            return True, f"Outgoing message verified in active chat bubble ({len(message_text)} chars)."
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        return False, "Timed out waiting for outgoing message bubble to appear in conversation history."


whatsapp_service = WhatsAppAutomationService()

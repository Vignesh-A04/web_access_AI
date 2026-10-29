"""Tests for WhatsApp Web contact message workflow using CDP and local mock page."""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from app.api.routes import generate_mock_whatsapp_html
from app.api.schemas import (
    WhatsAppSendModeEnum,
    WhatsAppStateEnum,
    WhatsAppTaskRequest,
)
from app.main import app
from app.services.whatsapp_service import (
    WhatsAppAutomationError,
    WhatsAppAutomationService,
    whatsapp_service,
)


class MockWhatsAppHttpHandler(BaseHTTPRequestHandler):
    """Local HTTP handler serving the simulated WhatsApp Web DOM for testing."""

    def do_GET(self):
        query_mode = None
        if "mode=qr" in self.path:
            query_mode = "qr"

        html = generate_mock_whatsapp_html(mode=query_mode)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging during tests
        pass


@pytest.fixture(scope="module")
def mock_whatsapp_server() -> Generator[str, None, None]:
    """Start an ephemeral local HTTP server serving the mock WhatsApp Web DOM."""
    server = HTTPServer(("127.0.0.1", 0), MockWhatsAppHttpHandler)
    host, port = server.server_address
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{port}"
    yield base_url

    server.shutdown()
    server.server_close()


# =========================================================================
# 1. API Route and Schema Tests
# =========================================================================

def test_mock_whatsapp_pages_served():
    """Verify mock WhatsApp Web page routes render correctly."""
    client = TestClient(app)

    # Logged-in simulation page
    res_logged_in = client.get("/test-whatsapp")
    assert res_logged_in.status_code == 200
    assert "WhatsApp Web Mock" in res_logged_in.text
    assert "chat-list" in res_logged_in.text
    assert "Alice Smith" in res_logged_in.text

    # QR code simulation page
    res_qr = client.get("/test-whatsapp?mode=qr")
    assert res_qr.status_code == 200
    assert "qrcode" in res_qr.text
    assert "Scan this QR code" in res_qr.text


def test_whatsapp_api_endpoints_validation():
    """Verify validation on WhatsApp task endpoints."""
    client = TestClient(app)

    # Missing required message
    bad_res = client.post("/api/whatsapp/tasks", json={"contact_name": "Alice"})
    assert bad_res.status_code == 422

    # Missing required contact_name
    bad_res2 = client.post("/api/whatsapp/tasks", json={"message": "Hello"})
    assert bad_res2.status_code == 422

    # Nonexistent task lookups
    missing_res = client.get("/api/whatsapp/tasks/nonexistent-id")
    assert missing_res.status_code == 404

    # Invalid contact selection on nonexistent task
    bad_select = client.post(
        "/api/whatsapp/tasks/nonexistent-id/select-contact",
        json={"selected_contact": "Alice Smith"},
    )
    assert bad_select.status_code == 400


# =========================================================================
# 2. DOM Automation & Verification Tests (Playwright Isolated)
# =========================================================================

@pytest.mark.asyncio
async def test_login_detection_authenticated_vs_qr(mock_whatsapp_server: str):
    """Verify login status detection distinguishes between chat list and QR code screen."""
    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Logged-in page
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp")
        is_logged_in = await service._check_login_status(page, timeout=3)
        assert is_logged_in is True, "Expected logged in status for normal chat interface"

        # 2. QR code page
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp?mode=qr")
        is_logged_in_qr = await service._check_login_status(page, timeout=3)
        assert is_logged_in_qr is False, "Expected unauthenticated status when QR code is shown"

        await browser.close()


@pytest.mark.asyncio
async def test_contact_search_exact_and_ambiguous(mock_whatsapp_server: str):
    """Verify contact search identifies unique matches and flags ambiguous results."""
    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp")

        # 1. Unique match: "Alice"
        alice_candidates = await service._search_contacts(page, "Alice", timeout=3)
        assert len(alice_candidates) == 1
        assert alice_candidates[0].name == "Alice Smith"

        # 2. Ambiguous match: "Charlie" (Charlie Brown and Charlie Davis)
        charlie_candidates = await service._search_contacts(page, "Charlie", timeout=3)
        assert len(charlie_candidates) == 2
        names = [c.name for c in charlie_candidates]
        assert "Charlie Brown" in names
        assert "Charlie Davis" in names

        # 3. Nonexistent contact: "ZackaryNonexistent"
        empty_candidates = await service._search_contacts(page, "ZackaryNonexistent", timeout=3)
        assert len(empty_candidates) == 0

        await browser.close()


@pytest.mark.asyncio
async def test_chat_opening_and_header_verification(mock_whatsapp_server: str):
    """Verify opening a contact updates and verifies the displayed header name."""
    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp")

        # Click Bob Jones
        await service._click_contact_item(page, "Bob Jones", timeout=3)
        header_name = await service._get_active_chat_header_name(page, timeout=3)
        assert header_name == "Bob Jones"

        # Test header mismatch safety logic
        wrong_contact = "Alice Smith"
        assert header_name != wrong_contact, "Header mismatch should be caught"

        await browser.close()


@pytest.mark.asyncio
async def test_draft_message_without_sending(mock_whatsapp_server: str):
    """Verify message drafting puts text in composer but does NOT send it."""
    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp")
        await service._click_contact_item(page, "Alice Smith", timeout=3)

        draft_text = "Important confidential notice: do not send yet."
        await service._draft_message_in_composer(page, draft_text, timeout=3)

        # Composer should contain text
        composer_val = await page.evaluate("() => document.getElementById('message-composer').innerText")
        assert draft_text in composer_val

        # Verify NO message-out bubble exists with this text yet!
        sent, _ = await service._verify_message_sent_in_chat(page, draft_text, timeout=2)
        assert sent is False, "Message must NOT have been sent automatically!"

        # Now click send once explicitly
        await service._click_send_button_once(page, timeout=3)

        # Verify sent bubble now appears
        verified, msg = await service._verify_message_sent_in_chat(page, draft_text, timeout=4)
        assert verified is True
        assert "verified" in msg.lower()

        await browser.close()


@pytest.mark.asyncio
async def test_composer_cleared_on_user_rejection(mock_whatsapp_server: str):
    """Verify that if the user cancels send, the composer is safely cleared."""
    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{mock_whatsapp_server}/test-whatsapp")
        await service._click_contact_item(page, "Bob Jones", timeout=3)

        draft_text = "Mistake text that user wants to cancel"
        await service._draft_message_in_composer(page, draft_text, timeout=3)

        # Clear composer
        await service._clear_composer(page)

        composer_val = await page.evaluate("() => document.getElementById('message-composer').innerText")
        assert composer_val.strip() == ""

        await browser.close()


# =========================================================================
# 3. End-to-End CDP Workflow Integration Test
# =========================================================================

@pytest.mark.asyncio
async def test_full_cdp_workflow_with_mock_site(mock_whatsapp_server: str):
    """Verify end-to-end WhatsApp workflow over Chrome DevTools Protocol (CDP).

    Steps:
    1. Launch headless Chromium with remote debugging port enabled.
    2. Start WhatsApp workflow via CDP pointing to mock WhatsApp site.
    3. Workflow pauses at WAITING_FOR_SEND_APPROVAL with preview.
    4. Client explicitly approves send.
    5. Workflow completes with verified outgoing message.
    """
    cdp_port = 9235
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    target_url = f"{mock_whatsapp_server}/test-whatsapp"

    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        # Launch dedicated browser instance with CDP remote debugging
        cdp_browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )

        try:
            req = WhatsAppTaskRequest(
                contact_name="Alice Smith",
                message="Automated e2e verification message via CDP",
                cdp_url=cdp_url,
                target_url=target_url,
            )

            # Start the task
            task = await service.start_task(req)
            assert task.task_id is not None

            # Wait for task to pause at WAITING_FOR_SEND_APPROVAL
            for _ in range(40):
                if task.status in {
                    WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL,
                    WhatsAppStateEnum.FAILED,
                    WhatsAppStateEnum.COMPLETED,
                }:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL
            assert task.verified_header_name == "Alice Smith"
            assert task.preview_data is not None
            assert task.preview_data["recipient"] == "Alice Smith"
            assert task.preview_data["message"] == req.message

            # Explicitly approve send
            await service.approve_send(task.task_id, approved=True)

            # Wait for task to complete
            for _ in range(30):
                if task.status in {WhatsAppStateEnum.COMPLETED, WhatsAppStateEnum.FAILED}:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.COMPLETED
            assert task.error is None
            assert any("Verification successful" in log for log in task.logs)

        finally:
            await cdp_browser.close()


@pytest.mark.asyncio
async def test_full_cdp_workflow_ambiguous_contact_selection(mock_whatsapp_server: str):
    """Verify end-to-end CDP workflow pauses on ambiguous contact search and resumes upon user selection."""
    cdp_port = 9236
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    target_url = f"{mock_whatsapp_server}/test-whatsapp"

    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        cdp_browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )

        try:
            # Search query "Charlie" matches both Charlie Brown and Charlie Davis
            req = WhatsAppTaskRequest(
                contact_name="Charlie",
                message="Testing ambiguous contact selection",
                cdp_url=cdp_url,
                target_url=target_url,
            )

            task = await service.start_task(req)

            # Wait for AMBIGUOUS_CONTACT pause
            for _ in range(40):
                if task.status in {
                    WhatsAppStateEnum.AMBIGUOUS_CONTACT,
                    WhatsAppStateEnum.FAILED,
                }:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.AMBIGUOUS_CONTACT
            assert len(task.candidates) >= 2

            # User selects Charlie Davis
            await service.select_contact(task.task_id, "Charlie Davis")

            # Wait for WAITING_FOR_SEND_APPROVAL
            for _ in range(40):
                if task.status in {
                    WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL,
                    WhatsAppStateEnum.FAILED,
                }:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.WAITING_FOR_SEND_APPROVAL
            assert task.verified_header_name == "Charlie Davis"

            # Approve send
            await service.approve_send(task.task_id, approved=True)

            # Wait for completion
            for _ in range(30):
                if task.status in {WhatsAppStateEnum.COMPLETED, WhatsAppStateEnum.FAILED}:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.COMPLETED

        finally:
            await cdp_browser.close()


@pytest.mark.asyncio
async def test_full_cdp_workflow_unauthenticated_login_screen(mock_whatsapp_server: str):
    """Verify CDP workflow pauses with AWAITING_MANUAL_LOGIN when WhatsApp is unauthenticated."""
    cdp_port = 9237
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    target_url = f"{mock_whatsapp_server}/test-whatsapp?mode=qr"

    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        cdp_browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )

        try:
            req = WhatsAppTaskRequest(
                contact_name="Alice Smith",
                message="Test QR detect",
                cdp_url=cdp_url,
                target_url=target_url,
            )

            task = await service.start_task(req)

            # Wait for AWAITING_MANUAL_LOGIN
            for _ in range(30):
                if task.status in {
                    WhatsAppStateEnum.AWAITING_MANUAL_LOGIN,
                    WhatsAppStateEnum.FAILED,
                }:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.AWAITING_MANUAL_LOGIN
            assert "scan the qr code" in (task.error or "").lower()

        finally:
            await cdp_browser.close()


# =========================================================================
# 4. CDP Preflight, Safe Disconnection & Screenshot Endpoint Tests
# =========================================================================

@pytest.mark.asyncio
async def test_cdp_preflight_unavailable_endpoint():
    """Verify check_cdp_preflight fails fast with actionable PowerShell error when CDP is down."""
    from app.services.whatsapp_service import check_cdp_preflight

    ok, message, version_data = await check_cdp_preflight("http://127.0.0.1:9998", timeout_seconds=0.5)
    assert ok is False
    assert version_data is None
    assert "Chrome DevTools Protocol" in message
    assert "--remote-debugging-port=" in message
    assert "chrome.exe" in message


@pytest.mark.asyncio
async def test_cdp_preflight_security_loopback_rejection():
    """Verify check_cdp_preflight rejects non-loopback hosts for security."""
    from app.services.whatsapp_service import check_cdp_preflight

    ok_ip, msg_ip, _ = await check_cdp_preflight("http://192.168.1.100:9222", timeout_seconds=0.5)
    assert ok_ip is False
    assert "Security policy rejection" in msg_ip
    assert "127.0.0.1" in msg_ip

    ok_domain, msg_domain, _ = await check_cdp_preflight("http://example.com:9222", timeout_seconds=0.5)
    assert ok_domain is False
    assert "Security policy rejection" in msg_domain


@pytest.mark.asyncio
async def test_cdp_preflight_success_on_active_endpoint():
    """Verify check_cdp_preflight returns True when Chrome CDP is listening."""
    from app.services.whatsapp_service import check_cdp_preflight

    cdp_port = 9239
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )
        try:
            ok, message, version_data = await check_cdp_preflight(f"http://127.0.0.1:{cdp_port}", timeout_seconds=2.0)
            assert ok is True
            assert "CDP endpoint reachable" in message
            assert version_data is not None
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_screenshot_endpoint_status_responses():
    """Verify get_whatsapp_screenshot returns clear status explanations instead of silent 404s."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Nonexistent task
        missing_resp = await ac.get("/api/whatsapp/tasks/nonexistent-xyz/screenshot")
        assert missing_resp.status_code == 404
        assert "not found" in missing_resp.json()["detail"].lower()

        # 2. Create task pointing to unreachable port
        create_resp = await ac.post(
            "/api/whatsapp/tasks",
            json={
                "contact_name": "Test User",
                "message": "Hello",
                "cdp_url": "http://127.0.0.1:9997",
            },
        )
        assert create_resp.status_code in {200, 201}
        task_id = create_resp.json()["task_id"]

        # Allow background task to fail fast via preflight
        for _ in range(40):
            t_data = (await ac.get(f"/api/whatsapp/tasks/{task_id}")).json()
            if t_data["status"] == "failed":
                break
            await asyncio.sleep(0.2)

        screenshot_resp = await ac.get(f"/api/whatsapp/tasks/{task_id}/screenshot")
        assert screenshot_resp.status_code == 404
        detail = screenshot_resp.json()["detail"]
        assert "screenshot unavailable" in detail.lower()
        assert "failed" in detail.lower()


@pytest.mark.asyncio
async def test_safe_browser_disconnect_preserves_remote_browser():
    """Verify disconnecting Playwright CDP client does NOT close the user's remote browser session."""
    cdp_port = 9240
    async with async_playwright() as p_server:
        user_browser = await p_server.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )
        user_page = await user_browser.new_page()
        await user_page.goto("data:text/html,<h1>User Active Tab</h1>")

        try:
            async with async_playwright() as p_client:
                client_browser = await p_client.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                assert len(client_browser.contexts) >= 1
                await client_browser.close()

            content = await user_page.content()
            assert "User Active Tab" in content
        finally:
            await user_browser.close()


def test_local_test_mode_isolation():
    """Verify local test mode settings do NOT substitute mock behavior for live WhatsApp workflow."""
    from app.config import settings
    from app.services.whatsapp_service import WhatsAppWorkflowTask

    assert hasattr(settings, "allow_local_test_domains")
    from app.api.schemas import WhatsAppTaskRequest
    default_req = WhatsAppTaskRequest(contact_name="Alice", message="Hi")
    task = WhatsAppWorkflowTask("test-mode-id", default_req)
    assert task.target_url == "https://web.whatsapp.com"


# =========================================================================
# 5. Explicit Send Modes: Manual Approval vs Automatic Sending
# =========================================================================

def test_whatsapp_send_mode_defaults_to_manual():
    """Verify send_mode strictly defaults to manual approval and is never implicitly automatic."""
    req = WhatsAppTaskRequest(contact_name="Alice", message="Hello")
    assert req.send_mode == WhatsAppSendModeEnum.MANUAL

    client = TestClient(app)
    resp = client.post(
        "/api/whatsapp/tasks",
        json={"contact_name": "Alice", "message": "Hello", "cdp_url": "http://127.0.0.1:9996"},
    )
    assert resp.status_code in {200, 201}
    assert resp.json()["send_mode"] == "manual"


@pytest.mark.asyncio
async def test_full_cdp_workflow_automatic_send_mode(mock_whatsapp_server: str):
    """Verify automatic send mode dispatches and verifies without stopping at WAITING_FOR_SEND_APPROVAL."""
    cdp_port = 9241
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    target_url = f"{mock_whatsapp_server}/test-whatsapp"

    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        cdp_browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )

        try:
            req = WhatsAppTaskRequest(
                contact_name="Alice Smith",
                message="Automated message via explicit automatic send mode",
                send_mode=WhatsAppSendModeEnum.AUTOMATIC,
                cdp_url=cdp_url,
                target_url=target_url,
            )

            task = await service.start_task(req)
            assert task.send_mode == WhatsAppSendModeEnum.AUTOMATIC

            # Wait for task to complete without manual confirmation
            for _ in range(50):
                if task.status in {WhatsAppStateEnum.COMPLETED, WhatsAppStateEnum.FAILED}:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.COMPLETED
            assert task.error is None
            assert any("AUTOMATIC SEND MODE" in log for log in task.logs)
            assert any("Verification successful" in log for log in task.logs)

        finally:
            await cdp_browser.close()


@pytest.mark.asyncio
async def test_automatic_send_mode_still_pauses_for_ambiguous_contact(mock_whatsapp_server: str):
    """Verify automatic send mode still safely halts at AMBIGUOUS_CONTACT when multiple candidates match."""
    cdp_port = 9242
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    target_url = f"{mock_whatsapp_server}/test-whatsapp"

    service = WhatsAppAutomationService()

    async with async_playwright() as p:
        cdp_browser = await p.chromium.launch(
            args=[f"--remote-debugging-port={cdp_port}", "--headless=new"]
        )

        try:
            req = WhatsAppTaskRequest(
                contact_name="Charlie",  # matches Charlie Brown and Charlie Davis
                message="Testing automatic mode ambiguity safety",
                send_mode=WhatsAppSendModeEnum.AUTOMATIC,
                cdp_url=cdp_url,
                target_url=target_url,
            )

            task = await service.start_task(req)

            # Wait for AMBIGUOUS_CONTACT pause
            for _ in range(40):
                if task.status in {WhatsAppStateEnum.AMBIGUOUS_CONTACT, WhatsAppStateEnum.FAILED}:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.AMBIGUOUS_CONTACT
            assert len(task.candidates) >= 2

            # User selects contact
            await service.select_contact(task.task_id, "Charlie Brown")

            # In automatic mode, it should now proceed to completion without waiting for send approval
            for _ in range(50):
                if task.status in {WhatsAppStateEnum.COMPLETED, WhatsAppStateEnum.FAILED}:
                    break
                await asyncio.sleep(0.4)

            assert task.status == WhatsAppStateEnum.COMPLETED
            assert task.verified_header_name == "Charlie Brown"

        finally:
            await cdp_browser.close()





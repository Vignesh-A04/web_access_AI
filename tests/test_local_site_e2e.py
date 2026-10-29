"""End-to-end tests for browser inspection, actions, and autonomous agent orchestration."""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import AgentTaskState, TaskStateEnum
from app.browser.actions import (
    execute_check_checkbox,
    execute_click,
    execute_extract_table,
    execute_extract_text,
    execute_fill_input,
    execute_select_option,
    execute_verify_element,
)
from app.browser.inspector import inspect_page
from app.browser.manager import PlaywrightBrowserManager
from app.llm.gemini_client import GeminiClient
from app.security.approvals import approval_manager

DEMO_HTML = """
<!DOCTYPE html>
<html>
<head><title>E2E Test Site</title></head>
<body>
    <h1>Welcome to Automation Testing</h1>
    <form id="test-form" action="/test-site/submit" method="POST">
        <input type="text" id="name" name="name" placeholder="Full Name" />
        <input type="email" id="email" name="email" placeholder="Email" />
        <select id="role" name="role">
            <option value="dev">Developer</option>
            <option value="admin">Administrator</option>
        </select>
        <input type="checkbox" id="terms" name="terms" />
        <button type="submit" id="btn-submit">Submit Registration</button>
    </form>
    <table id="data-table">
        <tr><th>ID</th><th>Service</th></tr>
        <tr><td>1</td><td>FastAPI</td></tr>
        <tr><td>2</td><td>Playwright</td></tr>
    </table>
    <div id="result-status">Ready</div>
</body>
</html>
"""

CONFIRMATION_HTML = """
<!DOCTYPE html>
<html>
<head><title>Confirmation</title></head>
<body>
    <h1 id="success-heading">Registration Confirmed!</h1>
    <p>Thank you. Your registration has been processed.</p>
</body>
</html>
"""


class InProcessTestServerHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler to serve test pages during integration tests."""

    def do_GET(self):
        if self.path.startswith("/test-site"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DEMO_HTML.encode("utf-8"))
        elif self.path.startswith("/confirmation"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CONFIRMATION_HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(CONFIRMATION_HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress test noise


@pytest.fixture(scope="module")
def local_test_server():
    """Start an ephemeral HTTP server on localhost for browser automation testing."""
    server = HTTPServer(("127.0.0.1", 0), InProcessTestServerHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_browser_inspector_and_actions():
    """Verify runtime page inspection and deterministic browser action tools on live DOM."""
    manager = PlaywrightBrowserManager(headless=True, allow_local_test=True)
    await manager.initialize()
    context = await manager.create_isolated_context(task_id="test-inspect-actions")
    page = await context.new_page()

    try:
        await page.set_content(DEMO_HTML)

        # 1. Test Inspector
        obs = await inspect_page(page)
        assert obs.title == "E2E Test Site"
        assert len(obs.headings) >= 1
        assert "Welcome to Automation Testing" in obs.headings[0]
        assert len(obs.interactive_elements) >= 4

        # Map elements by name
        el_by_name = {el.get("name"): el.get("element_id") for el in obs.interactive_elements if el.get("name")}
        name_id = el_by_name.get("name")
        email_id = el_by_name.get("email")
        role_id = el_by_name.get("role")
        terms_id = el_by_name.get("terms")

        # 2. Test fill_input
        fill_res = await execute_fill_input(page, name_id, "Dev Tester")
        assert fill_res["success"] is True
        assert fill_res["verified"] is True

        # 3. Test select_option
        sel_res = await execute_select_option(page, role_id, "Administrator")
        assert sel_res["success"] is True

        # 4. Test check_checkbox
        chk_res = await execute_check_checkbox(page, terms_id, True)
        assert chk_res["success"] is True
        assert chk_res["verified"] is True

        # 5. Test extract_table
        tbl_res = await execute_extract_table(page, table_index=0)
        assert tbl_res["success"] is True
        assert len(tbl_res["details"]["rows"]) == 2

        # 6. Test verify_element
        ver_res = await execute_verify_element(
            page,
            element_id=name_id,
            expected_value="Dev Tester",
        )
        assert ver_res["success"] is True

    finally:
        await manager.close_context(context)
        await manager.close()


@pytest.mark.asyncio
async def test_orchestrator_multi_step_flow_with_approval(local_test_server):
    """Verify end-to-end agent orchestration loop with mock Gemini decisions and approval handling."""
    manager = PlaywrightBrowserManager(headless=True, allow_local_test=True)
    await manager.initialize()

    step_counter = 0

    def mock_responder(history):
        nonlocal step_counter
        step_counter += 1
        if step_counter == 1:
            # Step 1: Fill name
            return "fill_input", {"element_id": "el-1", "value": "Jane Smith"}, "Filling name field"
        elif step_counter == 2:
            # Step 2: Fill email
            return "fill_input", {"element_id": "el-2", "value": "jane@example.com"}, "Filling email field"
        elif step_counter == 3:
            # Step 3: Consequential click on submit button
            return (
                "click_element",
                {"element_id": "el-5", "is_consequential": True},
                "Submitting the registration form",
            )
        else:
            # Step 4: Finish task
            return (
                "finish_task",
                {
                    "final_report": "Registration form was filled and submitted successfully.",
                    "verified_outcomes": ["Name and email entered", "Submit action confirmed"],
                },
                "Task completed",
            )

    gemini_client = GeminiClient(api_key="mock", mock_responder=mock_responder)

    task_state = AgentTaskState(
        task_id="e2e-orchestrator-test",
        url=f"{local_test_server}/test-site",
        instruction="Fill the registration form and submit it.",
        max_steps=10,
    )

    orchestrator = AgentOrchestrator(
        task_state=task_state,
        browser_manager=manager,
        gemini_client=gemini_client,
        allow_local_test=True,
    )

    # Background runner for orchestrator with concurrent approval simulator
    async def simulate_user_approval():
        for _ in range(50):
            await asyncio.sleep(0.1)
            if task_state.status == TaskStateEnum.WAITING_FOR_APPROVAL:
                pending = approval_manager.get_pending_for_task(task_state.task_id)
                if pending:
                    approval_manager.resolve_approval(pending.approval_id, approved=True, reason="Auto-approved in test")
                    orchestrator.notify_approval_resolved()
                    break

    approval_task = asyncio.create_task(simulate_user_approval())
    await orchestrator.run()
    await approval_task

    try:
        assert task_state.status == TaskStateEnum.COMPLETED
        assert task_state.final_report is not None
        assert "Registration form was filled" in task_state.final_report
        assert len(task_state.verified_outcomes) >= 1
        assert len(task_state.action_logs) >= 3
    finally:
        await manager.close()

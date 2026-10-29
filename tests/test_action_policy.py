"""Unit tests for action policy classification and approvals lifecycle."""

import pytest
from app.security.action_policy import ActionCategory, classify_action
from app.security.approvals import ApprovalManager


def test_classify_read_only_tools():
    read_only = ["inspect_page", "extract_text", "extract_table", "take_screenshot", "verify_element"]
    for tool in read_only:
        cat, reason = classify_action(tool, {})
        assert cat == ActionCategory.READ_ONLY


def test_classify_reversible_tools():
    reversible = [
        ("fill_input", {"element_id": "el-1", "value": "test"}),
        ("select_option", {"element_id": "el-2", "value_or_label": "opt1"}),
        ("check_checkbox", {"element_id": "el-3", "check": True}),
        ("scroll_page", {"direction": "down"}),
    ]
    for tool, args in reversible:
        cat, reason = classify_action(tool, args)
        assert cat == ActionCategory.REVERSIBLE


def test_classify_consequential_tools():
    # File upload is consequential
    cat, _ = classify_action("upload_file", {"element_id": "el-1", "file_path": "/test.txt"})
    assert cat == ActionCategory.CONSEQUENTIAL

    # Submit button click is consequential
    cat_submit, _ = classify_action(
        "click_element",
        {"element_id": "el-sub"},
        element_metadata={"tag": "button", "type": "submit", "text": "Submit Registration"}
    )
    assert cat_submit == ActionCategory.CONSEQUENTIAL

    # Keyword match in selector/hint
    cat_kw, _ = classify_action("click_element", {"element_id": "el-pay", "selector_hint": "button.pay-now"})
    assert cat_kw == ActionCategory.CONSEQUENTIAL


def test_approval_lifecycle():
    manager = ApprovalManager()
    task_id = "test-task-123"
    approval = manager.create_approval_request(
        task_id=task_id,
        action_name="click_element",
        action_args={"element_id": "el-submit"},
        target_url="https://example.com/checkout",
        page_state_hash="hash-abc-123",
        description="Submit payment form",
    )

    assert approval.is_pending() is True
    assert manager.get_pending_for_task(task_id) == approval

    # Verify state matching
    assert approval.is_valid_for_state("https://example.com/checkout", "hash-abc-123") is True
    assert approval.is_valid_for_state("https://example.com/other", "hash-abc-123") is False
    assert approval.is_valid_for_state("https://example.com/checkout", "hash-drifted") is False

    # Resolve approval
    resolved = manager.resolve_approval(approval.approval_id, approved=True, reason="User confirmed")
    assert resolved.status == "APPROVED"
    assert manager.get_pending_for_task(task_id) is None

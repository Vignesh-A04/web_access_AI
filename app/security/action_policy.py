"""Action policy classifier for browser tools (Read-only, Reversible, Consequential)."""

import enum
from typing import Any, Dict, Optional, Tuple


class ActionCategory(str, enum.Enum):
    """Classification of tool action impact."""
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    CONSEQUENTIAL = "CONSEQUENTIAL"


# Submit/destructive button keywords indicating consequential user action
CONSEQUENTIAL_KEYWORDS = {
    "submit", "pay", "checkout", "purchase", "place order", "buy",
    "delete", "remove", "confirm", "send", "transfer", "publish",
    "register", "sign up", "order now"
}


def classify_action(
    tool_name: str,
    args: Dict[str, Any],
    element_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[ActionCategory, str]:
    """Classify a proposed tool action into READ_ONLY, REVERSIBLE, or CONSEQUENTIAL.

    Returns:
        (category, reason)
    """
    tool = tool_name.lower().strip()

    # 1. Read-only actions
    if tool in {
        "inspect_page", "extract_text", "extract_table",
        "take_screenshot", "verify_element", "wait_for_element"
    }:
        return ActionCategory.READ_ONLY, "Inspection or verification action without state mutation."

    # 2. File upload is always consequential as it transfers user files
    if tool == "upload_file":
        return ActionCategory.CONSEQUENTIAL, "Uploading a file introduces persistent external data."

    # 3. Finish task is completed state
    if tool == "finish_task":
        return ActionCategory.READ_ONLY, "Finishing task and compiling final report."

    # 4. Check for click_element
    if tool == "click_element":
        # Check if caller explicitly flagged it
        if args.get("is_consequential"):
            return ActionCategory.CONSEQUENTIAL, "Action explicitly flagged as consequential."

        # Check element metadata if provided by inspector
        meta = element_metadata or {}
        el_tag = str(meta.get("tag", "")).lower()
        el_type = str(meta.get("type", "")).lower()
        el_text = str(meta.get("text", "")).lower()
        el_role = str(meta.get("role", "")).lower()
        el_label = str(meta.get("aria_label", "")).lower()

        # Check for submit buttons or inputs
        if el_type == "submit" or (el_tag == "button" and el_type != "button"):
            for keyword in CONSEQUENTIAL_KEYWORDS:
                if keyword in el_text or keyword in el_label:
                    return ActionCategory.CONSEQUENTIAL, f"Clicking submit/action button containing '{keyword}' is consequential."

        for keyword in CONSEQUENTIAL_KEYWORDS:
            if keyword in el_text or keyword in el_label:
                return ActionCategory.CONSEQUENTIAL, f"Clicking element with consequential keyword '{keyword}' requires confirmation."

        # If clicking an element whose selector or text explicitly signals submission
        selector_hint = str(args.get("element_id", "")).lower() + " " + str(args.get("selector_hint", "")).lower()
        for keyword in CONSEQUENTIAL_KEYWORDS:
            if keyword in selector_hint:
                return ActionCategory.CONSEQUENTIAL, f"Clicking element matching '{keyword}' requires confirmation."

        # Regular navigational / interactive clicks are reversible
        return ActionCategory.REVERSIBLE, "Standard interactive click on page element."

    # 5. Form field inputs and selections
    if tool in {"fill_input", "select_option", "check_checkbox", "uncheck_checkbox", "press_key"}:
        # Pressing 'Enter' inside a form input might submit it, but typing itself is reversible
        if tool == "press_key" and args.get("key", "").lower() == "enter":
            return ActionCategory.CONSEQUENTIAL, "Pressing Enter may submit the active form."
        return ActionCategory.REVERSIBLE, f"Modifying form field with {tool} is reversible before submission."

    # 6. Navigation and scrolling
    if tool in {"navigate", "go_back", "go_forward", "scroll_page"}:
        return ActionCategory.REVERSIBLE, f"Page movement with {tool} is reversible."

    # Fallback default: Treat unknown actions cautiously
    return ActionCategory.CONSEQUENTIAL, f"Unknown tool '{tool_name}' classified as consequential for safety."

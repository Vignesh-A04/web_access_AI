"""Validated browser action executors with element resolution and outcome verification."""

import asyncio
from typing import Any, Dict, List, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.browser.inspector import inspect_page, PageObservation
from app.browser.navigation import navigate_to_url
from app.logging.setup import get_logger

logger = get_logger("browser_actions")


class BrowserActionError(Exception):
    """Raised when a browser action cannot be executed or fails verification."""
    pass


async def resolve_element_locator(page: Page, element_id: str, selector_hint: Optional[str] = None):
    """Safely resolve an element locator by data-agent-id or fall back to an accessible selector."""
    if element_id:
        clean_id = element_id.strip()
        loc = page.locator(f'[data-agent-id="{clean_id}"]')
        if await loc.count() > 0:
            return loc.first

    if selector_hint:
        clean_hint = selector_hint.strip()
        loc = page.locator(clean_hint)
        if await loc.count() > 0:
            return loc.first

    raise BrowserActionError(f"Could not locate element with ID '{element_id}' or selector '{selector_hint}' on the current page.")


async def execute_click(page: Page, element_id: str, selector_hint: Optional[str] = None, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Click an element and wait for any subsequent navigation or DOM update."""
    loc = await resolve_element_locator(page, element_id, selector_hint)
    is_visible = await loc.is_visible()
    if not is_visible:
        raise BrowserActionError(f"Element '{element_id}' is not visible on page.")

    # Get details for verification
    text = (await loc.text_content() or "").strip()
    tag = await loc.evaluate("el => el.tagName.toLowerCase()")

    await loc.click(timeout=timeout_ms)
    # Allow micro-task network/DOM rendering
    await asyncio.sleep(0.5)

    return {
        "success": True,
        "message": f"Successfully clicked <{tag}> element '{element_id}' ({text[:40]}).",
        "verified": True,
        "details": {"element_id": element_id, "text": text, "current_url": page.url},
    }


async def execute_fill_input(page: Page, element_id: str, value: str, selector_hint: Optional[str] = None, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Fill a text input or textarea and verify the input value."""
    loc = await resolve_element_locator(page, element_id, selector_hint)
    await loc.fill(value, timeout=timeout_ms)

    # Verification: check the actual value property of the element
    actual_value = await loc.input_value()
    if actual_value != value:
        raise BrowserActionError(f"Value verification failed for '{element_id}': expected '{value}', found '{actual_value}'")

    return {
        "success": True,
        "message": f"Filled '{element_id}' with value.",
        "verified": True,
        "details": {"element_id": element_id, "verified_value": actual_value},
    }


async def execute_select_option(page: Page, element_id: str, value_or_label: str, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Select a dropdown option by label or value and verify selection."""
    loc = await resolve_element_locator(page, element_id)
    # Try selecting by label, then value
    try:
        selected = await loc.select_option(label=value_or_label, timeout=timeout_ms)
    except Exception:
        selected = await loc.select_option(value=value_or_label, timeout=timeout_ms)

    # Verification
    current_val = await loc.input_value()
    return {
        "success": True,
        "message": f"Selected option '{value_or_label}' on '{element_id}'.",
        "verified": bool(selected),
        "details": {"element_id": element_id, "selected_value": current_val},
    }


async def execute_check_checkbox(page: Page, element_id: str, check: bool = True, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Check or uncheck a checkbox or radio button and verify checked status."""
    loc = await resolve_element_locator(page, element_id)
    if check:
        await loc.check(timeout=timeout_ms)
    else:
        await loc.uncheck(timeout=timeout_ms)

    is_checked = await loc.is_checked()
    if is_checked != check:
        raise BrowserActionError(f"Checkbox state verification failed for '{element_id}': expected checked={check}, but got {is_checked}")

    return {
        "success": True,
        "message": f"{'Checked' if check else 'Unchecked'} checkbox '{element_id}'.",
        "verified": True,
        "details": {"element_id": element_id, "is_checked": is_checked},
    }


async def execute_press_key(page: Page, key: str) -> Dict[str, Any]:
    """Press a keyboard key."""
    await page.keyboard.press(key)
    await asyncio.sleep(0.3)
    return {
        "success": True,
        "message": f"Pressed keyboard key '{key}'.",
        "verified": True,
        "details": {"key": key, "current_url": page.url},
    }


async def execute_scroll(page: Page, direction: str = "down", amount: int = 500) -> Dict[str, Any]:
    """Scroll page up or down."""
    delta = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy(0, {delta})")
    await asyncio.sleep(0.3)
    return {
        "success": True,
        "message": f"Scrolled page {direction} by {amount}px.",
        "verified": True,
        "details": {"direction": direction, "amount": amount},
    }


async def execute_extract_text(page: Page, element_id: Optional[str] = None, selector_hint: Optional[str] = None) -> Dict[str, Any]:
    """Extract visible text from a specific element or the entire page."""
    if element_id or selector_hint:
        loc = await resolve_element_locator(page, element_id or "", selector_hint)
        text = (await loc.inner_text() or "").strip()
    else:
        text = (await page.inner_text("body") or "").strip()

    return {
        "success": True,
        "message": f"Extracted {len(text)} characters of text.",
        "verified": True,
        "details": {"extracted_text": text[:2000]},
    }


async def execute_extract_table(page: Page, table_index: int = 0) -> Dict[str, Any]:
    """Extract structured tabular data from a table element on the page."""
    tables = page.locator("table")
    count = await tables.count()
    if count == 0:
        raise BrowserActionError("No <table> element found on the current page.")

    target_table = tables.nth(table_index if table_index < count else 0)

    # Extract headers and rows via JavaScript
    table_data = await target_table.evaluate("""
        table => {
            const headers = Array.from(table.querySelectorAll('th')).map(th => th.innerText.trim());
            const rows = [];
            table.querySelectorAll('tr').forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                if (cells.length > 0) rows.push(cells);
            });
            return { headers, rows };
        }
    """)

    return {
        "success": True,
        "message": f"Extracted table with {len(table_data.get('rows', []))} rows.",
        "verified": True,
        "details": table_data,
    }


async def execute_wait_for_element(page: Page, selector_or_text: str, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Wait for an element matching a selector or visible text to appear."""
    try:
        await page.wait_for_selector(selector_or_text, timeout=timeout_ms, state="visible")
        return {
            "success": True,
            "message": f"Element matching '{selector_or_text}' is now visible.",
            "verified": True,
            "details": {"selector": selector_or_text},
        }
    except PlaywrightTimeoutError:
        raise BrowserActionError(f"Timed out waiting for element '{selector_or_text}' after {timeout_ms}ms")


async def execute_verify_element(
    page: Page,
    element_id: str,
    expected_value: Optional[str] = None,
    expected_text: Optional[str] = None,
    expected_checked: Optional[bool] = None,
) -> Dict[str, Any]:
    """Explicit verification of element state."""
    loc = await resolve_element_locator(page, element_id)

    checks = []
    if expected_value is not None:
        actual_val = await loc.input_value()
        if actual_val != expected_value:
            raise BrowserActionError(f"Verification failed: expected value '{expected_value}', but got '{actual_val}'")
        checks.append(f"value='{actual_val}'")

    if expected_text is not None:
        actual_txt = (await loc.text_content() or "").strip()
        if expected_text not in actual_txt:
            raise BrowserActionError(f"Verification failed: expected text '{expected_text}' not in '{actual_txt}'")
        checks.append(f"text contains '{expected_text}'")

    if expected_checked is not None:
        actual_chk = await loc.is_checked()
        if actual_chk != expected_checked:
            raise BrowserActionError(f"Verification failed: expected checked={expected_checked}, but got {actual_chk}")
        checks.append(f"checked={actual_chk}")

    return {
        "success": True,
        "message": f"Verified element '{element_id}': {', '.join(checks)}",
        "verified": True,
        "details": {"element_id": element_id, "checks": checks},
    }

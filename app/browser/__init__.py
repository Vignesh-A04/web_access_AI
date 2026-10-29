"""Browser package exports."""

from app.browser.manager import PlaywrightBrowserManager
from app.browser.inspector import inspect_page, PageObservation
from app.browser.navigation import navigate_to_url, NavigationSecurityError
from app.browser.actions import (
    BrowserActionError,
    execute_click,
    execute_fill_input,
    execute_select_option,
    execute_check_checkbox,
    execute_press_key,
    execute_scroll,
    execute_extract_text,
    execute_extract_table,
    execute_wait_for_element,
    execute_verify_element,
)

__all__ = [
    "PlaywrightBrowserManager",
    "inspect_page",
    "PageObservation",
    "navigate_to_url",
    "NavigationSecurityError",
    "BrowserActionError",
    "execute_click",
    "execute_fill_input",
    "execute_select_option",
    "execute_check_checkbox",
    "execute_press_key",
    "execute_scroll",
    "execute_extract_text",
    "execute_extract_table",
    "execute_wait_for_element",
    "execute_verify_element",
]

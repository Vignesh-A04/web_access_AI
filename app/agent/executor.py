"""Action executor dispatching validated tools to browser operations with error handling."""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from playwright.async_api import Page

from app.browser.actions import (
    BrowserActionError,
    execute_check_checkbox,
    execute_click,
    execute_extract_table,
    execute_extract_text,
    execute_fill_input,
    execute_press_key,
    execute_scroll,
    execute_select_option,
    execute_verify_element,
    execute_wait_for_element,
)
from app.browser.navigation import navigate_to_url
from app.browser.inspector import inspect_page
from app.logging.setup import get_logger

logger = get_logger("action_executor")


@dataclass
class ActionResult:
    """Outcome of an attempted browser tool execution."""
    success: bool
    message: str
    verified: bool = False
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ActionExecutor:
    """Dispatches validated tool calls to concrete browser actions."""

    async def execute(
        self,
        page: Page,
        tool_name: str,
        arguments: Dict[str, Any],
        allow_local_test: bool = False,
        domain_restrictions: Optional[set] = None,
        timeout_ms: int = 10000,
    ) -> ActionResult:
        """Execute a validated browser tool with timeout and error capture."""
        tool = tool_name.lower().strip()

        try:
            if tool == "navigate":
                target_url = arguments.get("url", "")
                final_url, status = await navigate_to_url(
                    page,
                    target_url,
                    allow_local_test=allow_local_test,
                    domain_restrictions=domain_restrictions,
                    timeout_ms=timeout_ms * 2,
                )
                return ActionResult(
                    success=True,
                    message=f"Successfully navigated to {final_url} (HTTP {status})",
                    verified=True,
                    details={"final_url": final_url, "status": status},
                )

            elif tool == "click_element":
                res = await execute_click(
                    page,
                    element_id=arguments.get("element_id", ""),
                    selector_hint=arguments.get("selector_hint"),
                    timeout_ms=timeout_ms,
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "fill_input":
                res = await execute_fill_input(
                    page,
                    element_id=arguments.get("element_id", ""),
                    value=arguments.get("value", ""),
                    selector_hint=arguments.get("selector_hint"),
                    timeout_ms=timeout_ms,
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "select_option":
                res = await execute_select_option(
                    page,
                    element_id=arguments.get("element_id", ""),
                    value_or_label=arguments.get("value_or_label", ""),
                    timeout_ms=timeout_ms,
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "check_checkbox":
                res = await execute_check_checkbox(
                    page,
                    element_id=arguments.get("element_id", ""),
                    check=arguments.get("check", True),
                    timeout_ms=timeout_ms,
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "press_key":
                res = await execute_press_key(page, key=arguments.get("key", ""))
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "scroll_page":
                res = await execute_scroll(
                    page,
                    direction=arguments.get("direction", "down"),
                    amount=arguments.get("amount", 500),
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "extract_text":
                res = await execute_extract_text(
                    page,
                    element_id=arguments.get("element_id"),
                    selector_hint=arguments.get("selector_hint"),
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "extract_table":
                res = await execute_extract_table(page, table_index=arguments.get("table_index", 0))
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "wait_for_element":
                res = await execute_wait_for_element(
                    page,
                    selector_or_text=arguments.get("selector_or_text", ""),
                    timeout_ms=arguments.get("timeout_ms", timeout_ms),
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "verify_element":
                res = await execute_verify_element(
                    page,
                    element_id=arguments.get("element_id", ""),
                    expected_value=arguments.get("expected_value"),
                    expected_text=arguments.get("expected_text"),
                    expected_checked=arguments.get("expected_checked"),
                )
                return ActionResult(
                    success=res["success"],
                    message=res["message"],
                    verified=res["verified"],
                    details=res.get("details"),
                )

            elif tool == "inspect_page":
                obs = await inspect_page(page)
                return ActionResult(
                    success=True,
                    message=f"Page re-inspected: {len(obs.interactive_elements)} interactive elements found.",
                    verified=True,
                    details={"element_count": len(obs.interactive_elements)},
                )

            elif tool == "go_back":
                await page.go_back()
                return ActionResult(success=True, message=f"Navigated back to {page.url}", verified=True)

            elif tool == "go_forward":
                await page.go_forward()
                return ActionResult(success=True, message=f"Navigated forward to {page.url}", verified=True)

            elif tool == "take_screenshot":
                return ActionResult(success=True, message="Screenshot captured", verified=True)

            elif tool == "finish_task":
                return ActionResult(
                    success=True,
                    message="Task finished signal received.",
                    verified=True,
                    details=arguments,
                )

            else:
                return ActionResult(
                    success=False,
                    message=f"Unsupported tool '{tool}'",
                    verified=False,
                    error=f"Tool '{tool}' not implemented in executor",
                )

        except BrowserActionError as e:
            logger.warning(f"Browser action error executing {tool}: {e}")
            return ActionResult(success=False, message=str(e), verified=False, error=str(e))
        except Exception as e:
            logger.error(f"Unexpected error executing {tool}: {e}")
            return ActionResult(success=False, message=f"Action execution failed: {e}", verified=False, error=str(e))

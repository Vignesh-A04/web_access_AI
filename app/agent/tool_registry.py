"""Tool definitions, Pydantic argument validation, and Gemini Function Declarations."""

from typing import Any, Dict, List, Optional, Type
from google.genai import types
from pydantic import BaseModel, Field, ValidationError


# ==========================================
# Tool Argument Models
# ==========================================

class NavigateArgs(BaseModel):
    """Navigate to a specified URL."""
    url: str = Field(..., description="Target web URL (http or https)")


class ClickElementArgs(BaseModel):
    """Click an interactive element identified by its task-scoped element ID (e.g., 'el-1')."""
    element_id: str = Field(..., description="The temporary element identifier like 'el-1', 'el-2'")
    selector_hint: Optional[str] = Field(default=None, description="Optional CSS or accessible selector fallback")
    is_consequential: Optional[bool] = Field(default=False, description="Flag indicating if this click submits or changes external data")


class FillInputArgs(BaseModel):
    """Fill a text input or textarea with a value."""
    element_id: str = Field(..., description="The element identifier (e.g. 'el-2')")
    value: str = Field(..., description="The exact text value to type or enter")
    selector_hint: Optional[str] = Field(default=None, description="Optional CSS selector fallback")


class SelectOptionArgs(BaseModel):
    """Select an option in a dropdown <select> element."""
    element_id: str = Field(..., description="The dropdown element identifier (e.g. 'el-3')")
    value_or_label: str = Field(..., description="The visible option label or value attribute to select")


class CheckCheckboxArgs(BaseModel):
    """Check or uncheck a checkbox or radio button."""
    element_id: str = Field(..., description="The element identifier (e.g. 'el-4')")
    check: bool = Field(default=True, description="True to check, False to uncheck")


class PressKeyArgs(BaseModel):
    """Press a key on the active element or page."""
    key: str = Field(..., description="Key name to press (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown')")


class ScrollPageArgs(BaseModel):
    """Scroll the page view up or down."""
    direction: str = Field(default="down", description="'down' or 'up'")
    amount: int = Field(default=500, description="Number of pixels to scroll (positive integer)")


class ExtractTextArgs(BaseModel):
    """Extract visible text content from the whole page or a specific element."""
    element_id: Optional[str] = Field(default=None, description="Optional element ID to scope text extraction")
    selector_hint: Optional[str] = Field(default=None, description="Optional CSS selector hint")


class ExtractTableArgs(BaseModel):
    """Extract tabular structured data from an HTML table."""
    table_index: int = Field(default=0, description="Zero-based index of the table on the page")


class TakeScreenshotArgs(BaseModel):
    """Take a full screenshot of the current page for visual validation."""
    pass


class GoBackArgs(BaseModel):
    """Navigate back in browser history."""
    pass


class GoForwardArgs(BaseModel):
    """Navigate forward in browser history."""
    pass


class WaitForElementArgs(BaseModel):
    """Wait for an element matching a selector or text to appear."""
    selector_or_text: str = Field(..., description="CSS selector or visible text to wait for")
    timeout_ms: int = Field(default=10000, description="Maximum wait time in milliseconds")


class UploadFileArgs(BaseModel):
    """Upload a user-provided file to a file input element."""
    element_id: str = Field(..., description="Target file input element ID (e.g. 'el-5')")
    file_path: str = Field(..., description="Absolute path to the user-provided file")


class VerifyElementArgs(BaseModel):
    """Verify that an element satisfies expected text, input value, or checked state."""
    element_id: str = Field(..., description="Element ID to verify (e.g. 'el-1')")
    expected_value: Optional[str] = Field(default=None, description="Expected input value")
    expected_text: Optional[str] = Field(default=None, description="Expected text substring")
    expected_checked: Optional[bool] = Field(default=None, description="Expected checked boolean status")


class InspectPageArgs(BaseModel):
    """Re-inspect the current page DOM and interactive elements."""
    pass


class FinishTaskArgs(BaseModel):
    """Complete the automation task, verify outcomes, and provide final report."""
    final_report: str = Field(..., description="Concise, factual summary of the executed actions and findings")
    verified_outcomes: List[str] = Field(default_factory=list, description="List of specifically verified task outcomes")


# Registry mapping tool names to their Pydantic argument schemas
TOOL_ARG_SCHEMAS: Dict[str, Type[BaseModel]] = {
    "navigate": NavigateArgs,
    "click_element": ClickElementArgs,
    "fill_input": FillInputArgs,
    "select_option": SelectOptionArgs,
    "check_checkbox": CheckCheckboxArgs,
    "press_key": PressKeyArgs,
    "scroll_page": ScrollPageArgs,
    "extract_text": ExtractTextArgs,
    "extract_table": ExtractTableArgs,
    "take_screenshot": TakeScreenshotArgs,
    "go_back": GoBackArgs,
    "go_forward": GoForwardArgs,
    "wait_for_element": WaitForElementArgs,
    "upload_file": UploadFileArgs,
    "verify_element": VerifyElementArgs,
    "inspect_page": InspectPageArgs,
    "finish_task": FinishTaskArgs,
}


def validate_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> BaseModel:
    """Validate raw tool arguments against the registered Pydantic schema."""
    schema_cls = TOOL_ARG_SCHEMAS.get(tool_name)
    if not schema_cls:
        raise ValueError(f"Unknown tool '{tool_name}'. Registered tools: {list(TOOL_ARG_SCHEMAS.keys())}")

    try:
        return schema_cls.model_validate(arguments or {})
    except ValidationError as e:
        raise ValueError(f"Invalid arguments for tool '{tool_name}': {e}") from e


def get_gemini_tool_declarations() -> List[types.Tool]:
    """Generate Gemini function declarations for all registered browser automation tools."""
    declarations = [
        types.FunctionDeclaration(
            name="navigate",
            description="Navigate to a target website URL.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "url": {"type": "STRING", "description": "Target website URL (http or https)"}
                },
                "required": ["url"],
            },
        ),
        types.FunctionDeclaration(
            name="click_element",
            description="Click an interactive button, link, or element using its assigned ID (e.g. 'el-1').",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "The element ID such as 'el-1'"},
                    "selector_hint": {"type": "STRING", "description": "Optional CSS selector fallback"},
                    "is_consequential": {"type": "BOOLEAN", "description": "True if clicking this submits data or triggers persistent changes"},
                },
                "required": ["element_id"],
            },
        ),
        types.FunctionDeclaration(
            name="fill_input",
            description="Fill a text input or textarea field with text.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "The input element ID (e.g. 'el-2')"},
                    "value": {"type": "STRING", "description": "Text value to fill into the field"},
                    "selector_hint": {"type": "STRING", "description": "Optional CSS selector fallback"},
                },
                "required": ["element_id", "value"],
            },
        ),
        types.FunctionDeclaration(
            name="select_option",
            description="Select an option in a dropdown <select> menu.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "The dropdown element ID (e.g. 'el-3')"},
                    "value_or_label": {"type": "STRING", "description": "The visible text or value of the option to select"},
                },
                "required": ["element_id", "value_or_label"],
            },
        ),
        types.FunctionDeclaration(
            name="check_checkbox",
            description="Check or uncheck a checkbox or radio button.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "The element ID (e.g. 'el-4')"},
                    "check": {"type": "BOOLEAN", "description": "True to check, False to uncheck"},
                },
                "required": ["element_id"],
            },
        ),
        types.FunctionDeclaration(
            name="press_key",
            description="Press a keyboard key on the active page or element.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "key": {"type": "STRING", "description": "Key name (e.g. 'Enter', 'Tab', 'Escape')"},
                },
                "required": ["key"],
            },
        ),
        types.FunctionDeclaration(
            name="scroll_page",
            description="Scroll the page view up or down.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "direction": {"type": "STRING", "enum": ["down", "up"], "description": "'down' or 'up'"},
                    "amount": {"type": "INTEGER", "description": "Scroll distance in pixels (default: 500)"},
                },
            },
        ),
        types.FunctionDeclaration(
            name="extract_text",
            description="Extract visible text content from the entire page or a specific element.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "Optional element ID to extract text from"},
                    "selector_hint": {"type": "STRING", "description": "Optional CSS selector fallback"},
                },
            },
        ),
        types.FunctionDeclaration(
            name="extract_table",
            description="Extract structured tabular data from a <table> element.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "table_index": {"type": "INTEGER", "description": "Index of table on page (default 0)"},
                },
            },
        ),
        types.FunctionDeclaration(
            name="take_screenshot",
            description="Capture a screenshot of the current page for inspection.",
            parameters={"type": "OBJECT", "properties": {}},
        ),
        types.FunctionDeclaration(
            name="go_back",
            description="Go back to the previous page in browser history.",
            parameters={"type": "OBJECT", "properties": {}},
        ),
        types.FunctionDeclaration(
            name="go_forward",
            description="Go forward to the next page in browser history.",
            parameters={"type": "OBJECT", "properties": {}},
        ),
        types.FunctionDeclaration(
            name="wait_for_element",
            description="Wait for an element matching a selector or text to appear on the page.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "selector_or_text": {"type": "STRING", "description": "Selector or text to wait for"},
                    "timeout_ms": {"type": "INTEGER", "description": "Timeout in milliseconds"},
                },
                "required": ["selector_or_text"],
            },
        ),
        types.FunctionDeclaration(
            name="upload_file",
            description="Upload an authorized local file to a file input.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "File input element ID"},
                    "file_path": {"type": "STRING", "description": "Path to file"},
                },
                "required": ["element_id", "file_path"],
            },
        ),
        types.FunctionDeclaration(
            name="verify_element",
            description="Verify that an element contains expected text, value, or checked state.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "element_id": {"type": "STRING", "description": "Element ID to verify"},
                    "expected_value": {"type": "STRING", "description": "Expected input value"},
                    "expected_text": {"type": "STRING", "description": "Expected text substring"},
                    "expected_checked": {"type": "BOOLEAN", "description": "Expected checked state"},
                },
                "required": ["element_id"],
            },
        ),
        types.FunctionDeclaration(
            name="inspect_page",
            description="Re-inspect the current page DOM to refresh the interactive elements list.",
            parameters={"type": "OBJECT", "properties": {}},
        ),
        types.FunctionDeclaration(
            name="finish_task",
            description="Declare the task finished with a final factual report and verified outcomes.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "final_report": {"type": "STRING", "description": "Factual report summarizing findings and completed actions"},
                    "verified_outcomes": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "List of outcomes that were explicitly verified",
                    },
                },
                "required": ["final_report"],
            },
        ),
    ]
    return [types.Tool(function_declarations=declarations)]

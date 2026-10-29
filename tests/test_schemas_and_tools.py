"""Unit tests for tool argument validation and Gemini declarations."""

import pytest
from app.agent.tool_registry import (
    validate_tool_arguments,
    get_gemini_tool_declarations,
    TOOL_ARG_SCHEMAS,
)


def test_registered_tools_count():
    assert len(TOOL_ARG_SCHEMAS) >= 15


def test_validate_valid_tool_arguments():
    # navigate
    nav = validate_tool_arguments("navigate", {"url": "https://example.com"})
    assert nav.url == "https://example.com"

    # click_element
    clk = validate_tool_arguments("click_element", {"element_id": "el-1"})
    assert clk.element_id == "el-1"

    # fill_input
    fill = validate_tool_arguments("fill_input", {"element_id": "el-2", "value": "Jane Doe"})
    assert fill.value == "Jane Doe"

    # finish_task
    fin = validate_tool_arguments("finish_task", {"final_report": "Completed successfully.", "verified_outcomes": ["Form submitted"]})
    assert fin.final_report == "Completed successfully."
    assert "Form submitted" in fin.verified_outcomes


def test_validate_invalid_tool_arguments():
    # Missing required argument 'url' for navigate
    with pytest.raises(ValueError):
        validate_tool_arguments("navigate", {})

    # Missing required argument 'element_id' for fill_input
    with pytest.raises(ValueError):
        validate_tool_arguments("fill_input", {"value": "test"})

    # Unknown tool
    with pytest.raises(ValueError) as exc:
        validate_tool_arguments("unknown_arbitrary_tool", {})
    assert "unknown tool" in str(exc.value).lower()


def test_gemini_tool_declarations():
    tools = get_gemini_tool_declarations()
    assert len(tools) == 1
    func_decls = tools[0].function_declarations
    assert len(func_decls) >= 15
    names = {fd.name for fd in func_decls}
    assert "navigate" in names
    assert "click_element" in names
    assert "fill_input" in names
    assert "finish_task" in names

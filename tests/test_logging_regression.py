"""Regression tests verifying logging fixes and sensitive data redaction."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.llm.gemini_client import GeminiClient
from app.logging.setup import StructuredJsonFormatter, sanitize_data


RESERVED_LOGRECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


@pytest.mark.asyncio
async def test_decide_action_logging_does_not_raise_args_overwrite_error(caplog):
    """Verify that GeminiClient.decide_action logs tool selection without attempting to overwrite reserved 'args'."""
    client = GeminiClient(api_key="test_api_key")

    mock_response = MagicMock()
    mock_response.text = "Filling credentials"
    mock_call = MagicMock()
    mock_call.name = "fill_input"
    mock_call.args = {"element_id": "el-1", "value": "test_user", "password": "supersecretpassword"}
    mock_response.function_calls = [mock_call]

    mock_generate = AsyncMock(return_value=mock_response)
    client._client = MagicMock()
    client._client.aio.models.generate_content = mock_generate

    with caplog.at_level(logging.INFO, logger="gemini_client"):
        tool_name, args, explanation = await client.decide_action([])

    assert tool_name == "fill_input"
    assert args["element_id"] == "el-1"

    # Find the log record produced by decide_action
    tool_logs = [r for r in caplog.records if r.name == "gemini_client" and "Gemini selected tool" in r.message]
    assert len(tool_logs) == 1
    record = tool_logs[0]

    # Verify that 'args' in record is the standard LogRecord formatting tuple (not overwritten)
    assert isinstance(record.args, tuple)
    # Verify that our safe field 'tool_args' is present on the record
    assert hasattr(record, "tool_args")
    assert record.tool_args["element_id"] == "el-1"
    # Verify sensitive data was redacted before or during logging
    assert record.tool_args["password"] == "***REDACTED***"


def test_structured_json_formatter_handles_tool_args_and_redaction():
    """Verify StructuredJsonFormatter formats tool_args cleanly into JSON with redaction."""
    formatter = StructuredJsonFormatter()
    logger = logging.getLogger("test_formatter")
    
    # Create record with extra tool_args
    record = logger.makeRecord(
        name="test_formatter",
        level=logging.INFO,
        fn="test_file.py",
        lno=10,
        msg="Executing tool",
        args=(),
        exc_info=None,
        extra={"tool_name": "fill_input", "tool_args": {"password": "mypassword", "value": "hello"}},
    )

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["tool_name"] == "fill_input"
    assert parsed["tool_args"]["value"] == "hello"
    assert parsed["tool_args"]["password"] == "***REDACTED***"


def test_no_extra_dict_uses_reserved_logrecord_keys():
    """Verify that none of the reserved LogRecord keys are used in any logging extra dictionary."""
    import ast
    import glob

    python_files = glob.glob("app/**/*.py", recursive=True)
    assert len(python_files) > 0

    conflicts = []
    for filepath in python_files:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "extra" and isinstance(keyword.value, ast.Dict):
                        for key_node in keyword.value.keys:
                            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                                if key_node.value in RESERVED_LOGRECORD_KEYS:
                                    conflicts.append((filepath, key_node.lineno, key_node.value))

    assert conflicts == [], f"Found reserved LogRecord keys in extra dicts: {conflicts}"

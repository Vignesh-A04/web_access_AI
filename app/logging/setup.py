"""Logging configuration with structured logs and sensitive data masking."""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict

# Patterns for sensitive data that must never appear in logs
SENSITIVE_PATTERNS = [
    (re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\'])([^"\']{4,})(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(authorization["\']?\s*[:=]\s*["\']bearer\s+)([^"\']{4,})(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(cookie["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'AIzaSy[A-Za-z0-9_-]{33}', re.IGNORECASE), r'***GEMINI_API_KEY_REDACTED***'),
]


def redact_sensitive_string(text: str) -> str:
    """Mask sensitive patterns such as API keys, tokens, and passwords in a string."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_data(data: Any) -> Any:
    """Recursively sanitize sensitive fields in dictionaries, lists, and primitives."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(secret_term in k_lower for secret_term in ["password", "secret", "token", "api_key", "cookie", "auth"]):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return redact_sensitive_string(data)
    return data


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter that enforces structured logs and redaction."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_string(record.getMessage()),
        }

        # Include custom task context if present
        if hasattr(record, "task_id"):
            log_entry["task_id"] = record.task_id
        if hasattr(record, "tool_name"):
            log_entry["tool_name"] = record.tool_name
        if hasattr(record, "tool_args"):
            log_entry["tool_args"] = sanitize_data(record.tool_args)
        if hasattr(record, "action_arguments"):
            log_entry["action_arguments"] = sanitize_data(record.action_arguments)
        if hasattr(record, "step"):
            log_entry["step"] = record.step
        if hasattr(record, "url"):
            log_entry["url"] = record.url
        if hasattr(record, "headless"):
            log_entry["headless"] = record.headless
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry["data"] = sanitize_data(record.extra_data)

        if record.exc_info:
            log_entry["exception"] = redact_sensitive_string(self.formatException(record.exc_info))

        return json.dumps(log_entry)



def setup_logging(level: str = "INFO", structured: bool = True) -> logging.Logger:
    """Configure system-wide logging with redaction and structured output."""
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if structured:
        console_handler.setFormatter(StructuredJsonFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
        )

    root_logger.addHandler(console_handler)
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)

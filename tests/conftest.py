"""Pytest configuration, fixtures, and mock clients."""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure local test domains are permitted during tests
os.environ["ALLOW_LOCAL_TEST_DOMAINS"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"

from app.main import app
from app.config import settings
from app.llm.gemini_client import GeminiClient


@pytest.fixture
def test_client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_gemini_client():
    """GeminiClient with configurable mock responder."""
    def _create_mock(responder_func):
        return GeminiClient(
            api_key="mock_key",
            mock_responder=responder_func,
        )
    return _create_mock

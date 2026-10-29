"""Regression tests for centralized Gemini model configuration."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.llm.gemini_client import GeminiClient, GeminiClientError
from app.services.task_service import task_service
from google.genai.errors import APIError


def test_default_model_is_gemini_3_5_flash_lite():
    """Verify that the centralized default model is 'gemini-3.5-flash-lite'."""
    # Test a fresh Settings instance without external env overrides
    default_settings = Settings(_env_file=None)
    assert default_settings.gemini_model == "gemini-3.5-flash-lite"
    assert default_settings.GEMINI_MODEL == "gemini-3.5-flash-lite"


def test_gemini_model_env_var_override(monkeypatch):
    """Verify that an explicit GEMINI_MODEL environment variable overrides the default."""
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-override-model")
    custom_settings = Settings(_env_file=None)
    assert custom_settings.gemini_model == "gemini-test-override-model"
    assert custom_settings.GEMINI_MODEL == "gemini-test-override-model"


def test_production_clients_use_centralized_configuration():
    """Verify that all production Gemini clients in services use the centralized model."""
    client = GeminiClient()
    assert client.model == settings.gemini_model
    assert task_service.gemini_client.model == settings.gemini_model
    # Explicitly check no deprecated fallback IDs are present
    assert client.model != "gemini-2.5-flash"
    assert client.model != "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_gemini_client_passes_configured_model_to_sdk():
    """Verify that GeminiClient.decide_action passes the configured model ID to aio.models.generate_content."""
    client = GeminiClient(api_key="test_api_key")
    
    mock_response = MagicMock()
    mock_response.text = "Action explanation"
    mock_call = MagicMock()
    mock_call.name = "finish_task"
    mock_call.args = {"final_report": "Done"}
    mock_response.function_calls = [mock_call]

    mock_generate = AsyncMock(return_value=mock_response)
    client._client = MagicMock()
    client._client.aio.models.generate_content = mock_generate

    tool_name, args, explanation = await client.decide_action([])
    
    assert tool_name == "finish_task"
    assert args == {"final_report": "Done"}
    mock_generate.assert_awaited_once()
    call_kwargs = mock_generate.call_args.kwargs
    assert call_kwargs["model"] == settings.gemini_model
    assert call_kwargs["model"] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_client_handles_model_unavailable_error():
    """Verify that model-unavailable or quota API errors are clearly reported with model context."""
    client = GeminiClient(api_key="test_api_key")
    
    mock_generate = AsyncMock(
        side_effect=APIError(404, {"error": {"message": "Model 'gemini-3.5-flash-lite' is not found or not supported"}})
    )

    client._client = MagicMock()
    client._client.aio.models.generate_content = mock_generate

    with pytest.raises(GeminiClientError) as exc_info:
        await client.decide_action([])
    
    assert "gemini-3.5-flash-lite" in str(exc_info.value)
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value)


def test_health_endpoint_reports_configured_model(test_client: TestClient):
    """Verify that the /health endpoint safely reports the configured model ID without live API checks."""
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["gemini_model"] == settings.gemini_model
    assert data["configured_model"] == settings.gemini_model
    assert data["configured_model"] == "gemini-3.5-flash-lite"
    assert data["model_verified_live"] is False  # Safe distinction


@pytest.mark.asyncio
async def test_mock_responder_still_functions_without_api_key():
    """Verify mock responder functionality remains completely intact without requiring an API key."""
    def sample_responder(history):
        return "click_element", {"element_id": "el-99"}, "Clicking element"

    mock_client = GeminiClient(api_key=None, mock_responder=sample_responder)
    assert mock_client.is_configured() is True
    assert mock_client.model == settings.gemini_model

    tool, args, expl = await mock_client.decide_action([])
    assert tool == "click_element"
    assert args == {"element_id": "el-99"}
    assert expl == "Clicking element"

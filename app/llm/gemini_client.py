"""Gemini LLM client using official google-genai SDK with structured tool calling."""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple
from google.genai import Client, types
from google.genai.errors import APIError

from app.agent.tool_registry import get_gemini_tool_declarations
from app.config import settings
from app.llm.prompts import SYSTEM_INSTRUCTION
from app.logging.setup import get_logger, sanitize_data

logger = get_logger("gemini_client")



class GeminiClientError(Exception):
    """Raised when Gemini API encounters an error."""
    pass


class GeminiClient:
    """Official Google Gen AI client wrapper for browser agent tool selection."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        mock_responder: Optional[Callable[[List[Any]], Tuple[str, Dict[str, Any], str]]] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        # Single source of truth from centralized settings
        self.model = model if model is not None else settings.gemini_model
        self.mock_responder = mock_responder
        self._client: Optional[Client] = None

        if self.api_key and not self.mock_responder:
            try:
                self._client = Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}")

    def is_configured(self) -> bool:
        """Check if Gemini API is configured with a key or mock responder."""
        return bool(self.api_key or self.mock_responder)

    async def decide_action(
        self,
        conversation_history: List[types.Content | Dict[str, Any]],
        timeout_seconds: float = 30.0,
    ) -> Tuple[str, Dict[str, Any], str]:
        """Send prompt and history to Gemini and receive the selected tool, arguments, and explanation.

        Returns:
            (tool_name, arguments_dict, explanation_text)
        """
        # If mock responder is registered (for automated unit & integration testing)
        if self.mock_responder:
            logger.info("Using mock responder for Gemini decision")
            return self.mock_responder(conversation_history)

        if not self._client:
            raise GeminiClientError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in your .env file or environment."
            )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=get_gemini_tool_declarations(),
            temperature=0.1,
        )

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=conversation_history,
                    config=config,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise GeminiClientError(f"Gemini API request timed out after {timeout_seconds}s for model '{self.model}'")
        except APIError as e:
            logger.error(f"Gemini API Error for model '{self.model}': {e.message} (code: {e.code})")
            raise GeminiClientError(f"Gemini API Error (model: {self.model}): {e.message}") from e
        except Exception as e:
            logger.error(f"Unexpected error communicating with Gemini API for model '{self.model}': {e}")
            raise GeminiClientError(f"Gemini client communication failed (model: {self.model}): {e}") from e


        # Extract explanation text and function call
        explanation = (response.text or "").strip()
        function_calls = response.function_calls or []

        if not function_calls:
            # If model answered with text rather than calling a tool, fallback to finish_task or inspect_page
            logger.warning(f"Gemini did not return a tool call. Model text: {explanation[:200]}")
            return "finish_task", {"final_report": explanation or "Task completed based on model reasoning."}, explanation

        selected_call = function_calls[0]
        tool_name = selected_call.name
        raw_args = dict(selected_call.args or {})

        logger.info(
            f"Gemini selected tool: {tool_name}",
            extra={"tool_name": tool_name, "tool_args": sanitize_data(raw_args)},
        )
        return tool_name, raw_args, explanation


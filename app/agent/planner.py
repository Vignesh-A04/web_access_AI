"""Planner module formatting untrusted webpage observations into structured Gemini turns."""

from typing import Any, Dict, List, Optional
from google.genai import types

from app.browser.inspector import PageObservation
from app.llm.prompts import build_user_turn_prompt
from app.logging.setup import get_logger

logger = get_logger("agent_planner")


class AgentPlanner:
    """Manages the dialogue context and turn preparation for the LLM."""

    def __init__(self, instruction: str, task_data: Optional[Dict[str, Any]] = None, max_steps: int = 15):
        self.instruction = instruction
        self.task_data = task_data
        self.max_steps = max_steps
        self.history: List[types.Content] = []

    def prepare_turn_prompt(
        self,
        observation: PageObservation,
        last_result_summary: Optional[str] = None,
        step: int = 1,
    ) -> str:
        """Create the turn prompt combining the user instruction, task data, and clean page observation."""
        obs_text = observation.to_summary_text()
        return build_user_turn_prompt(
            task_instruction=self.instruction,
            task_data=self.task_data,
            page_observation_summary=obs_text,
            last_action_result=last_result_summary,
            step_number=step,
            max_steps=self.max_steps,
        )

    def append_user_message(self, text: str) -> None:
        """Append user observation to history."""
        self.history.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text)],
            )
        )

    def append_model_turn(self, explanation: str, tool_name: str, args: Dict[str, Any]) -> None:
        """Append model response and tool call to history."""
        parts = []
        if explanation:
            parts.append(types.Part.from_text(text=explanation))
        parts.append(
            types.Part.from_function_call(
                name=tool_name,
                args=args,
            )
        )
        self.history.append(types.Content(role="model", parts=parts))

    def append_tool_result(self, tool_name: str, result_dict: Dict[str, Any]) -> None:
        """Append tool execution observation to history."""
        self.history.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_dict},
                    )
                ],
            )
        )

"""Agent orchestrator executing the autonomous browser automation loop with security controls."""

import asyncio
from typing import Optional, Set
from playwright.async_api import BrowserContext, Page

from app.agent.executor import ActionExecutor
from app.agent.planner import AgentPlanner
from app.agent.state import AgentTaskState
from app.agent.tool_registry import validate_tool_arguments
from app.api.schemas import ActionLogItem, TaskStateEnum
from app.browser.inspector import inspect_page, PageObservation
from app.browser.manager import PlaywrightBrowserManager
from app.browser.navigation import navigate_to_url, NavigationSecurityError
from app.config import settings
from app.llm.gemini_client import GeminiClient, GeminiClientError
from app.logging.setup import get_logger
from app.security.action_policy import ActionCategory, classify_action
from app.security.approvals import approval_manager
from app.security.url_policy import validate_url_security

logger = get_logger("agent_orchestrator")


class AgentOrchestrator:
    """Coordinates the end-to-end autonomous reasoning, inspection, security, and browser execution."""

    def __init__(
        self,
        task_state: AgentTaskState,
        browser_manager: PlaywrightBrowserManager,
        gemini_client: GeminiClient,
        allow_local_test: bool = False,
    ):
        self.state = task_state
        self.browser_manager = browser_manager
        self.gemini_client = gemini_client
        self.allow_local_test = allow_local_test
        self.executor = ActionExecutor()
        self.planner = AgentPlanner(
            instruction=task_state.instruction,
            task_data=task_state.task_data,
            max_steps=task_state.max_steps,
        )
        self._cancel_requested = False
        self._approval_event = asyncio.Event()

    def request_cancel(self) -> None:
        """Signal the orchestrator to cancel execution safely."""
        self._cancel_requested = True
        self._approval_event.set()

    def notify_approval_resolved(self) -> None:
        """Signal that a pending approval decision was made."""
        self._approval_event.set()

    async def run(self) -> None:
        """Run the automation task to completion or safe stoppage."""
        task_id = self.state.task_id
        logger.info(f"Starting execution of task {task_id}", extra={"task_id": task_id, "url": self.state.url})

        # 1. URL Security Validation before anything is launched
        domain_set = set(self.state.domain_restrictions) if self.state.domain_restrictions else None
        valid_url, reason = validate_url_security(
            self.state.url,
            allow_local_test=self.allow_local_test,
            domain_allowlist=domain_set,
        )
        if not valid_url:
            self.state.errors.append(f"Security validation failed for initial URL: {reason}")
            self.state.transition_to(TaskStateEnum.FAILED, reason=reason)
            return

        context: Optional[BrowserContext] = None
        page: Optional[Page] = None

        try:
            self.state.transition_to(TaskStateEnum.RUNNING)

            # 2. Launch isolated browser context
            context = await self.browser_manager.create_isolated_context(
                task_id=task_id,
                domain_restrictions=domain_set,
            )
            page = await context.new_page()

            # 3. Initial navigation
            final_url, status = await navigate_to_url(
                page,
                self.state.url,
                allow_local_test=self.allow_local_test,
                domain_restrictions=domain_set,
                timeout_ms=settings.navigation_timeout_ms,
            )
            self.state.current_url = final_url

            # Capture initial screenshot
            screenshot = await self.browser_manager.capture_screenshot(page, task_id)
            if screenshot:
                self.state.screenshot_path = screenshot

            # 4. Orchestration Loop
            last_result_summary: Optional[str] = f"Navigated to {final_url} (HTTP {status})"

            while self.state.step < self.state.max_steps:
                if self._cancel_requested:
                    self.state.transition_to(TaskStateEnum.CANCELLED)
                    logger.info(f"Task {task_id} cancelled by user request.")
                    break

                self.state.step += 1
                current_step = self.state.step

                # Inspect live page
                observation = await inspect_page(page)
                self.state.current_url = observation.url

                # Prepare turn prompt
                turn_prompt = self.planner.prepare_turn_prompt(
                    observation=observation,
                    last_result_summary=last_result_summary,
                    step=current_step,
                )
                self.planner.append_user_message(turn_prompt)

                # Ask Gemini for decision
                try:
                    tool_name, raw_args, explanation = await self.gemini_client.decide_action(
                        self.planner.history
                    )
                except GeminiClientError as e:
                    self.state.errors.append(str(e))
                    self.state.transition_to(TaskStateEnum.FAILED, reason=str(e))
                    break

                # Validate tool arguments against Pydantic schema
                try:
                    validated_args_model = validate_tool_arguments(tool_name, raw_args)
                    validated_args = validated_args_model.model_dump()
                except ValueError as e:
                    error_msg = f"Tool argument validation failed for '{tool_name}': {e}"
                    logger.warning(error_msg)
                    last_result_summary = f"ERROR: {error_msg}. Please provide valid arguments."
                    self.state.add_log(
                        ActionLogItem(
                            step=current_step,
                            tool_name=tool_name,
                            category="INVALID",
                            arguments=raw_args,
                            error=error_msg,
                            explanation=explanation,
                        )
                    )
                    continue

                # Add model turn to planner history
                self.planner.append_model_turn(explanation, tool_name, validated_args)

                # Find element metadata if an element ID was provided
                target_el_meta = None
                if "element_id" in validated_args:
                    target_id = validated_args["element_id"]
                    for el in observation.interactive_elements:
                        if el.get("element_id") == target_id:
                            target_el_meta = el
                            break

                # Classify action (READ_ONLY, REVERSIBLE, CONSEQUENTIAL)
                category, category_reason = classify_action(tool_name, validated_args, target_el_meta)

                # Handle consequential action requiring user approval
                if category == ActionCategory.CONSEQUENTIAL:
                    approval_desc = (
                        f"Action '{tool_name}' on {observation.url} classified as consequential: "
                        f"{category_reason}. Submitted args: {validated_args}"
                    )
                    pending = approval_manager.create_approval_request(
                        task_id=task_id,
                        action_name=tool_name,
                        action_args=validated_args,
                        target_url=observation.url,
                        page_state_hash=observation.state_hash,
                        description=approval_desc,
                    )
                    self.state.pending_approval = pending
                    self.state.transition_to(TaskStateEnum.WAITING_FOR_APPROVAL)
                    logger.info(f"Task {task_id} waiting for user approval of action {tool_name}")

                    # Wait for user approval or cancellation
                    self._approval_event.clear()
                    await self._approval_event.wait()

                    if self._cancel_requested:
                        self.state.transition_to(TaskStateEnum.CANCELLED)
                        break

                    # Check approval status
                    resolved = approval_manager.get_approval(pending.approval_id)
                    if not resolved or resolved.status != "APPROVED":
                        reason = resolved.reason if resolved else "Rejected by user"
                        last_result_summary = f"Consequential action '{tool_name}' was NOT approved by user ({reason}). Choose an alternative safe action or finish."
                        self.state.add_log(
                            ActionLogItem(
                                step=current_step,
                                tool_name=tool_name,
                                category=category.value,
                                arguments=validated_args,
                                error=f"Action rejected: {reason}",
                                explanation=explanation,
                            )
                        )
                        self.state.pending_approval = None
                        self.state.transition_to(TaskStateEnum.RUNNING)
                        continue

                    # Verify state hash before executing approved action
                    fresh_obs = await inspect_page(page)
                    if not pending.is_valid_for_state(fresh_obs.url, fresh_obs.state_hash):
                        approval_manager.expire_approval(pending.approval_id)
                        last_result_summary = "Approval expired because page state changed before execution. Please re-evaluate page."
                        self.state.pending_approval = None
                        self.state.transition_to(TaskStateEnum.RUNNING)
                        continue

                    self.state.pending_approval = None
                    self.state.transition_to(TaskStateEnum.RUNNING)

                # Execute permitted action
                action_result = await self.executor.execute(
                    page=page,
                    tool_name=tool_name,
                    arguments=validated_args,
                    allow_local_test=self.allow_local_test,
                    domain_restrictions=domain_set,
                    timeout_ms=settings.action_timeout_ms,
                )

                # Record log
                log_entry = ActionLogItem(
                    step=current_step,
                    tool_name=tool_name,
                    category=category.value,
                    arguments=validated_args,
                    result=action_result.details if action_result.success else None,
                    error=action_result.error,
                    explanation=explanation,
                )
                self.state.add_log(log_entry)

                # Inform planner of tool result
                self.planner.append_tool_result(
                    tool_name=tool_name,
                    result_dict={
                        "success": action_result.success,
                        "message": action_result.message,
                        "details": action_result.details or {},
                    },
                )
                last_result_summary = action_result.message

                # Update screenshot
                screenshot = await self.browser_manager.capture_screenshot(page, task_id)
                if screenshot:
                    self.state.screenshot_path = screenshot

                # Check if task is finished
                if tool_name == "finish_task" and action_result.success:
                    self.state.final_report = validated_args.get("final_report", "Task completed.")
                    self.state.verified_outcomes = validated_args.get("verified_outcomes", [])
                    self.state.transition_to(TaskStateEnum.COMPLETED)
                    logger.info(f"Task {task_id} completed successfully.")
                    break

            # Handle step limit reached
            if not self.state.is_terminal():
                if self.state.step >= self.state.max_steps:
                    self.state.final_report = (
                        f"Task stopped: reached maximum allowed step limit ({self.state.max_steps} steps)."
                    )
                    self.state.transition_to(TaskStateEnum.COMPLETED)

        except NavigationSecurityError as e:
            self.state.errors.append(str(e))
            self.state.transition_to(TaskStateEnum.FAILED, reason=str(e))
        except Exception as e:
            logger.error(f"Fatal error during task execution {task_id}: {e}", exc_info=True)
            self.state.errors.append(f"Internal execution error: {e}")
            self.state.transition_to(TaskStateEnum.FAILED, reason=str(e))
        finally:
            # Clean up browser context reliably
            if context:
                await self.browser_manager.close_context(context)
            logger.info(f"Cleaned up browser resources for task {task_id}")

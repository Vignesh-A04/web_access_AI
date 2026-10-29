"""Task management service managing background execution, concurrency, and task lifecycle."""

import asyncio
import uuid
from typing import Dict, List, Optional
from pathlib import Path

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import AgentTaskState
from app.api.schemas import ActionLogItem, TaskCreateRequest, TaskStateEnum
from app.browser.manager import PlaywrightBrowserManager
from app.config import settings
from app.llm.gemini_client import GeminiClient
from app.logging.setup import get_logger
from app.security.approvals import approval_manager

logger = get_logger("task_service")


class TaskService:
    """Manages active automation tasks, background workers, and orchestrator instances."""

    def __init__(self, max_concurrency: int = 4):
        self._tasks: Dict[str, AgentTaskState] = {}
        self._orchestrators: Dict[str, AgentOrchestrator] = {}
        self._background_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.browser_manager = PlaywrightBrowserManager(
            headless=settings.browser_headless,
            allow_local_test=settings.allow_local_test_domains,
        )
        self.gemini_client = GeminiClient()

    async def create_task(self, req: TaskCreateRequest) -> AgentTaskState:
        """Create and queue a new automation task."""
        task_id = str(uuid.uuid4())
        headless_mode = req.headless if req.headless is not None else settings.browser_headless

        # Create task state
        state = AgentTaskState(
            task_id=task_id,
            url=req.url,
            instruction=req.instruction,
            task_data=req.task_data,
            domain_restrictions=req.domain_restrictions,
            headless=headless_mode,
            max_steps=settings.max_agent_steps,
        )
        self._tasks[task_id] = state

        # If task requires custom headless mode different from default browser manager,
        # create dedicated browser manager or use default
        b_manager = self.browser_manager
        if headless_mode != settings.browser_headless:
            b_manager = PlaywrightBrowserManager(
                headless=headless_mode,
                allow_local_test=settings.allow_local_test_domains,
            )

        orchestrator = AgentOrchestrator(
            task_state=state,
            browser_manager=b_manager,
            gemini_client=self.gemini_client,
            allow_local_test=settings.allow_local_test_domains,
        )
        self._orchestrators[task_id] = orchestrator

        # Launch in background worker
        bg_task = asyncio.create_task(self._run_task_worker(task_id, orchestrator))
        self._background_tasks[task_id] = bg_task

        return state

    async def _run_task_worker(self, task_id: str, orchestrator: AgentOrchestrator) -> None:
        """Execute the orchestrator within concurrency limits and task timeout."""
        async with self._semaphore:
            try:
                await asyncio.wait_for(
                    orchestrator.run(),
                    timeout=settings.task_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(f"Task {task_id} exceeded maximum timeout of {settings.task_timeout_seconds}s")
                orchestrator.state.errors.append(f"Task exceeded execution timeout of {settings.task_timeout_seconds}s")
                orchestrator.state.transition_to(TaskStateEnum.FAILED, reason="Execution timeout exceeded")
            except Exception as e:
                logger.error(f"Uncaught worker error for task {task_id}: {e}", exc_info=True)
                orchestrator.state.errors.append(f"Internal worker error: {e}")
                orchestrator.state.transition_to(TaskStateEnum.FAILED, reason=str(e))

    def get_task(self, task_id: str) -> Optional[AgentTaskState]:
        """Retrieve task state by ID."""
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running or queued task."""
        orchestrator = self._orchestrators.get(task_id)
        if orchestrator and not orchestrator.state.is_terminal():
            orchestrator.request_cancel()
            return True
        return False

    def approve_action(self, task_id: str, approved: bool, reason: str = "") -> bool:
        """Approve or reject a pending consequential action for a task."""
        pending = approval_manager.get_pending_for_task(task_id)
        if not pending:
            return False

        approval_manager.resolve_approval(pending.approval_id, approved=approved, reason=reason)
        orchestrator = self._orchestrators.get(task_id)
        if orchestrator:
            orchestrator.notify_approval_resolved()
        return True

    def get_task_logs(self, task_id: str) -> List[ActionLogItem]:
        """Get the execution action logs for a task."""
        task = self._tasks.get(task_id)
        return task.action_logs if task else []

    def get_screenshot_path(self, task_id: str) -> Optional[str]:
        """Get local file path to task screenshot if it exists."""
        task = self._tasks.get(task_id)
        if task and task.screenshot_path and Path(task.screenshot_path).exists():
            return task.screenshot_path

        # Check default path
        candidate = Path(settings.screenshot_dir) / f"{task_id}.png"
        if candidate.exists():
            return str(candidate)
        return None

    async def shutdown(self) -> None:
        """Clean shutdown of active tasks and browser resources."""
        for task_id, orchestrator in self._orchestrators.items():
            if not orchestrator.state.is_terminal():
                orchestrator.request_cancel()

        await self.browser_manager.close()


task_service = TaskService()

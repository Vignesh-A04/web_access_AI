"""Agent task state model with explicit state machine transitions and audit history."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.api.schemas import ActionLogItem, PendingApprovalResponse, TaskResponse, TaskStateEnum
from app.security.approvals import PendingApproval


class InvalidStateTransitionError(Exception):
    """Raised when an illegal task state transition is attempted."""
    pass


# Allowed state transitions
VALID_TRANSITIONS = {
    TaskStateEnum.QUEUED: {TaskStateEnum.RUNNING, TaskStateEnum.CANCELLED},
    TaskStateEnum.RUNNING: {
        TaskStateEnum.RUNNING,
        TaskStateEnum.WAITING_FOR_APPROVAL,
        TaskStateEnum.COMPLETED,
        TaskStateEnum.FAILED,
        TaskStateEnum.CANCELLED,
    },
    TaskStateEnum.WAITING_FOR_APPROVAL: {
        TaskStateEnum.RUNNING,
        TaskStateEnum.FAILED,
        TaskStateEnum.CANCELLED,
    },
    TaskStateEnum.COMPLETED: set(),  # Terminal
    TaskStateEnum.FAILED: set(),     # Terminal
    TaskStateEnum.CANCELLED: set(),  # Terminal
}


@dataclass
class AgentTaskState:
    """Complete state snapshot of an automation task."""
    task_id: str
    url: str
    instruction: str
    task_data: Optional[Dict[str, Any]] = None
    domain_restrictions: Optional[List[str]] = None
    headless: Optional[bool] = None
    status: TaskStateEnum = TaskStateEnum.QUEUED
    current_url: Optional[str] = None
    step: int = 0
    max_steps: int = 15
    action_logs: List[ActionLogItem] = field(default_factory=list)
    pending_approval: Optional[PendingApproval] = None
    verified_outcomes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    final_report: Optional[str] = None
    screenshot_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def transition_to(self, new_state: TaskStateEnum, reason: str = "") -> None:
        """Validate and transition to a new task state."""
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_state not in allowed and new_state != self.status:
            raise InvalidStateTransitionError(
                f"Cannot transition task {self.task_id} from {self.status.value} to {new_state.value}"
            )
        self.status = new_state
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if new_state in {TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELLED}:
            self.completed_at = self.updated_at

    def is_terminal(self) -> bool:
        """Check if the task has reached a terminal state."""
        return self.status in {TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELLED}

    def add_log(self, item: ActionLogItem) -> None:
        """Append an action log item and update timestamp."""
        self.action_logs.append(item)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_response(self) -> TaskResponse:
        """Convert state into TaskResponse Pydantic schema."""
        pending_resp = None
        if self.pending_approval and self.pending_approval.is_pending():
            pending_resp = PendingApprovalResponse(
                approval_id=self.pending_approval.approval_id,
                task_id=self.pending_approval.task_id,
                action_name=self.pending_approval.action_name,
                action_args=self.pending_approval.action_args,
                target_url=self.pending_approval.target_url,
                description=self.pending_approval.description,
                created_at=self.pending_approval.created_at,
            )

        return TaskResponse(
            task_id=self.task_id,
            status=self.status,
            url=self.url,
            current_url=self.current_url or self.url,
            instruction=self.instruction,
            task_data=self.task_data,
            created_at=self.created_at,
            updated_at=self.updated_at,
            completed_at=self.completed_at,
            steps_taken=self.step,
            max_steps=self.max_steps,
            pending_approval=pending_resp,
            final_report=self.final_report,
            verified_outcomes=self.verified_outcomes,
            errors=self.errors,
            screenshot_path=self.screenshot_path,
        )

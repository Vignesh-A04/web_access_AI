"""Approval workflow for consequential actions with state binding and expiration."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class PendingApproval:
    """Approval request bound to a specific task, action, and page state."""
    approval_id: str
    task_id: str
    action_name: str
    action_args: Dict[str, Any]
    target_url: str
    page_state_hash: str
    description: str
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXPIRED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    reason: Optional[str] = None

    def is_pending(self) -> bool:
        return self.status == "PENDING"

    def is_valid_for_state(self, current_url: str, current_state_hash: str) -> bool:
        """Verify that the page URL and page state have not drifted since approval request."""
        if not self.is_pending():
            return False
        # Normalize URLs
        url_match = self.target_url.rstrip("/") == current_url.rstrip("/")
        hash_match = self.page_state_hash == current_state_hash
        return url_match and hash_match

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "action_name": self.action_name,
            "action_args": self.action_args,
            "target_url": self.target_url,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "reason": self.reason,
        }


class ApprovalManager:
    """Thread-safe manager for consequential action approvals."""

    def __init__(self):
        self._approvals: Dict[str, PendingApproval] = {}
        self._task_pending: Dict[str, str] = {}  # task_id -> approval_id

    def create_approval_request(
        self,
        task_id: str,
        action_name: str,
        action_args: Dict[str, Any],
        target_url: str,
        page_state_hash: str,
        description: str,
    ) -> PendingApproval:
        """Create a new pending approval bound to page state."""
        approval_id = str(uuid.uuid4())
        approval = PendingApproval(
            approval_id=approval_id,
            task_id=task_id,
            action_name=action_name,
            action_args=action_args,
            target_url=target_url,
            page_state_hash=page_state_hash,
            description=description,
        )
        self._approvals[approval_id] = approval
        self._task_pending[task_id] = approval_id
        return approval

    def get_approval(self, approval_id: str) -> Optional[PendingApproval]:
        return self._approvals.get(approval_id)

    def get_pending_for_task(self, task_id: str) -> Optional[PendingApproval]:
        app_id = self._task_pending.get(task_id)
        if app_id:
            app = self._approvals.get(app_id)
            if app and app.is_pending():
                return app
        return None

    def resolve_approval(self, approval_id: str, approved: bool, reason: str = "") -> Optional[PendingApproval]:
        """Resolve a pending approval to APPROVED or REJECTED."""
        approval = self._approvals.get(approval_id)
        if not approval or not approval.is_pending():
            return None

        approval.status = "APPROVED" if approved else "REJECTED"
        approval.resolved_at = datetime.now(timezone.utc).isoformat()
        approval.reason = reason
        if approval.task_id in self._task_pending:
            del self._task_pending[approval.task_id]
        return approval

    def expire_approval(self, approval_id: str, reason: str = "Page state mutated before approval") -> None:
        """Expire an approval if the underlying state changed."""
        approval = self._approvals.get(approval_id)
        if approval and approval.is_pending():
            approval.status = "EXPIRED"
            approval.resolved_at = datetime.now(timezone.utc).isoformat()
            approval.reason = reason
            if approval.task_id in self._task_pending:
                del self._task_pending[approval.task_id]


approval_manager = ApprovalManager()

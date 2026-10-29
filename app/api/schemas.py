"""Pydantic schemas for API requests, responses, and agent state representation."""

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStateEnum(str, enum.Enum):
    """Explicit lifecycle states of an automation task."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskCreateRequest(BaseModel):
    """Payload for submitting a new AI web automation task."""
    url: str = Field(..., description="Target website URL (HTTP/HTTPS)")
    instruction: str = Field(..., min_length=3, description="Natural language instructions for the agent")
    task_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional user-provided key-value input data")
    domain_restrictions: Optional[List[str]] = Field(default=None, description="Optional list of permitted domains")
    headless: Optional[bool] = Field(default=None, description="Override headless browser mode")


class ApproveActionRequest(BaseModel):
    """Payload for approving or rejecting a pending consequential action."""
    approved: bool = Field(..., description="True to permit execution, False to reject")
    reason: Optional[str] = Field(default=None, description="Optional feedback or rejection reason")


class ActionLogItem(BaseModel):
    """Structured record of an executed tool action."""
    step: int
    tool_name: str
    category: str
    arguments: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    explanation: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PendingApprovalResponse(BaseModel):
    """Information regarding a pending consequential action requiring user approval."""
    approval_id: str
    task_id: str
    action_name: str
    action_args: Dict[str, Any]
    target_url: str
    description: str
    created_at: str


class TaskResponse(BaseModel):
    """Comprehensive status of an automation task."""
    task_id: str
    status: TaskStateEnum
    url: str
    current_url: Optional[str] = None
    instruction: str
    task_data: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    steps_taken: int = 0
    max_steps: int = 15
    pending_approval: Optional[PendingApprovalResponse] = None
    final_report: Optional[str] = None
    verified_outcomes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    screenshot_path: Optional[str] = None


class HealthResponse(BaseModel):
    """Application health status response."""
    status: str
    gemini_configured: bool
    gemini_model: str
    configured_model: str = Field(default="", description="Centralized configured Gemini model ID")
    model_verified_live: bool = Field(
        default=False,
        description="Whether the model has been verified via a live API request (distinguishing config from live verification)"
    )
    playwright_ready: bool
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =========================================================================
# WhatsApp Web Automation Workflow Schemas
# =========================================================================

class WhatsAppStateEnum(str, enum.Enum):
    """States of the WhatsApp Web message composition and verification workflow."""
    QUEUED = "QUEUED"
    CONNECTING_CDP = "CONNECTING_CDP"
    CHECKING_LOGIN = "CHECKING_LOGIN"
    AWAITING_MANUAL_LOGIN = "AWAITING_MANUAL_LOGIN"
    SEARCHING_CONTACT = "SEARCHING_CONTACT"
    AMBIGUOUS_CONTACT = "AMBIGUOUS_CONTACT"
    CONTACT_NOT_FOUND = "CONTACT_NOT_FOUND"
    OPENING_CHAT = "OPENING_CHAT"
    VERIFYING_CHAT_HEADER = "VERIFYING_CHAT_HEADER"
    DRAFTING_MESSAGE = "DRAFTING_MESSAGE"
    WAITING_FOR_SEND_APPROVAL = "WAITING_FOR_SEND_APPROVAL"
    SENDING = "SENDING"
    VERIFYING_SENT = "VERIFYING_SENT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WhatsAppCandidateItem(BaseModel):
    """Candidate contact matching a search query."""
    id: str
    name: str
    subtitle: Optional[str] = ""


class WhatsAppTaskRequest(BaseModel):
    """Payload to initiate a WhatsApp Web message dispatch workflow."""
    contact_name: str = Field(..., min_length=1, description="Exact or search name of the contact")
    message: str = Field(..., min_length=1, description="Message text to draft and send")
    cdp_url: Optional[str] = Field(default=None, description="Chrome DevTools Protocol endpoint (e.g. http://127.0.0.1:9222)")
    target_url: Optional[str] = Field(default=None, description="Override WhatsApp URL (e.g. for testing against local mock site)")


class WhatsAppSelectContactRequest(BaseModel):
    """Payload to select a contact candidate when multiple matches exist."""
    selected_contact: str = Field(..., min_length=1, description="Selected contact name")


class WhatsAppSendConfirmationRequest(BaseModel):
    """Payload to approve or reject sending the drafted message."""
    approved: bool = Field(..., description="True to permit sending, False to cancel")
    reason: Optional[str] = Field(default=None, description="Optional cancellation reason")


class WhatsAppTaskResponse(BaseModel):
    """Comprehensive status model for the WhatsApp Web workflow."""
    task_id: str
    status: WhatsAppStateEnum
    contact_name: str
    selected_contact: Optional[str] = None
    candidates: List[WhatsAppCandidateItem] = Field(default_factory=list)
    verified_header_name: Optional[str] = None
    message_text: str
    screenshot_path: Optional[str] = None
    preview_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    logs: List[str] = Field(default_factory=list)



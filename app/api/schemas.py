"""Pydantic schemas for API requests, responses, and agent state representation."""

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


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


class WhatsAppSendModeEnum(str, enum.Enum):
    """Execution mode for dispatching the WhatsApp message."""
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class WhatsAppCandidateItem(BaseModel):
    """Candidate contact matching a search query."""
    id: str
    name: str
    subtitle: Optional[str] = ""


class WhatsAppTaskRequest(BaseModel):
    """Payload to initiate a WhatsApp Web message dispatch workflow."""
    contact_name: str = Field(..., min_length=1, description="Exact or search name of the contact")
    message: str = Field(..., min_length=1, description="Message text to draft and send")
    send_mode: WhatsAppSendModeEnum = Field(
        default=WhatsAppSendModeEnum.MANUAL,
        description="Sending mode: 'manual' (requires explicit user confirmation before sending) or 'automatic' (sends automatically upon verification)"
    )
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
    send_mode: WhatsAppSendModeEnum = WhatsAppSendModeEnum.MANUAL
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


# =========================================================================
# Incoming-Message Chatbot Schemas
# =========================================================================

class ChatbotMessageStatusEnum(str, enum.Enum):
    """Processing state for an observed incoming WhatsApp message."""
    DETECTED = "DETECTED"
    GENERATING = "GENERATING"
    READY_TO_SEND = "READY_TO_SEND"
    SENDING = "SENDING"
    SENT = "SENT"
    SEND_UNCONFIRMED = "SEND_UNCONFIRMED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ChatbotContactItem(BaseModel):
    """An explicitly allowlisted contact monitored by the chatbot."""
    contact_name: str
    name: Optional[str] = None
    is_paused: bool = False
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: Optional[str] = None

    @model_validator(mode="after")
    def sync_name(self) -> "ChatbotContactItem":
        if not self.name:
            self.name = self.contact_name
        return self


class ChatbotConfigModel(BaseModel):
    """Chatbot runtime configuration and safety thresholds."""
    enabled: bool = False
    auto_reply_enabled: bool = False
    allowed_contacts: List[str] = Field(default_factory=list)
    paused_contacts: List[str] = Field(default_factory=list)
    poll_interval_seconds: float = 3.0
    max_reply_length: int = 160
    max_replies_per_contact_window: int = 5
    rate_limit_window_minutes: int = 15
    allow_group_replies: bool = False
    system_instructions: str = (
        "You are a friendly, helpful assistant on WhatsApp. "
        "Keep your replies natural, polite, and concise (1-2 sentences). "
        "Never make financial commitments, provide legal/medical advice, or disclose private credentials."
    )
    cdp_url: Optional[str] = None
    target_url: Optional[str] = None


class ChatbotConfigUpdateRequest(BaseModel):
    """Payload to update chatbot runtime configuration."""
    enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    poll_interval_seconds: Optional[float] = None
    max_reply_length: Optional[int] = None
    max_replies_per_contact_window: Optional[int] = None
    rate_limit_window_minutes: Optional[int] = None
    allow_group_replies: Optional[bool] = None
    system_instructions: Optional[str] = None
    cdp_url: Optional[str] = None
    target_url: Optional[str] = None


class ChatbotAddContactRequest(BaseModel):
    """Payload to add an allowed contact."""
    contact_name: Optional[str] = Field(default=None, description="Exact contact name saved in WhatsApp")
    name: Optional[str] = Field(default=None, description="Alternative field name for contact name")
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def validate_contact_name(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_name = data.get("contact_name") if data.get("contact_name") is not None else data.get("name")
        if raw_name is None:
            raise ValueError("Field 'contact_name' is required.")
        if not isinstance(raw_name, str):
            raise ValueError("Contact name must be a string.")
        trimmed = raw_name.strip()
        if not trimmed:
            raise ValueError("Contact name cannot be empty or whitespace only.")
        data["contact_name"] = trimmed
        data["name"] = trimmed
        return data


class ChatbotMessageRecord(BaseModel):
    """Record of an observed and processed incoming message."""
    id: str
    fingerprint: str
    contact_name: str
    incoming_text: str
    timestamp_str: str
    status: ChatbotMessageStatusEnum
    reply_text: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    skip_reason: Optional[str] = None
    total_duration_ms: Optional[float] = None
    stage_timings: Optional[Dict[str, float]] = None
    created_at: str
    updated_at: str


class ChatbotStatusResponse(BaseModel):
    """Status summary of the background chatbot monitor."""
    is_running: bool
    config: ChatbotConfigModel
    contacts: List[ChatbotContactItem] = Field(default_factory=list)
    processed_messages_count: int = 0
    recent_messages: List[ChatbotMessageRecord] = Field(default_factory=list)
    last_check_timestamp: Optional[str] = None
    last_error: Optional[str] = None


class ChatbotReconcileRequest(BaseModel):
    """Payload to resolve an uncertain send outcome."""
    confirm_sent: bool = Field(..., description="True if manual inspection confirmed message sent, False to mark skipped")
    notes: Optional[str] = None




"""FastAPI REST routes for tasks, approvals, health checks, and embedded test website."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.api.schemas import (
    ActionLogItem,
    ApproveActionRequest,
    ChatbotAddContactRequest,
    ChatbotConfigModel,
    ChatbotConfigUpdateRequest,
    ChatbotMessageRecord,
    ChatbotReconcileRequest,
    ChatbotResetRateLimitResponse,
    ChatbotStatusResponse,
    HealthResponse,
    TaskCreateRequest,
    TaskResponse,
    WhatsAppCandidateItem,
    WhatsAppSelectContactRequest,
    WhatsAppSendConfirmationRequest,
    WhatsAppStateEnum,
    WhatsAppTaskRequest,
    WhatsAppTaskResponse,
)
from app.config import settings
from app.services.chatbot_reply_service import chatbot_reply_service
from app.services.chatbot_service import chatbot_service
from app.services.chatbot_store import chatbot_store
from app.services.task_service import task_service
from app.services.whatsapp_service import whatsapp_service

api_router = APIRouter()



@api_router.get("/health", response_model=HealthResponse, tags=["System"])
async def get_health():
    """Health check endpoint exposing configuration readiness and timestamp."""
    return HealthResponse(
        status="healthy",
        gemini_configured=task_service.gemini_client.is_configured(),
        gemini_model=settings.gemini_model,
        configured_model=settings.gemini_model,
        model_verified_live=False,  # Explicitly distinguished: config state without expensive live call
        playwright_ready=True,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )



@api_router.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(req: TaskCreateRequest):
    """Create and start a new autonomous web automation task."""
    try:
        task_state = await task_service.create_task(req)
        return task_state.to_response()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create task: {e}",
        )


@api_router.get("/api/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_task(task_id: str):
    """Retrieve the current state, progress, and outcomes of a task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    return task.to_response()


@api_router.post("/api/tasks/{task_id}/approve", tags=["Approvals"])
async def approve_task_action(task_id: str, req: ApproveActionRequest):
    """Approve or reject a pending consequential action for a task."""
    success = task_service.approve_action(task_id, approved=req.approved, reason=req.reason or "")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No pending approval found for task '{task_id}' or already resolved",
        )
    return {
        "status": "success",
        "task_id": task_id,
        "action": "APPROVED" if req.approved else "REJECTED",
    }


@api_router.post("/api/tasks/{task_id}/cancel", tags=["Tasks"])
async def cancel_task(task_id: str):
    """Cancel an active or queued automation task."""
    success = task_service.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_id}' could not be cancelled (may already be finished or not found)",
        )
    return {"status": "success", "message": f"Task '{task_id}' cancellation requested"}


@api_router.get("/api/tasks/{task_id}/logs", response_model=List[ActionLogItem], tags=["Tasks"])
async def get_task_logs(task_id: str):
    """Retrieve detailed action execution logs for a task."""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
    return task.action_logs


@api_router.get("/api/tasks/{task_id}/screenshot", tags=["Observability"])
async def get_task_screenshot(task_id: str):
    """Serve the latest browser screenshot captured during task execution."""
    screenshot_path = task_service.get_screenshot_path(task_id)
    if not screenshot_path or not Path(screenshot_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not available")
    return FileResponse(screenshot_path, media_type="image/png")


# =========================================================================
# WhatsApp Web Automation Workflow Endpoints
# =========================================================================

@api_router.post("/api/whatsapp/tasks", response_model=WhatsAppTaskResponse, status_code=status.HTTP_201_CREATED, tags=["WhatsApp"])
async def create_whatsapp_task(req: WhatsAppTaskRequest):
    """Start an autonomous WhatsApp Web contact message workflow via CDP."""
    try:
        task = await whatsapp_service.start_task(req)
        return task.to_response()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to start WhatsApp task: {e}",
        )


@api_router.get("/api/whatsapp/tasks/{task_id}", response_model=WhatsAppTaskResponse, tags=["WhatsApp"])
async def get_whatsapp_task(task_id: str):
    """Retrieve the current state, progress logs, preview data, and candidates of a WhatsApp task."""
    task = whatsapp_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WhatsApp task '{task_id}' not found")
    return task.to_response()


@api_router.post("/api/whatsapp/tasks/{task_id}/select-contact", response_model=WhatsAppTaskResponse, tags=["WhatsApp"])
async def select_whatsapp_contact(task_id: str, req: WhatsAppSelectContactRequest):
    """Select a specific recipient when contact search yielded multiple candidates."""
    try:
        task = await whatsapp_service.select_contact(task_id, req.selected_contact)
        return task.to_response()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_router.post("/api/whatsapp/tasks/{task_id}/approve-send", response_model=WhatsAppTaskResponse, tags=["WhatsApp"])
async def approve_whatsapp_send(task_id: str, req: WhatsAppSendConfirmationRequest):
    """Explicitly approve or reject sending the drafted WhatsApp message."""
    try:
        task = await whatsapp_service.approve_send(task_id, approved=req.approved, reason=req.reason)
        return task.to_response()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_router.post("/api/whatsapp/tasks/{task_id}/cancel", response_model=WhatsAppTaskResponse, tags=["WhatsApp"])
async def cancel_whatsapp_task(task_id: str):
    """Safely cancel an active WhatsApp task and clear the composer."""
    try:
        task = await whatsapp_service.cancel_task(task_id)
        return task.to_response()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_router.get("/api/whatsapp/tasks/{task_id}/screenshot", tags=["WhatsApp"])
async def get_whatsapp_screenshot(task_id: str):
    """Retrieve the latest screenshot captured during WhatsApp automation."""
    task = whatsapp_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WhatsApp task '{task_id}' not found")
    if not task.screenshot_path or not Path(task.screenshot_path).exists():
        if task.status in {WhatsAppStateEnum.FAILED, WhatsAppStateEnum.CANCELLED}:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screenshot unavailable: task {task.status.value.lower()} before any screenshot was captured."
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screenshot pending: task is currently in state '{task.status.value}'."
        )
    return FileResponse(task.screenshot_path, media_type="image/png")


# =========================================================================
# WhatsApp Incoming Chatbot Endpoints
# =========================================================================

@api_router.get("/api/chatbot/config", response_model=ChatbotConfigModel, tags=["Chatbot"])
async def get_chatbot_config():
    """Retrieve the current chatbot configuration."""
    return chatbot_store.get_config()


@api_router.post("/api/chatbot/config", response_model=ChatbotConfigModel, tags=["Chatbot"])
async def update_chatbot_config(req: ChatbotConfigUpdateRequest):
    """Update runtime chatbot configuration (intervals, auto-reply, rate limits, lengths)."""
    return chatbot_service.update_config(req)


@api_router.get("/api/chatbot/status", response_model=ChatbotStatusResponse, tags=["Chatbot"])
async def get_chatbot_status():
    """Retrieve the current status of the incoming-message chatbot monitor."""
    return chatbot_service.get_status()


@api_router.post("/api/chatbot/start", response_model=ChatbotStatusResponse, tags=["Chatbot"])
async def start_chatbot():
    """Start the background monitor for WhatsApp incoming messages."""
    await chatbot_service.start()
    return chatbot_service.get_status()


@api_router.post("/api/chatbot/stop", response_model=ChatbotStatusResponse, tags=["Chatbot"])
async def stop_chatbot():
    """Stop the background monitor safely and detach from the browser."""
    await chatbot_service.stop()
    return chatbot_service.get_status()


@api_router.post("/api/chatbot/contacts", response_model=ChatbotConfigModel, status_code=status.HTTP_201_CREATED, tags=["Chatbot"])
async def add_chatbot_contact(req: ChatbotAddContactRequest):
    """Add a verified contact name to the explicit allowlist."""
    name = (req.contact_name or req.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact name cannot be empty or whitespace only.",
        )

    existing = chatbot_store.get_contact(name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Contact '{existing.contact_name}' is already in the allowlist.",
        )

    try:
        chatbot_store.add_contact(name, req.notes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return chatbot_store.get_config()


@api_router.delete("/api/chatbot/contacts/{contact_name}", response_model=ChatbotConfigModel, tags=["Chatbot"])
async def remove_chatbot_contact(contact_name: str):
    """Remove a contact from the allowlist."""
    success = chatbot_store.remove_contact(contact_name)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact '{contact_name}' not in allowlist")
    return chatbot_store.get_config()


@api_router.post("/api/chatbot/contacts/{contact_name}/pause", response_model=ChatbotConfigModel, tags=["Chatbot"])
async def pause_chatbot_contact(contact_name: str):
    """Pause automatic monitoring and replies for a specific contact."""
    success = chatbot_store.set_contact_paused(contact_name, paused=True)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact '{contact_name}' not found")
    return chatbot_store.get_config()


@api_router.post("/api/chatbot/contacts/{contact_name}/resume", response_model=ChatbotConfigModel, tags=["Chatbot"])
async def resume_chatbot_contact(contact_name: str):
    """Resume automatic monitoring and replies for a paused contact."""
    success = chatbot_store.set_contact_paused(contact_name, paused=False)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact '{contact_name}' not found")
    return chatbot_store.get_config()


@api_router.post(
    "/api/chatbot/contacts/{contact_name}/reset-rate-limit",
    response_model=ChatbotResetRateLimitResponse,
    tags=["Chatbot"]
)
async def reset_chatbot_contact_rate_limit(contact_name: str):
    """Reset the sent-reply rate-limit history for a specific allowlisted contact."""
    clean_name = contact_name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact name cannot be empty or whitespace only.",
        )

    contact_entry = chatbot_store.get_contact(clean_name)
    if not contact_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact '{clean_name}' not found in allowlist.",
        )

    canonical_name = contact_entry.contact_name
    reset_at = await chatbot_service.reset_contact_rate_limit(canonical_name)
    if not reset_at:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset rate limit for '{canonical_name}'.",
        )

    return ChatbotResetRateLimitResponse(
        status="success",
        contact_name=canonical_name,
        message=f"Rate limit reset successfully for '{canonical_name}'.",
        rate_limit_reset_at=reset_at,
    )



@api_router.get("/api/chatbot/messages", response_model=List[ChatbotMessageRecord], tags=["Chatbot"])
async def list_chatbot_messages(limit: int = 50):
    """List recently observed incoming messages and their processing lifecycle states."""
    return chatbot_store.list_recent_messages(limit=min(limit, 100))


@api_router.get("/api/chatbot/messages/{message_id}", response_model=ChatbotMessageRecord, tags=["Chatbot"])
async def get_chatbot_message(message_id: str):
    """Retrieve detailed lifecycle and audit information for a specific message."""
    msg = chatbot_store.get_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found")
    return msg


@api_router.post("/api/chatbot/messages/{message_id}/reconcile", response_model=ChatbotMessageRecord, tags=["Chatbot"])
async def reconcile_chatbot_message(message_id: str, req: ChatbotReconcileRequest):
    """Reconcile an unconfirmed send (SEND_UNCONFIRMED) safely without blind resending."""
    reconciled = chatbot_store.reconcile_unconfirmed_message(
        message_id=message_id,
        confirmed=req.confirmed,
        notes=req.notes
    )
    if not reconciled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found")
    return reconciled


@api_router.post("/api/chatbot/messages/{message_id}/send", response_model=ChatbotMessageRecord, tags=["Chatbot"])
async def send_approved_chatbot_message(message_id: str):
    """Explicitly approve and send a single READY_TO_SEND candidate reply proposal."""
    updated = await chatbot_service.send_approved_reply(message_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found")
    return updated


@api_router.post("/api/chatbot/messages/{message_id}/dismiss", response_model=ChatbotMessageRecord, tags=["Chatbot"])
async def dismiss_chatbot_message(message_id: str):
    """Explicitly dismiss a candidate reply proposal without sending it."""
    dismissed = chatbot_store.dismiss_message(message_id)
    if not dismissed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found")
    return dismissed



def generate_mock_whatsapp_html(mode: Optional[str] = None) -> str:
    """Generate mock WhatsApp Web DOM for automated testing and offline verification."""
    if mode == "qr":
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WhatsApp Web</title>
    <style>
        body { margin:0; padding:0; background:#111b21; color:#e9edef; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; }
        .card { background:#202c33; padding:40px; border-radius:12px; text-align:center; max-width:400px; box-shadow:0 8px 24px rgba(0,0,0,0.5); }
        .qr-placeholder { width:220px; height:220px; background:#fff; margin:20px auto; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#000; font-weight:bold; font-size:14px; text-align:center; padding:10px; }
        h2 { color:#00a884; margin-bottom:10px; }
        p { color:#8696a0; font-size:14px; line-height:1.5; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Use WhatsApp on your computer</h2>
        <div data-testid="qrcode" class="qr-placeholder">Scan this QR code with WhatsApp on your phone</div>
        <p>1. Open WhatsApp on your phone<br>2. Tap Linked devices<br>3. Scan this QR code</p>
    </div>
</body>
</html>"""

    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WhatsApp Web Mock</title>
    <style>
        * { box-sizing:border-box; margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
        body { display:flex; height:100vh; background:#111b21; color:#e9edef; }
        #side { width:360px; min-width:360px; border-right:1px solid #222e35; display:flex; flex-direction:column; background:#111b21; }
        .side-header { padding:14px 16px; background:#202c33; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid #222e35; }
        .side-header h2 { font-size:18px; color:#e9edef; }
        .search-container { padding:10px 14px; background:#111b21; border-bottom:1px solid #222e35; }
        .search-box { width:100%; min-height:36px; padding:8px 12px; background:#202c33; border:1px solid #334155; border-radius:8px; color:#e9edef; font-size:14px; outline:none; }
        .search-box[contenteditable]:empty:before { content: attr(placeholder); color: #8696a0; }
        #chat-list { flex:1; overflow-y:auto; }
        .contact-item { display:flex; align-items:center; padding:12px 16px; cursor:pointer; border-bottom:1px solid #182229; transition:background 0.15s; }
        .contact-item:hover, .contact-item.active { background:#202c33; }
        .avatar { width:44px; height:44px; border-radius:50%; background:#00a884; display:flex; align-items:center; justify-content:center; font-weight:bold; margin-right:12px; color:#111b21; flex-shrink:0; }
        .contact-info { flex:1; min-width:0; }
        .contact-name { font-weight:500; font-size:15px; color:#e9edef; display:flex; justify-content:space-between; }
        .last-msg { font-size:13px; color:#8696a0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:3px; }
        #main { flex:1; display:flex; flex-direction:column; background:#0b141a; }
        #main header { height:62px; background:#202c33; padding:10px 18px; display:flex; align-items:center; border-bottom:1px solid #222e35; gap:12px; }
        .header-avatar { width:38px; height:38px; border-radius:50%; background:#00a884; display:flex; align-items:center; justify-content:center; font-weight:bold; color:#111b21; }
        .chat-title { font-weight:600; font-size:16px; color:#e9edef; }
        #conversation { flex:1; padding:24px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; background-color:#0b141a; background-image:radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px); background-size:24px 24px; }
        .message-bubble { max-width:65%; padding:10px 14px; border-radius:8px; font-size:14.5px; line-height:1.45; word-break:break-word; }
        .message-in { align-self:flex-start; background:#202c33; color:#e9edef; border-top-left-radius:2px; }
        .message-out { align-self:flex-end; background:#005c4b; color:#e9edef; border-top-right-radius:2px; }
        #main footer { background:#202c33; padding:12px 18px; display:flex; align-items:center; gap:12px; border-top:1px solid #222e35; }
        #message-composer { flex:1; background:#2a3942; border-radius:8px; padding:10px 14px; min-height:42px; color:#e9edef; outline:none; font-size:14.5px; line-height:1.4; border:1px solid #3b4a54; }
        #message-composer[contenteditable]:empty:before { content: attr(placeholder); color: #8696a0; }
        #send-button { background:#00a884; border:none; border-radius:50%; width:42px; height:42px; display:flex; align-items:center; justify-content:center; cursor:pointer; color:#111b21; font-weight:bold; font-size:18px; flex-shrink:0; transition:background 0.2s; }
        #send-button:hover { background:#02906f; }
    </style>
</head>
<body>
    <div id="side" data-testid="chat-list">
        <div class="side-header">
            <h2>Chats</h2>
        </div>
        <div class="search-container">
            <div id="search-input" contenteditable="true" role="textbox" data-tab="3" data-testid="chat-list-search" class="search-box" placeholder="Search or start new chat"></div>
        </div>
        <div id="chat-list" data-testid="chat-list-container">
            <div class="contact-item" data-testid="cell-frame-container" role="listitem" onclick="openChat('Alice Smith')">
                <div class="avatar">AS</div>
                <div class="contact-info">
                    <div class="contact-name" data-testid="cell-frame-title"><span title="Alice Smith">Alice Smith</span></div>
                    <div class="last-msg" data-testid="last-msg-status">Let's connect soon!</div>
                </div>
            </div>
            <div class="contact-item" data-testid="cell-frame-container" role="listitem" onclick="openChat('Bob Jones')">
                <div class="avatar">BJ</div>
                <div class="contact-info">
                    <div class="contact-name" data-testid="cell-frame-title"><span title="Bob Jones">Bob Jones</span></div>
                    <div class="last-msg" data-testid="last-msg-status">The report is ready.</div>
                </div>
            </div>
            <div class="contact-item" data-testid="cell-frame-container" role="listitem" onclick="openChat('Charlie Brown')">
                <div class="avatar">CB</div>
                <div class="contact-info">
                    <div class="contact-name" data-testid="cell-frame-title"><span title="Charlie Brown">Charlie Brown</span></div>
                    <div class="last-msg" data-testid="last-msg-status">Let's catch up tomorrow afternoon.</div>
                </div>
            </div>
            <div class="contact-item" data-testid="cell-frame-container" role="listitem" onclick="openChat('Charlie Davis')">
                <div class="avatar">CD</div>
                <div class="contact-info">
                    <div class="contact-name" data-testid="cell-frame-title"><span title="Charlie Davis">Charlie Davis</span></div>
                    <div class="last-msg" data-testid="last-msg-status">Project roadmap has been updated.</div>
                </div>
            </div>
            <div class="contact-item" data-testid="cell-frame-container" role="listitem" onclick="openChat('David Wilson')">
                <div class="avatar">DW</div>
                <div class="contact-info">
                    <div class="contact-name" data-testid="cell-frame-title"><span title="David Wilson">David Wilson</span></div>
                    <div class="last-msg" data-testid="last-msg-status">Thanks for the update!</div>
                </div>
            </div>
        </div>
    </div>

    <div id="main">
        <header>
            <div class="header-avatar" id="header-avatar">?</div>
            <div data-testid="conversation-info-header-chat-title">
                <span id="chat-header-name" class="chat-title" dir="auto">Select a chat</span>
            </div>
        </header>

        <div id="conversation" data-testid="conversation-panel-wrapper">
            <div class="message-bubble message-in">
                <span>Welcome to WhatsApp Web simulation. Select a contact on the left to begin messaging.</span>
            </div>
        </div>

        <footer>
            <div id="message-composer" contenteditable="true" role="textbox" data-tab="10" data-testid="conversation-compose-box-input" placeholder="Type a message"></div>
            <button id="send-button" aria-label="Send" data-testid="compose-btn-send" onclick="sendMessage()">
                <span data-icon="send">&#10148;</span>
            </button>
        </footer>
    </div>

    <script>
        const searchBox = document.getElementById('search-input');
        function filterContacts() {
            const query = (searchBox.innerText || searchBox.textContent || '').trim().toLowerCase();
            const items = document.querySelectorAll('.contact-item');
            items.forEach(item => {
                const titleSpan = item.querySelector('.contact-name span');
                const name = (titleSpan ? (titleSpan.getAttribute('title') || titleSpan.innerText) : '').toLowerCase();
                if (!query || name.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        }
        searchBox.addEventListener('input', filterContacts);
        searchBox.addEventListener('keyup', filterContacts);

        function openChat(name) {
            document.getElementById('chat-header-name').innerText = name;
            const initials = name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
            document.getElementById('header-avatar').innerText = initials;
            document.querySelectorAll('.contact-item').forEach(el => el.classList.remove('active'));
            const clicked = Array.from(document.querySelectorAll('.contact-item')).find(el => {
                return (el.querySelector('.contact-name span')?.innerText || '') === name;
            });
            if (clicked) clicked.classList.add('active');
        }

        function sendMessage() {
            const composer = document.getElementById('message-composer');
            const text = (composer.innerText || composer.textContent || '').trim();
            if (!text) return;
            const conv = document.getElementById('conversation');
            const bubble = document.createElement('div');
            bubble.className = 'message-bubble message-out';
            bubble.setAttribute('data-testid', 'msg-container');
            const inner = document.createElement('div');
            inner.className = 'message-out';
            inner.innerText = text;
            bubble.appendChild(inner);
            conv.appendChild(bubble);
            composer.innerText = '';
            conv.scrollTop = conv.scrollHeight;
        }

        document.getElementById('message-composer').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>"""


@api_router.get("/test-whatsapp", response_class=HTMLResponse, tags=["Test Website"])
async def serve_test_whatsapp(mode: Optional[str] = None):
    """Local WhatsApp Web simulation page for automated testing without live network or real WhatsApp credentials."""
    return HTMLResponse(content=generate_mock_whatsapp_html(mode=mode))


# =========================================================================
# Embedded Local Test Website Endpoints (For Automated Verification & E2E)
# =========================================================================

test_site_router = APIRouter(prefix="/test-site", tags=["Test Website"])


@test_site_router.get("/whatsapp", response_class=HTMLResponse)
async def serve_test_site_whatsapp(mode: Optional[str] = None):
    """Prefix alias for WhatsApp Web simulation."""
    return HTMLResponse(content=generate_mock_whatsapp_html(mode=mode))



@test_site_router.get("", response_class=HTMLResponse)
async def serve_test_site():
    """Local test website page with forms, inputs, dropdown, checkbox, and table."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>AI Automation Agent Demo Test Site</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; max-width: 900px; margin: 0 auto; }
            .card { background: #1e293b; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
            h1 { color: #38bdf8; margin-top: 0; }
            h2 { color: #94a3b8; font-size: 1.25rem; }
            label { display: block; margin-top: 1rem; font-weight: 500; color: #cbd5e1; }
            input[type="text"], input[type="email"], select, textarea { width: 100%; padding: 0.6rem; margin-top: 0.3rem; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #f8fafc; box-sizing: border-box; }
            .checkbox-group { margin-top: 1.2rem; display: flex; align-items: center; gap: 0.5rem; }
            button { background: #0284c7; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 6px; font-weight: 600; cursor: pointer; margin-top: 1.5rem; }
            button:hover { background: #0369a1; }
            table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
            th, td { border: 1px solid #334155; padding: 0.75rem; text-align: left; }
            th { background: #0f172a; color: #38bdf8; }
            .badge { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
            .badge-active { background: #065f46; color: #34d399; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Authorized Demo Registration & Task Form</h1>
            <p>This is an authorized local test website designed to verify generic web automation workflows.</p>

            <form id="registration-form" action="/test-site/submit" method="POST">
                <label for="name-input">Full Name</label>
                <input type="text" id="name-input" name="name" placeholder="Enter your full name" required>

                <label for="email-input">Email Address</label>
                <input type="email" id="email-input" name="email" placeholder="name@example.com" required>

                <label for="account-type-select">Account Tier</label>
                <select id="account-type-select" name="account_type">
                    <option value="personal">Personal Plan</option>
                    <option value="business">Business Plan</option>
                    <option value="enterprise">Enterprise Plan</option>
                </select>

                <label for="message-input">Task / Project Requirements</label>
                <textarea id="message-input" name="message" rows="4" placeholder="Describe requirements..."></textarea>

                <div class="checkbox-group">
                    <input type="checkbox" id="terms-checkbox" name="agree_terms" value="yes">
                    <label for="terms-checkbox" style="margin-top:0;">I accept the Terms and Conditions</label>
                </div>

                <button type="submit" id="submit-button">Submit Registration</button>
            </form>
        </div>

        <div class="card">
            <h2>Inventory & System Status Table</h2>
            <table id="inventory-table">
                <thead>
                    <tr><th>Item ID</th><th>Item Name</th><th>Category</th><th>Stock</th><th>Status</th></tr>
                </thead>
                <tbody>
                    <tr><td>SKU-101</td><td>AI Server Node A</td><td>Hardware</td><td>15</td><td><span class="badge badge-active">Available</span></td></tr>
                    <tr><td>SKU-102</td><td>Playwright Worker Container</td><td>Software</td><td>42</td><td><span class="badge badge-active">Active</span></td></tr>
                    <tr><td>SKU-103</td><td>Gemini Flash Accelerator</td><td>Cloud Service</td><td>Unlimited</td><td><span class="badge badge-active">Online</span></td></tr>
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@test_site_router.post("/submit", response_class=HTMLResponse)
async def submit_test_site(
    name: str = Form(...),
    email: str = Form(...),
    account_type: str = Form("personal"),
    message: str = Form(""),
    agree_terms: Optional[str] = Form(None),
):
    """Handle consequential form submission and return success verification page."""
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Registration Confirmed - AI Automation Test Site</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; max-width: 800px; margin: 0 auto; }}
            .card {{ background: #1e293b; border-radius: 12px; padding: 2rem; border: 1px solid #10b981; }}
            h1 {{ color: #34d399; margin-top: 0; }}
            .summary-box {{ background: #0f172a; padding: 1.5rem; border-radius: 8px; margin-top: 1rem; border: 1px solid #334155; }}
            a {{ color: #38bdf8; text-decoration: none; display: inline-block; margin-top: 1rem; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1 id="success-heading">Registration Confirmed!</h1>
            <p id="confirmation-text">Thank you, <strong>{name}</strong>. Your registration for the <strong>{account_type.capitalize()}</strong> plan has been processed successfully.</p>
            <div class="summary-box">
                <p><strong>Registered Email:</strong> <span id="confirmed-email">{email}</span></p>
                <p><strong>Submitted Message:</strong> <span id="confirmed-message">{message}</span></p>
                <p><strong>Terms Accepted:</strong> <span id="confirmed-terms">{'Yes' if agree_terms else 'No'}</span></p>
            </div>
            <a href="/test-site" id="back-link">&larr; Back to Test Form</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

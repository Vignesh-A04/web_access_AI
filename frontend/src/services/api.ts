import {
  HealthResponse,
  TaskCreateRequest,
  TaskResponse,
  ActionLogItem,
  WhatsAppTaskRequest,
  WhatsAppTaskResponse,
  ChatbotConfig,
  ChatbotConfigUpdateRequest,
  ChatbotMessageRecord,
  ChatbotResetRateLimitResponse,
  ChatbotStatusResponse,
} from '../types';

const API_BASE = ''; // Uses Vite proxy in development, or relative in production

export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function submitTask(payload: TaskCreateRequest): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to submit task');
  }
  return res.json();
}

export async function fetchTask(taskId: string): Promise<TaskResponse> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Failed to fetch task: ${res.statusText}`);
  return res.json();
}

export async function fetchTaskLogs(taskId: string): Promise<ActionLogItem[]> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/logs`);
  if (!res.ok) throw new Error(`Failed to fetch task logs: ${res.statusText}`);
  return res.json();
}

export async function sendApproval(taskId: string, approved: boolean, reason?: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to process approval');
  }
}

export async function cancelTask(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to cancel task');
  }
}

export function getScreenshotUrl(taskId: string): string {
  return `${API_BASE}/api/tasks/${taskId}/screenshot?t=${Date.now()}`;
}

// =========================================================================
// WhatsApp Automation API Methods
// =========================================================================

export async function startWhatsAppTask(payload: WhatsAppTaskRequest): Promise<WhatsAppTaskResponse> {
  const res = await fetch(`${API_BASE}/api/whatsapp/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start WhatsApp task');
  }
  return res.json();
}

export async function fetchWhatsAppTask(taskId: string): Promise<WhatsAppTaskResponse> {
  const res = await fetch(`${API_BASE}/api/whatsapp/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Failed to fetch WhatsApp task: ${res.statusText}`);
  return res.json();
}

export async function selectWhatsAppContact(taskId: string, selectedContact: string): Promise<WhatsAppTaskResponse> {
  const res = await fetch(`${API_BASE}/api/whatsapp/tasks/${taskId}/select-contact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_contact: selectedContact }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to select contact');
  }
  return res.json();
}

export async function confirmWhatsAppSend(taskId: string, approved: boolean, reason?: string): Promise<WhatsAppTaskResponse> {
  const res = await fetch(`${API_BASE}/api/whatsapp/tasks/${taskId}/approve-send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to confirm send');
  }
  return res.json();
}

export async function cancelWhatsAppTask(taskId: string): Promise<WhatsAppTaskResponse> {
  const res = await fetch(`${API_BASE}/api/whatsapp/tasks/${taskId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to cancel WhatsApp task');
  }
  return res.json();
}

export function getWhatsAppScreenshotUrl(taskId: string): string {
  return `${API_BASE}/api/whatsapp/tasks/${taskId}/screenshot?t=${Date.now()}`;
}

// =========================================================================
// WhatsApp Incoming Chatbot API Methods
// =========================================================================

export async function fetchChatbotStatus(): Promise<ChatbotStatusResponse> {
  const res = await fetch(`${API_BASE}/api/chatbot/status`);
  if (!res.ok) throw new Error(`Failed to fetch chatbot status: ${res.statusText}`);
  return res.json();
}

export async function updateChatbotConfig(payload: ChatbotConfigUpdateRequest): Promise<ChatbotConfig> {
  const res = await fetch(`${API_BASE}/api/chatbot/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to update chatbot config');
  }
  return res.json();
}

export async function startChatbot(): Promise<ChatbotStatusResponse> {
  const res = await fetch(`${API_BASE}/api/chatbot/start`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start chatbot');
  }
  return res.json();
}

export async function stopChatbot(): Promise<ChatbotStatusResponse> {
  const res = await fetch(`${API_BASE}/api/chatbot/stop`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to stop chatbot');
  }
  return res.json();
}

function formatApiError(errData: any, fallbackText: string): string {
  if (!errData) return fallbackText;
  if (typeof errData.detail === 'string') return errData.detail;
  if (Array.isArray(errData.detail) && errData.detail.length > 0) {
    return errData.detail
      .map((d: any) => {
        if (typeof d === 'string') return d;
        if (d && typeof d.msg === 'string') return d.msg;
        return JSON.stringify(d);
      })
      .join(', ');
  }
  if (typeof errData.message === 'string') return errData.message;
  return fallbackText;
}

export async function addChatbotContact(contactName: string, notes?: string): Promise<ChatbotConfig> {
  const trimmed = contactName.trim();
  const res = await fetch(`${API_BASE}/api/chatbot/contacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contact_name: trimmed,
      name: trimmed,
      notes: notes || undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err, `Failed to add contact (${res.status})`));
  }
  return res.json();
}

export async function removeChatbotContact(contactName: string): Promise<ChatbotConfig> {
  const res = await fetch(`${API_BASE}/api/chatbot/contacts/${encodeURIComponent(contactName.trim())}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err, `Failed to remove contact (${res.status})`));
  }
  return res.json();
}

export async function pauseChatbotContact(contactName: string): Promise<ChatbotConfig> {
  const res = await fetch(`${API_BASE}/api/chatbot/contacts/${encodeURIComponent(contactName.trim())}/pause`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err, `Failed to pause contact (${res.status})`));
  }
  return res.json();
}

export async function resumeChatbotContact(contactName: string): Promise<ChatbotConfig> {
  const res = await fetch(`${API_BASE}/api/chatbot/contacts/${encodeURIComponent(contactName.trim())}/resume`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err, `Failed to resume contact (${res.status})`));
  }
  return res.json();
}

export async function resetChatbotContactRateLimit(contactName: string): Promise<ChatbotResetRateLimitResponse> {
  const res = await fetch(`${API_BASE}/api/chatbot/contacts/${encodeURIComponent(contactName.trim())}/reset-rate-limit`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err, `Failed to reset rate limit (${res.status})`));
  }
  return res.json();
}

export async function fetchChatbotMessages(limit: number = 50): Promise<ChatbotMessageRecord[]> {
  const res = await fetch(`${API_BASE}/api/chatbot/messages?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch chatbot messages: ${res.statusText}`);
  return res.json();
}

export async function reconcileChatbotMessage(messageId: string, confirmed: boolean, notes?: string): Promise<ChatbotMessageRecord> {
  const res = await fetch(`${API_BASE}/api/chatbot/messages/${messageId}/reconcile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed, notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to reconcile message');
  }
  return res.json();
}

export async function approveChatbotMessage(messageId: string): Promise<ChatbotMessageRecord> {
  const res = await fetch(`${API_BASE}/api/chatbot/messages/${messageId}/send`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to approve and send message');
  }
  return res.json();
}

export async function dismissChatbotMessage(messageId: string): Promise<ChatbotMessageRecord> {
  const res = await fetch(`${API_BASE}/api/chatbot/messages/${messageId}/dismiss`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to dismiss message proposal');
  }
  return res.json();
}



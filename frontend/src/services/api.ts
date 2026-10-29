import {
  HealthResponse,
  TaskCreateRequest,
  TaskResponse,
  ActionLogItem,
  WhatsAppTaskRequest,
  WhatsAppTaskResponse,
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


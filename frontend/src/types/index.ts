export type TaskState = 
  | 'QUEUED' 
  | 'RUNNING' 
  | 'WAITING_FOR_APPROVAL' 
  | 'COMPLETED' 
  | 'FAILED' 
  | 'CANCELLED';

export interface ActionLogItem {
  step: number;
  tool_name: string;
  category: string;
  arguments: Record<string, any>;
  result?: Record<string, any> | null;
  error?: string | null;
  explanation: string;
  timestamp: string;
}

export interface PendingApproval {
  approval_id: string;
  task_id: string;
  action_name: string;
  action_args: Record<string, any>;
  target_url: string;
  description: string;
  created_at: string;
}

export interface TaskResponse {
  task_id: string;
  status: TaskState;
  url: string;
  current_url?: string;
  instruction: string;
  task_data?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  steps_taken: number;
  max_steps: number;
  pending_approval?: PendingApproval | null;
  final_report?: string | null;
  verified_outcomes: string[];
  errors: string[];
  screenshot_path?: string | null;
}

export interface TaskCreateRequest {
  url: string;
  instruction: string;
  task_data?: Record<string, any>;
  domain_restrictions?: string[];
  headless?: boolean;
}

export interface HealthResponse {
  status: string;
  gemini_configured: boolean;
  gemini_model: string;
  configured_model?: string;
  model_verified_live?: boolean;
  playwright_ready: boolean;
  timestamp: string;
}

// =========================================================================
// WhatsApp Web Automation Types
// =========================================================================

export type WhatsAppState =
  | 'QUEUED'
  | 'CONNECTING_CDP'
  | 'CHECKING_LOGIN'
  | 'AWAITING_MANUAL_LOGIN'
  | 'SEARCHING_CONTACT'
  | 'AMBIGUOUS_CONTACT'
  | 'CONTACT_NOT_FOUND'
  | 'OPENING_CHAT'
  | 'VERIFYING_CHAT_HEADER'
  | 'DRAFTING_MESSAGE'
  | 'WAITING_FOR_SEND_APPROVAL'
  | 'SENDING'
  | 'VERIFYING_SENT'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface WhatsAppCandidateItem {
  id: string;
  name: string;
  subtitle?: string;
}

export type WhatsAppSendMode = 'manual' | 'automatic';

export interface WhatsAppTaskRequest {
  contact_name: string;
  message: string;
  send_mode?: WhatsAppSendMode;
  cdp_url?: string;
  target_url?: string;
}

export interface WhatsAppTaskResponse {
  task_id: string;
  status: WhatsAppState;
  send_mode?: WhatsAppSendMode;
  contact_name: string;
  selected_contact?: string | null;
  candidates: WhatsAppCandidateItem[];
  verified_header_name?: string | null;
  message_text: string;
  screenshot_path?: string | null;
  preview_data?: {
    recipient: string;
    message: string;
    chat_header: string;
    char_count: number;
  } | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  logs: string[];
}

// =========================================================================
// WhatsApp Incoming Chatbot Types
// =========================================================================

export type ChatbotMessageStatus =
  | 'DETECTED'
  | 'GENERATING'
  | 'READY_TO_SEND'
  | 'SENDING'
  | 'SENT'
  | 'SEND_UNCONFIRMED'
  | 'SKIPPED'
  | 'FAILED';

export interface ChatbotContactItem {
  contact_name: string;
  name?: string;
  is_paused: boolean;
  added_at: string;
  notes?: string | null;
}

export interface ChatbotAddContactRequest {
  contact_name: string;
  name?: string;
  notes?: string | null;
}

export interface ChatbotConfig {
  enabled: boolean;
  auto_reply_enabled: boolean;
  poll_interval_seconds: number;
  max_reply_length: number;
  allowed_contacts: string[];
  max_replies_per_window: number;
  rate_limit_window_minutes: number;
  system_prompt_extra: string;
  cdp_url: string;
  whatsapp_url: string;
}

export interface ChatbotConfigUpdateRequest {
  enabled?: boolean;
  auto_reply_enabled?: boolean;
  poll_interval_seconds?: number;
  max_reply_length?: number;
  max_replies_per_window?: number;
  rate_limit_window_minutes?: number;
  system_prompt_extra?: string;
}

export interface ChatbotMessageRecord {
  id: string;
  fingerprint: string;
  contact_name: string;
  incoming_text: string;
  timestamp_str: string;
  status: ChatbotMessageStatus;
  reply_text?: string | null;
  intent?: string | null;
  confidence?: number | null;
  skip_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatbotStatusResponse {
  is_running: boolean;
  config: ChatbotConfig;
  contacts: ChatbotContactItem[];
  processed_messages_count: number;
  recent_messages: ChatbotMessageRecord[];
  last_check_timestamp?: string | null;
  last_error?: string | null;
}




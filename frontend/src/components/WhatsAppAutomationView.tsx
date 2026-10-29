import React, { useEffect, useState } from 'react';
import {
  MessageSquare,
  Send,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ExternalLink,
  RefreshCw,
  Search,
  Check,
  ChevronDown,
  ChevronUp,
  UserCheck,
  Eye,
  Camera,
  Zap,
} from 'lucide-react';
import {
  WhatsAppCandidateItem,
  WhatsAppSendMode,
  WhatsAppState,
  WhatsAppTaskRequest,
  WhatsAppTaskResponse,
} from '../types';
import { getWhatsAppScreenshotUrl } from '../services/api';


interface WhatsAppAutomationViewProps {
  task: WhatsAppTaskResponse | null;
  isLoading: boolean;
  onStartTask: (req: WhatsAppTaskRequest) => Promise<void>;
  onSelectCandidate: (selectedContact: string) => Promise<void>;
  onConfirmSend: (approved: boolean, reason?: string) => Promise<void>;
  onCancelTask: () => Promise<void>;
  onResetTask: () => void;
}

const STEP_ORDER: { state: WhatsAppState; label: string }[] = [
  { state: 'CONNECTING_CDP', label: 'Connect Chrome CDP' },
  { state: 'CHECKING_LOGIN', label: 'Verify Login Session' },
  { state: 'SEARCHING_CONTACT', label: 'Search Contact' },
  { state: 'VERIFYING_CHAT_HEADER', label: 'Verify Chat Header' },
  { state: 'DRAFTING_MESSAGE', label: 'Draft in Composer' },
  { state: 'WAITING_FOR_SEND_APPROVAL', label: 'Confirm & Send' },
  { state: 'VERIFYING_SENT', label: 'Verify Sent Message' },
];

export const WhatsAppAutomationView: React.FC<WhatsAppAutomationViewProps> = ({
  task,
  isLoading,
  onStartTask,
  onSelectCandidate,
  onConfirmSend,
  onCancelTask,
  onResetTask,
}) => {
  // Form state
  const [contactName, setContactName] = useState('');
  const [message, setMessage] = useState('');
  const [sendMode, setSendMode] = useState<WhatsAppSendMode>('manual');
  const [cdpUrl, setCdpUrl] = useState('http://127.0.0.1:9222');
  const [targetUrl, setTargetUrl] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [imgKey, setImgKey] = useState(Date.now());

  useEffect(() => {
    if (task?.screenshot_path) {
      setImgKey(Date.now());
    }
  }, [task?.screenshot_path]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contactName.trim() || !message.trim()) return;

    await onStartTask({
      contact_name: contactName.trim(),
      message: message.trim(),
      send_mode: sendMode,
      cdp_url: cdpUrl.trim() || undefined,
      target_url: targetUrl.trim() || undefined,
    });
    // Automatic mode requires explicit user selection for each task and is never enabled implicitly
    setSendMode('manual');
  };

  const handleApplyMockPreset = () => {
    setContactName('Alice Smith');
    setMessage('Hello! This is a verified test message sent through the WhatsApp automation workflow.');
    setTargetUrl('http://127.0.0.1:8000/test-whatsapp');
    setShowAdvanced(true);
  };

  const handleSelectCandidateWrapper = async (candidateName: string) => {
    setIsActionLoading(true);
    try {
      await onSelectCandidate(candidateName);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleConfirmSendWrapper = async (approved: boolean) => {
    setIsActionLoading(true);
    try {
      await onConfirmSend(approved);
      setImgKey(Date.now());
    } finally {
      setIsActionLoading(false);
    }
  };

  // Compute status step index
  const getStepStatus = (stepState: WhatsAppState) => {
    if (!task) return 'pending';

    // If task is in automatic mode, WAITING_FOR_SEND_APPROVAL is satisfied once sending or verified
    if (task.send_mode === 'automatic' && stepState === 'WAITING_FOR_SEND_APPROVAL') {
      if (['SENDING', 'VERIFYING_SENT', 'COMPLETED'].includes(task.status)) return 'completed';
    }

    const stateOrder = [
      'QUEUED',
      'CONNECTING_CDP',
      'CHECKING_LOGIN',
      'SEARCHING_CONTACT',
      'AMBIGUOUS_CONTACT',
      'OPENING_CHAT',
      'VERIFYING_CHAT_HEADER',
      'DRAFTING_MESSAGE',
      'WAITING_FOR_SEND_APPROVAL',
      'SENDING',
      'VERIFYING_SENT',
      'COMPLETED',
    ];

    const currentIndex = stateOrder.indexOf(task.status);
    const targetIndex = stateOrder.indexOf(stepState);

    if (task.status === 'COMPLETED') return 'completed';
    if (task.status === 'FAILED' || task.status === 'CANCELLED') {
      if (currentIndex >= targetIndex) return 'failed';
      return 'pending';
    }
    if (currentIndex > targetIndex) return 'completed';
    if (currentIndex === targetIndex) return 'active';
    return 'pending';
  };

  // Render Form (when task is null)
  if (!task) {
    return (
      <div style={{ maxWidth: '860px', margin: '2rem auto', padding: '0 1.5rem' }}>
        {/* WhatsApp Brand Banner */}
        <div
          className="glass-panel"
          style={{
            padding: '2rem',
            marginBottom: '2rem',
            background: 'linear-gradient(135deg, rgba(0, 168, 132, 0.12) 0%, rgba(17, 24, 39, 0.9) 100%)',
            borderColor: 'rgba(0, 168, 132, 0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #00a884 0%, #008f6f 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 20px rgba(0, 168, 132, 0.4)',
              }}
            >
              <MessageSquare size={26} color="#ffffff" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f8fafc' }}>
                WhatsApp Web Contact Messenger
              </h2>
              <p style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                Automated recipient search, header verification, safe message drafting, and explicit send approval
              </p>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '1rem',
              marginTop: '1.5rem',
            }}
          >
            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                padding: '1rem',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#38bdf8', marginBottom: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                <ShieldCheck size={16} /> Direct CDP Session
              </div>
              <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                Connects to your active Chrome browser via CDP. Never asks for or logs your WhatsApp credentials, QR codes, or private chat histories.
              </p>
            </div>

            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                padding: '1rem',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#34d399', marginBottom: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                <UserCheck size={16} /> Recipient Verification
              </div>
              <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                Searches for the contact, resolves ambiguity if multiple match, and strictly verifies the chat title matches before composing.
              </p>
            </div>

            <div
              style={{
                background: 'rgba(15, 23, 42, 0.6)',
                padding: '1rem',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.06)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fbbf24', marginBottom: '0.35rem', fontWeight: 600, fontSize: '0.85rem' }}>
                <Eye size={16} /> Safety Send Preview
              </div>
              <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                Drafts the message in the composer without sending. Displays a live preview and requires your explicit Send confirmation in the UI.
              </p>
            </div>
          </div>
        </div>

        {/* Message Creation Form */}
        <div className="glass-panel" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#f8fafc' }}>
              Compose WhatsApp Message
            </h3>
            <button
              type="button"
              onClick={handleApplyMockPreset}
              style={{
                background: 'rgba(0, 168, 132, 0.15)',
                color: '#34d399',
                border: '1px solid rgba(0, 168, 132, 0.3)',
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: 500,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <ExternalLink size={13} /> Test with Mock Page
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.5rem' }}>
                Contact / Recipient Name <span style={{ color: '#f43f5e' }}>*</span>
              </label>
              <div style={{ position: 'relative' }}>
                <Search
                  size={18}
                  color="#64748b"
                  style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                />
                <input
                  type="text"
                  required
                  placeholder="e.g. Alice Smith or John Doe"
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem 1rem 0.75rem 2.5rem',
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: '#f8fafc',
                    fontSize: '0.95rem',
                    outline: 'none',
                  }}
                />
              </div>
              <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.4rem' }}>
                Enter the exact contact name or phone name as saved in your WhatsApp chat list.
              </p>
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1' }}>
                  Message Text <span style={{ color: '#f43f5e' }}>*</span>
                </label>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  {message.length} characters
                </span>
              </div>
              <textarea
                required
                rows={4}
                placeholder="Type your message here. It will be drafted into the WhatsApp Web composer for your preview before any send action occurs."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.75rem 1rem',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  color: '#f8fafc',
                  fontSize: '0.95rem',
                  outline: 'none',
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Sending Mode Selector (Manual vs Automatic) */}
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.6rem' }}>
                Sending Mode <span style={{ color: '#f43f5e' }}>*</span>
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
                {/* Option 1: Manual Approval (Default) */}
                <div
                  onClick={() => setSendMode('manual')}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '8px',
                    border: `2px solid ${sendMode === 'manual' ? '#00a884' : 'var(--border-subtle)'}`,
                    background: sendMode === 'manual' ? 'rgba(0, 168, 132, 0.12)' : 'var(--bg-input)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.35rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.9rem', color: sendMode === 'manual' ? '#34d399' : '#f8fafc' }}>
                      <ShieldCheck size={18} />
                      <span>Manual Approval</span>
                    </div>
                    <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.1)', color: '#94a3b8' }}>
                      Default
                    </span>
                  </div>
                  <p style={{ fontSize: '0.76rem', color: '#94a3b8', margin: 0, lineHeight: 1.4 }}>
                    Finds & verifies recipient, drafts in composer, and shows preview. Requires your explicit confirmation before sending.
                  </p>
                </div>

                {/* Option 2: Automatic Send */}
                <div
                  onClick={() => setSendMode('automatic')}
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '8px',
                    border: `2px solid ${sendMode === 'automatic' ? '#f59e0b' : 'var(--border-subtle)'}`,
                    background: sendMode === 'automatic' ? 'rgba(245, 158, 11, 0.12)' : 'var(--bg-input)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.35rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.9rem', color: sendMode === 'automatic' ? '#fbbf24' : '#f8fafc' }}>
                      <Zap size={16} />
                      <span>Automatic Send</span>
                    </div>
                    {sendMode === 'automatic' && (
                      <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem', borderRadius: '4px', background: 'rgba(245, 158, 11, 0.25)', color: '#fbbf24', fontWeight: 700 }}>
                        Active
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '0.76rem', color: '#94a3b8', margin: 0, lineHeight: 1.4 }}>
                    Verifies recipient, fills composer, clicks Send automatically, and verifies outgoing message bubble.
                  </p>
                </div>
              </div>

              {sendMode === 'automatic' && (
                <div
                  style={{
                    marginTop: '0.65rem',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    background: 'rgba(245, 158, 11, 0.08)',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    color: '#fbbf24',
                    fontSize: '0.78rem',
                  }}
                >
                  <AlertTriangle size={16} style={{ flexShrink: 0 }} />
                  <span>
                    <strong>Automatic Mode Selected:</strong> The workflow will automatically click Send once the recipient header is verified. Requires explicit selection per task.
                  </span>
                </div>
              )}
            </div>

            {/* Collapsible Advanced CDP Settings */}
            <div style={{ marginBottom: '1.5rem' }}>
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#94a3b8',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: 0,
                }}
              >
                {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                <span>Advanced Chrome CDP & Target Settings</span>
              </button>

              {showAdvanced && (
                <div
                  style={{
                    marginTop: '0.75rem',
                    padding: '1rem',
                    background: 'rgba(15, 23, 42, 0.7)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '1rem',
                  }}
                >
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '0.35rem' }}>
                      Chrome DevTools Protocol (CDP) Endpoint
                    </label>
                    <input
                      type="text"
                      value={cdpUrl}
                      onChange={(e) => setCdpUrl(e.target.value)}
                      placeholder="http://127.0.0.1:9222"
                      style={{
                        width: '100%',
                        padding: '0.5rem 0.75rem',
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '0.85rem',
                      }}
                    />
                    <p style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.25rem' }}>
                      Launch Chrome with: <code>chrome.exe --remote-debugging-port=9222</code>
                    </p>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '0.35rem' }}>
                      WhatsApp Web URL (or Local Test Mock)
                    </label>
                    <input
                      type="text"
                      value={targetUrl}
                      onChange={(e) => setTargetUrl(e.target.value)}
                      placeholder="https://web.whatsapp.com (default)"
                      style={{
                        width: '100%',
                        padding: '0.5rem 0.75rem',
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '0.85rem',
                      }}
                    />
                    <p style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.25rem' }}>
                      Leave empty to use official WhatsApp Web, or point to <code>http://127.0.0.1:8000/test-whatsapp</code> for offline simulation.
                    </p>
                  </div>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={isLoading || !contactName.trim() || !message.trim()}
              className="btn-whatsapp"
              style={{
                width: '100%',
                padding: '0.85rem',
                borderRadius: '8px',
                fontSize: '1rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                background: sendMode === 'automatic' ? 'linear-gradient(135deg, #d97706 0%, #b45309 100%)' : undefined,
                boxShadow: sendMode === 'automatic' ? '0 0 20px rgba(245, 158, 11, 0.4)' : undefined,
              }}
            >
              {sendMode === 'automatic' ? <Zap size={18} /> : <Send size={18} />}
              {isLoading
                ? 'Starting Workflow...'
                : sendMode === 'automatic'
                ? 'Verify Recipient & Send Automatically'
                : 'Find Contact & Draft Message'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Active Task Execution View
  const isTerminal = ['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.status);
  const screenshotUrl = getWhatsAppScreenshotUrl(task.task_id) + `&v=${imgKey}`;

  return (
    <div style={{ maxWidth: '1100px', margin: '1.5rem auto', padding: '0 1.5rem' }}>
      {/* Task Header & Action Bar */}
      <div
        className="glass-panel"
        style={{
          padding: '1.25rem 1.75rem',
          marginBottom: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '10px',
              background: '#00a884',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <MessageSquare size={22} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc' }}>
                Target: {task.verified_header_name || task.selected_contact || task.contact_name}
              </h2>
              <span
                style={{
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '6px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  background:
                    task.status === 'COMPLETED'
                      ? 'rgba(16, 185, 129, 0.2)'
                      : task.status === 'FAILED'
                      ? 'rgba(244, 63, 94, 0.2)'
                      : task.status === 'WAITING_FOR_SEND_APPROVAL'
                      ? 'rgba(245, 158, 11, 0.25)'
                      : 'rgba(0, 168, 132, 0.2)',
                  color:
                    task.status === 'COMPLETED'
                      ? '#34d399'
                      : task.status === 'FAILED'
                      ? '#fb7185'
                      : task.status === 'WAITING_FOR_SEND_APPROVAL'
                      ? '#fbbf24'
                      : '#00a884',
                  border: '1px solid currentColor',
                }}
              >
                {task.status.replace(/_/g, ' ')}
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  padding: '0.2rem 0.55rem',
                  borderRadius: '6px',
                  fontWeight: 600,
                  background: task.send_mode === 'automatic' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(56, 189, 248, 0.15)',
                  color: task.send_mode === 'automatic' ? '#fbbf24' : '#38bdf8',
                  border: task.send_mode === 'automatic' ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(56, 189, 248, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                }}
              >
                {task.send_mode === 'automatic' ? (
                  <>
                    <Zap size={12} /> Auto-Send Mode
                  </>
                ) : (
                  <>
                    <ShieldCheck size={12} /> Manual Approval Mode
                  </>
                )}
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
              Task ID: <code>{task.task_id.substring(0, 8)}...</code> &bull; Started: {new Date(task.created_at).toLocaleTimeString()}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {!isTerminal && (
            <button
              onClick={onCancelTask}
              disabled={isActionLoading}
              style={{
                background: 'rgba(244, 63, 94, 0.15)',
                color: '#fb7185',
                border: '1px solid rgba(244, 63, 94, 0.3)',
                padding: '0.5rem 1rem',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel Workflow
            </button>
          )}

          {isTerminal && (
            <button
              onClick={onResetTask}
              className="btn-whatsapp"
              style={{
                padding: '0.5rem 1.25rem',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              + Send Another Message
            </button>
          )}
        </div>
      </div>

      {/* Workflow Stepper */}
      <div
        className="glass-panel"
        style={{
          padding: '1.25rem 1.5rem',
          marginBottom: '1.5rem',
          overflowX: 'auto',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minWidth: '700px' }}>
          {STEP_ORDER.map((step, idx) => {
            const st = getStepStatus(step.state);
            return (
              <React.Fragment key={step.state}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.35rem' }}>
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      background:
                        st === 'completed'
                          ? '#00a884'
                          : st === 'active'
                          ? '#0284c7'
                          : st === 'failed'
                          ? '#f43f5e'
                          : '#1e293b',
                      color: st === 'pending' ? '#64748b' : '#ffffff',
                      boxShadow:
                        st === 'active'
                          ? '0 0 12px rgba(2, 132, 199, 0.6)'
                          : st === 'completed'
                          ? '0 0 10px rgba(0, 168, 132, 0.4)'
                          : 'none',
                      transition: 'all 0.3s ease',
                    }}
                  >
                    {st === 'completed' ? (
                      <Check size={16} />
                    ) : st === 'failed' ? (
                      <XCircle size={16} />
                    ) : (
                      idx + 1
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: st === 'active' ? 700 : 500,
                      color: st === 'active' ? '#38bdf8' : st === 'completed' ? '#34d399' : '#64748b',
                      textAlign: 'center',
                      maxWidth: '85px',
                    }}
                  >
                    {step.label}
                  </span>
                </div>
                {idx < STEP_ORDER.length - 1 && (
                  <div
                    style={{
                      flex: 1,
                      height: '2px',
                      background: st === 'completed' ? '#00a884' : '#334155',
                      margin: '0 0.5rem',
                      marginBottom: '1.25rem',
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Main Interactive Stage Panels */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Left Column: Interactive State Card */}
        <div>
          {/* 1. Login Required Screen */}
          {task.status === 'AWAITING_MANUAL_LOGIN' && (
            <div
              className="glass-panel"
              style={{
                padding: '1.75rem',
                border: '1px solid rgba(245, 158, 11, 0.5)',
                background: 'rgba(245, 158, 11, 0.08)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fbbf24', marginBottom: '1rem' }}>
                <AlertTriangle size={24} />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>WhatsApp Web Login Required</h3>
              </div>
              <p style={{ fontSize: '0.88rem', color: '#cbd5e1', lineHeight: 1.5, marginBottom: '1rem' }}>
                WhatsApp Web is not currently authenticated in your Chrome browser window.
              </p>
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  padding: '1rem',
                  borderRadius: '8px',
                  fontSize: '0.82rem',
                  color: '#94a3b8',
                  marginBottom: '1.25rem',
                  lineHeight: 1.6,
                }}
              >
                1. Switch to your Chrome browser window.<br />
                2. Scan the displayed QR code with your phone.<br />
                3. Once your chat list appears, start a new message workflow.
              </div>
              <button
                onClick={onResetTask}
                className="btn-primary"
                style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}
              >
                Try Again
              </button>
            </div>
          )}

          {/* 2. Ambiguous Contact Resolution Screen */}
          {task.status === 'AMBIGUOUS_CONTACT' && (
            <div
              className="glass-panel"
              style={{
                padding: '1.75rem',
                border: '1px solid rgba(14, 165, 233, 0.4)',
                background: 'rgba(14, 165, 233, 0.08)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#38bdf8', marginBottom: '0.75rem' }}>
                <Search size={22} />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Select Intended Contact</h3>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#cbd5e1', marginBottom: '1.25rem' }}>
                Multiple contacts matched <strong>"{task.contact_name}"</strong>. Please select the correct recipient:
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
                {task.candidates.map((candidate: WhatsAppCandidateItem) => (
                  <button
                    key={candidate.id}
                    onClick={() => handleSelectCandidateWrapper(candidate.name)}
                    disabled={isActionLoading}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.85rem 1.25rem',
                      background: 'rgba(15, 23, 42, 0.8)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#00a884')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)')}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#38bdf8' }}>
                        {candidate.name}
                      </div>
                      {candidate.subtitle && (
                        <div style={{ fontSize: '0.78rem', color: '#8696a0', marginTop: '0.2rem' }}>
                          {candidate.subtitle}
                        </div>
                      )}
                    </div>
                    <span
                      style={{
                        fontSize: '0.8rem',
                        color: '#00a884',
                        background: 'rgba(0, 168, 132, 0.15)',
                        padding: '0.3rem 0.6rem',
                        borderRadius: '4px',
                        fontWeight: 600,
                      }}
                    >
                      Select
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Automatic Send In-Progress Card */}
          {task.send_mode === 'automatic' && !isTerminal && task.status !== 'AWAITING_MANUAL_LOGIN' && task.status !== 'AMBIGUOUS_CONTACT' && (
            <div
              className="glass-panel"
              style={{
                padding: '1.75rem',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(15, 23, 42, 0.95) 100%)',
                boxShadow: '0 0 20px rgba(245, 158, 11, 0.15)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fbbf24', marginBottom: '0.75rem' }}>
                <Zap size={24} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Automatic Send Active</h3>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#cbd5e1', marginBottom: '1.25rem', lineHeight: 1.5 }}>
                {task.status === 'SENDING'
                  ? 'Recipient header verified. Clicking Send button automatically...'
                  : task.status === 'VERIFYING_SENT'
                  ? 'Message sent. Verifying outgoing bubble in conversation...'
                  : task.status === 'DRAFTING_MESSAGE'
                  ? 'Drafting message into composer. Will send automatically once drafted...'
                  : 'Searching & verifying recipient. Once confirmed, will send automatically without prompting.'}
              </p>

              {/* Target & Header Badge */}
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  padding: '1rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  marginBottom: '1rem',
                }}
              >
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#94a3b8', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Target Recipient
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <UserCheck size={18} color="#fbbf24" />
                  <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc' }}>
                    {task.verified_header_name || task.selected_contact || task.contact_name}
                  </span>
                  {task.verified_header_name && (
                    <span style={{ fontSize: '0.7rem', background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24', padding: '0.15rem 0.4rem', borderRadius: '4px', fontWeight: 600 }}>
                      VERIFIED
                    </span>
                  )}
                </div>
              </div>

              {/* Message Preview */}
              <div
                style={{
                  background: 'rgba(11, 20, 26, 0.95)',
                  padding: '1rem 1.25rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                }}
              >
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#fbbf24', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Message Text ({task.message_text.length} chars)
                </div>
                <div
                  style={{
                    fontSize: '0.95rem',
                    color: '#e9edef',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.5,
                    fontStyle: 'italic',
                  }}
                >
                  "{task.message_text}"
                </div>
              </div>
            </div>
          )}

          {/* 3. Waiting for Send Approval Screen (CORE REQUIREMENT) */}
          {task.status === 'WAITING_FOR_SEND_APPROVAL' && (
            <div
              className="glass-panel"
              style={{
                padding: '1.75rem',
                border: '1px solid rgba(0, 168, 132, 0.5)',
                background: 'linear-gradient(135deg, rgba(0, 168, 132, 0.12) 0%, rgba(15, 23, 42, 0.95) 100%)',
                boxShadow: '0 0 25px rgba(0, 168, 132, 0.2)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#00a884', marginBottom: '0.75rem' }}>
                <ShieldCheck size={24} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Explicit Send Approval Required</h3>
              </div>
              <p style={{ fontSize: '0.85rem', color: '#cbd5e1', marginBottom: '1.25rem' }}>
                The message has been drafted into the WhatsApp Web composer. <strong>It has NOT been sent.</strong> Verify the details below and confirm:
              </p>

              {/* Recipient Verification Badge */}
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  padding: '1rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  marginBottom: '1rem',
                }}
              >
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#94a3b8', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Verified Recipient Header
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <UserCheck size={18} color="#34d399" />
                  <span style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc' }}>
                    {task.verified_header_name || task.selected_contact || task.contact_name}
                  </span>
                  <span style={{ fontSize: '0.7rem', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '0.15rem 0.4rem', borderRadius: '4px', fontWeight: 600 }}>
                    MATCH CONFIRMED
                  </span>
                </div>
              </div>

              {/* Exact Drafted Message Preview */}
              <div
                style={{
                  background: 'rgba(11, 20, 26, 0.95)',
                  padding: '1rem 1.25rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(0, 168, 132, 0.3)',
                  marginBottom: '1.5rem',
                }}
              >
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#00a884', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Exact Message in Composer ({task.message_text.length} chars)
                </div>
                <div
                  style={{
                    fontSize: '0.95rem',
                    color: '#e9edef',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.5,
                    fontStyle: 'italic',
                  }}
                >
                  "{task.message_text}"
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '1rem' }}>
                <button
                  onClick={() => handleConfirmSendWrapper(true)}
                  disabled={isActionLoading}
                  className="btn-whatsapp"
                  style={{
                    flex: 1,
                    padding: '0.85rem',
                    borderRadius: '8px',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <Send size={16} />
                  {isActionLoading ? 'Sending...' : 'Confirm & Send Once'}
                </button>

                <button
                  onClick={() => handleConfirmSendWrapper(false)}
                  disabled={isActionLoading}
                  style={{
                    padding: '0.85rem 1.25rem',
                    borderRadius: '8px',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    background: 'rgba(244, 63, 94, 0.15)',
                    color: '#fb7185',
                    border: '1px solid rgba(244, 63, 94, 0.3)',
                    cursor: 'pointer',
                  }}
                >
                  Cancel Send
                </button>
              </div>
            </div>
          )}

          {/* 4. Completed Success Card */}
          {task.status === 'COMPLETED' && (
            <div
              className="glass-panel"
              style={{
                padding: '2rem',
                border: '1px solid rgba(16, 185, 129, 0.5)',
                background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.95) 100%)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#34d399', marginBottom: '1rem' }}>
                <CheckCircle2 size={26} />
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Message Successfully Sent & Verified</h3>
              </div>
              <p style={{ fontSize: '0.88rem', color: '#cbd5e1', lineHeight: 1.5, marginBottom: '1.25rem' }}>
                The message to <strong>{task.verified_header_name || task.selected_contact}</strong> was submitted and verified appearing as an outgoing chat bubble.
              </p>
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  padding: '1rem',
                  borderRadius: '8px',
                  fontSize: '0.82rem',
                  color: '#94a3b8',
                  marginBottom: '1.5rem',
                }}
              >
                <div><strong>Recipient:</strong> {task.verified_header_name}</div>
                <div><strong>Message:</strong> {task.message_text}</div>
                <div><strong>Completed:</strong> {new Date(task.completed_at || task.updated_at).toLocaleTimeString()}</div>
              </div>
              <button
                onClick={onResetTask}
                className="btn-whatsapp"
                style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}
              >
                + Send Another Message
              </button>
            </div>
          )}

          {/* 5. Failed Card */}
          {(task.status === 'FAILED' || task.status === 'CONTACT_NOT_FOUND') && (
            <div
              className="glass-panel"
              style={{
                padding: '1.75rem',
                border: '1px solid rgba(244, 63, 94, 0.5)',
                background: 'rgba(244, 63, 94, 0.08)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fb7185', marginBottom: '0.75rem' }}>
                <XCircle size={24} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Workflow Did Not Complete</h3>
              </div>
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.8)',
                  padding: '1rem',
                  borderRadius: '8px',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                  border: '1px solid rgba(244, 63, 94, 0.25)',
                  marginBottom: '1.25rem',
                  lineHeight: 1.5,
                }}
              >
                {task.error || 'An error occurred during WhatsApp Web automation.'}
              </div>
              <button
                onClick={onResetTask}
                className="btn-primary"
                style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}
              >
                Start Over
              </button>
            </div>
          )}

          {/* 6. In-Progress Spinner */}
          {!['AWAITING_MANUAL_LOGIN', 'AMBIGUOUS_CONTACT', 'WAITING_FOR_SEND_APPROVAL', 'COMPLETED', 'FAILED', 'CONTACT_NOT_FOUND', 'CANCELLED'].includes(task.status) && (
            <div
              className="glass-panel"
              style={{
                padding: '2.5rem 1.75rem',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <RefreshCw
                size={36}
                color="#00a884"
                style={{ animation: 'spin 2s linear infinite', marginBottom: '1.25rem' }}
              />
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
                Executing WhatsApp Workflow
              </h3>
              <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '320px' }}>
                {task.status === 'CONNECTING_CDP' && 'Connecting to Chrome via DevTools Protocol...'}
                {task.status === 'CHECKING_LOGIN' && 'Verifying WhatsApp Web authenticated session...'}
                {task.status === 'SEARCHING_CONTACT' && `Searching chat list for '${task.contact_name}'...`}
                {task.status === 'OPENING_CHAT' && 'Opening conversation window...'}
                {task.status === 'VERIFYING_CHAT_HEADER' && 'Verifying chat title matches recipient...'}
                {task.status === 'DRAFTING_MESSAGE' && 'Drafting message into composer...'}
                {task.status === 'SENDING' && 'Clicking Send button once...'}
                {task.status === 'VERIFYING_SENT' && 'Verifying outgoing bubble in conversation history...'}
              </p>
            </div>
          )}
        </div>

        {/* Right Column: Browser Screenshot View */}
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Eye size={18} color="#00a884" />
              <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#f8fafc' }}>
                Browser View
              </h4>
            </div>
            {task.screenshot_path && (
              <button
                onClick={() => setImgKey(Date.now())}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  fontSize: '0.75rem',
                }}
              >
                <RefreshCw size={12} /> Refresh
              </button>
            )}
          </div>

          <div
            style={{
              flex: 1,
              minHeight: '260px',
              background: '#090d16',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {task.screenshot_path ? (
              <img
                src={screenshotUrl}
                alt="WhatsApp Browser View"
                style={{
                  width: '100%',
                  height: 'auto',
                  maxHeight: '360px',
                  objectFit: 'contain',
                  display: 'block',
                }}
              />
            ) : isTerminal ? (
              <div
                style={{
                  color: '#94a3b8',
                  fontSize: '0.82rem',
                  textAlign: 'center',
                  padding: '2rem',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <Camera size={32} color="#64748b" style={{ opacity: 0.5 }} />
                <span>
                  {task.status === 'FAILED'
                    ? 'No browser screenshot captured. The workflow failed before a browser view could be captured.'
                    : 'Workflow ended without capturing an updated screenshot.'}
                </span>
              </div>
            ) : (
              <div
                style={{
                  color: '#64748b',
                  fontSize: '0.8rem',
                  textAlign: 'center',
                  padding: '2rem',
                }}
              >
                Connecting to Chrome session... screenshot will appear once connected.
              </div>
            )}
          </div>
        </div>
      </div>


      {/* Execution Logs Card */}
      <div className="glass-panel" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <Clock size={16} color="#94a3b8" />
          <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc' }}>
            Workflow Verification Logs ({task.logs.length} steps)
          </h4>
        </div>

        <div
          style={{
            maxHeight: '220px',
            overflowY: 'auto',
            background: '#0c1220',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid var(--border-subtle)',
            fontSize: '0.8rem',
            fontFamily: 'var(--font-mono)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.4rem',
          }}
        >
          {task.logs.length === 0 ? (
            <span style={{ color: '#64748b' }}>No logs recorded yet.</span>
          ) : (
            task.logs.map((logLine, index) => (
              <div
                key={index}
                style={{
                  color:
                    logLine.includes('error') || logLine.includes('failed') || logLine.includes('Mismatch')
                      ? '#fb7185'
                      : logLine.includes('success') || logLine.includes('verified') || logLine.includes('confirmed')
                      ? '#34d399'
                      : logLine.includes('Waiting for')
                      ? '#fbbf24'
                      : '#cbd5e1',
                  lineHeight: 1.4,
                }}
              >
                {logLine}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect, useCallback } from 'react';
import {
  Play,
  Square,
  AlertOctagon,
  RefreshCw,
  UserPlus,
  Trash2,
  PauseCircle,
  PlayCircle,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Shield,
  Bot,
  MessageSquare,
  Sparkles,
  Sliders,
  Check,
  X,
  ExternalLink,
  Send,
  Zap,
  RotateCcw,
} from 'lucide-react';
import {
  ChatbotConfig,
  ChatbotContactItem,
  ChatbotMessageRecord,
  ChatbotMessageStatus,
  ChatbotStatusResponse,
  HealthResponse,
} from '../types';
import {
  fetchChatbotStatus,
  updateChatbotConfig,
  startChatbot,
  stopChatbot,
  addChatbotContact,
  removeChatbotContact,
  pauseChatbotContact,
  resumeChatbotContact,
  resetChatbotContactRateLimit,
  reconcileChatbotMessage,
  approveChatbotMessage,
  dismissChatbotMessage,
} from '../services/api';

interface WhatsAppChatbotViewProps {
  health: HealthResponse | null;
}

export const WhatsAppChatbotView: React.FC<WhatsAppChatbotViewProps> = ({ health }) => {
  const [statusData, setStatusData] = useState<ChatbotStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form states
  const [newContactName, setNewContactName] = useState('');
  const [newContactNotes, setNewContactNotes] = useState('');

  // Settings editing state
  const [configEditing, setConfigEditing] = useState<Partial<ChatbotConfig>>({});
  const [configSaving, setConfigSaving] = useState(false);

  // Reconciliation modal state
  const [reconcilingMsg, setReconcilingMsg] = useState<ChatbotMessageRecord | null>(null);
  const [reconcileNotes, setReconcileNotes] = useState('');

  // Reset rate limit modal state
  const [resetContactModal, setResetContactModal] = useState<string | null>(null);

  const loadStatus = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const data = await fetchChatbotStatus();
      setStatusData(data);
      if (!configSaving) {
        const maxReplies = data.config.max_replies_per_contact_window ?? data.config.max_replies_per_window ?? 5;
        setConfigEditing({
          auto_reply_enabled: data.config.auto_reply_enabled,
          poll_interval_seconds: data.config.poll_interval_seconds,
          max_reply_length: data.config.max_reply_length,
          max_replies_per_contact_window: maxReplies,
          max_replies_per_window: maxReplies,
          rate_limit_window_minutes: data.config.rate_limit_window_minutes,
        });
      }
    } catch (err: any) {
      if (!quiet) setErrorMsg(err.message || 'Failed to fetch chatbot status');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [configSaving]);

  // Initial load and adaptive status polling
  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    const isBusy = statusData?.is_running || (statusData?.recent_messages || []).some(m => m.status === 'GENERATING' || m.status === 'SENDING');
    const pollInterval = isBusy ? 1500 : 4000;
    const interval = setInterval(() => {
      loadStatus(true);
    }, pollInterval);
    return () => clearInterval(interval);
  }, [loadStatus, statusData?.is_running, statusData?.recent_messages]);

  // Temporary flash message clearer
  useEffect(() => {
    if (successMsg) {
      const timer = setTimeout(() => setSuccessMsg(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [successMsg]);

  const handleStart = async () => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const res = await startChatbot();
      setStatusData(res);
      setSuccessMsg('Chatbot monitor started successfully.');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to start chatbot');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const res = await stopChatbot();
      setStatusData(res);
      setSuccessMsg('Chatbot monitor stopped successfully.');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to stop chatbot');
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleAutoReply = async () => {
    if (!statusData) return;
    const nextVal = !statusData.config.auto_reply_enabled;
    setActionLoading(true);
    try {
      const updated = await updateChatbotConfig({ auto_reply_enabled: nextVal });
      setStatusData(prev => prev ? { ...prev, config: updated } : null);
      setSuccessMsg(nextVal ? 'Automatic replies ENABLED' : 'Automatic replies DISABLED');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to toggle auto-reply');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setConfigSaving(true);
    setErrorMsg(null);
    try {
      const maxReplies = configEditing.max_replies_per_contact_window ?? configEditing.max_replies_per_window ?? 5;
      const updated = await updateChatbotConfig({
        poll_interval_seconds: configEditing.poll_interval_seconds,
        max_reply_length: configEditing.max_reply_length,
        max_replies_per_contact_window: maxReplies,
        max_replies_per_window: maxReplies,
        rate_limit_window_minutes: configEditing.rate_limit_window_minutes,
      });
      setStatusData(prev => prev ? { ...prev, config: updated } : null);
      setSuccessMsg('Safety & Rate Limit configuration saved.');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save configuration');
    } finally {
      setConfigSaving(false);
    }
  };

  const handleAddContact = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newContactName.trim();
    if (!trimmed) {
      setErrorMsg("Contact name cannot be empty or whitespace only.");
      return;
    }
    setActionLoading(true);
    setErrorMsg(null);
    try {
      await addChatbotContact(trimmed, newContactNotes.trim() || undefined);
      setNewContactName('');
      setNewContactNotes('');
      await loadStatus(true);
      setSuccessMsg(`Added '${trimmed}' to allowlist.`);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to add contact');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveContact = async (name: string) => {
    if (!window.confirm(`Are you sure you want to remove '${name}' from the allowlist?`)) return;
    setActionLoading(true);
    try {
      await removeChatbotContact(name);
      await loadStatus(true);
      setSuccessMsg(`Removed '${name}' from allowlist.`);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to remove contact');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTogglePauseContact = async (name: string, isPaused: boolean) => {
    setActionLoading(true);
    try {
      if (isPaused) {
        await resumeChatbotContact(name);
        setSuccessMsg(`Resumed replies for '${name}'.`);
      } else {
        await pauseChatbotContact(name);
        setSuccessMsg(`Paused replies for '${name}'.`);
      }
      await loadStatus(true);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to toggle pause contact');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmResetRateLimit = async (contactName: string) => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const res = await resetChatbotContactRateLimit(contactName);
      setResetContactModal(null);
      await loadStatus(true);
      setSuccessMsg(res.message || `Rate limit reset successfully for '${contactName}'.`);
    } catch (err: any) {
      setErrorMsg(err.message || `Failed to reset rate limit for '${contactName}'`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReconcileSubmit = async (confirmed: boolean) => {
    if (!reconcilingMsg) return;
    setActionLoading(true);
    try {
      await reconcileChatbotMessage(reconcilingMsg.id, confirmed, reconcileNotes);
      setReconcilingMsg(null);
      setReconcileNotes('');
      await loadStatus(true);
      setSuccessMsg(`Message reconciled as ${confirmed ? 'SENT' : 'SKIPPED'}.`);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to reconcile message');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveSend = async (messageId: string) => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      await approveChatbotMessage(messageId);
      setSuccessMsg('Candidate reply approved and sent successfully.');
      await loadStatus(true);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to send approved reply');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDismiss = async (messageId: string) => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      await dismissChatbotMessage(messageId);
      setSuccessMsg('Proposal dismissed without sending.');
      await loadStatus(true);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dismiss proposal');
    } finally {
      setActionLoading(false);
    }
  };

  const isRunning = statusData?.is_running ?? false;
  const isAutoReply = statusData?.config.auto_reply_enabled ?? false;
  const contacts = statusData?.contacts ?? [];
  const messages = statusData?.recent_messages ?? [];

  const getStatusBadge = (status: ChatbotMessageStatus) => {
    switch (status) {
      case 'SENT':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <CheckCircle2 size={13} /> SENT
          </span>
        );
      case 'SEND_UNCONFIRMED':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <AlertTriangle size={13} /> SEND UNCONFIRMED
          </span>
        );
      case 'SKIPPED':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(148, 163, 184, 0.2)', color: '#94a3b8', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <Clock size={13} /> SKIPPED
          </span>
        );
      case 'FAILED':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(244, 63, 94, 0.2)', color: '#f43f5e', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <XCircle size={13} /> FAILED
          </span>
        );
      case 'GENERATING':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <Sparkles size={13} /> GENERATING
          </span>
        );
      case 'READY_TO_SEND':
      case 'SENDING':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(168, 85, 247, 0.2)', color: '#c084fc', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            <Bot size={13} /> {status}
          </span>
        );
      default:
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(100, 116, 139, 0.2)', color: '#cbd5e1', padding: '3px 8px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600 }}>
            {status}
          </span>
        );
    }
  };

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Notifications */}
      {errorMsg && (
        <div style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '10px', padding: '0.85rem 1.25rem', color: '#fca5a5', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <AlertTriangle size={18} color="#ef4444" />
            <span style={{ fontSize: '0.9rem' }}>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} style={{ background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer' }}>
            <X size={16} />
          </button>
        </div>
      )}

      {successMsg && (
        <div style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid #10b981', borderRadius: '10px', padding: '0.85rem 1.25rem', color: '#6ee7b7', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <CheckCircle2 size={18} color="#10b981" />
            <span style={{ fontSize: '0.9rem' }}>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} style={{ background: 'none', border: 'none', color: '#6ee7b7', cursor: 'pointer' }}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Main Control Banner */}
      <div className="glass-panel" style={{ padding: '1.5rem', borderRadius: '14px', background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.75) 100%)', border: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: isRunning ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'linear-gradient(135deg, #64748b 0%, #334155 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: isRunning ? '0 0 20px rgba(16, 185, 129, 0.4)' : 'none',
              transition: 'all 0.3s ease'
            }}>
              <Bot size={28} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
                  WhatsApp Incoming-Message AI Chatbot
                </h2>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '3px 10px',
                  borderRadius: '12px',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  background: isRunning ? 'rgba(16, 185, 129, 0.2)' : 'rgba(148, 163, 184, 0.15)',
                  color: isRunning ? '#34d399' : '#94a3b8',
                  border: `1px solid ${isRunning ? '#10b981' : '#64748b'}`
                }}>
                  <span style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: isRunning ? '#10b981' : '#64748b',
                    boxShadow: isRunning ? '0 0 8px #10b981' : 'none'
                  }} />
                  {isRunning ? 'MONITORING ACTIVE' : 'IDLE / STOPPED'}
                </span>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#94a3b8', margin: '4px 0 0 0' }}>
                Monitors verified contacts in your authenticated Chrome session (CDP: 127.0.0.1:9222) and replies contextually via Gemini.
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            {!isRunning ? (
              <button
                onClick={handleStart}
                disabled={actionLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.65rem 1.4rem',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  border: 'none',
                  cursor: actionLoading ? 'not-allowed' : 'pointer',
                  boxShadow: '0 4px 14px rgba(16, 185, 129, 0.35)',
                }}
              >
                <Play size={16} /> Start Chatbot
              </button>
            ) : (
              <button
                onClick={handleStop}
                disabled={actionLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.65rem 1.4rem',
                  borderRadius: '10px',
                  background: 'rgba(239, 68, 68, 0.2)',
                  color: '#fca5a5',
                  fontWeight: 700,
                  fontSize: '0.9rem',
                  border: '1px solid #ef4444',
                  cursor: actionLoading ? 'not-allowed' : 'pointer',
                }}
              >
                <Square size={16} /> Stop Chatbot
              </button>
            )}

            {/* Global Emergency Stop */}
            <button
              onClick={handleStop}
              title="Immediately halts monitoring and safely detaches from Chrome browser"
              disabled={!isRunning || actionLoading}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.65rem 1rem',
                borderRadius: '10px',
                background: 'rgba(225, 29, 72, 0.15)',
                color: '#fb7185',
                border: '1px solid rgba(225, 29, 72, 0.4)',
                fontWeight: 600,
                fontSize: '0.85rem',
                cursor: !isRunning || actionLoading ? 'not-allowed' : 'pointer',
              }}
            >
              <AlertOctagon size={16} /> Emergency Halt
            </button>

            <button
              onClick={() => loadStatus()}
              disabled={loading}
              title="Refresh status"
              style={{
                padding: '0.65rem',
                borderRadius: '10px',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#cbd5e1',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                cursor: 'pointer',
              }}
            >
              <RefreshCw size={16} className={loading ? 'spin' : ''} />
            </button>
          </div>
        </div>

        {/* Security & Automatic Mode Toggle Banner */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          background: isAutoReply ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
          border: `1px solid ${isAutoReply ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
          padding: '0.9rem 1.25rem',
          borderRadius: '10px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Shield size={22} color={isAutoReply ? '#10b981' : '#fbbf24'} />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontWeight: 700, fontSize: '0.92rem', color: '#f8fafc' }}>
                  Automatic Sending Mode:
                </span>
                <span style={{
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  color: isAutoReply ? '#34d399' : '#fbbf24',
                }}>
                  {isAutoReply ? 'ENABLED (Autonomous Reply Enabled)' : 'DISABLED (Detection Only / Safe Mode)'}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8' }}>
                {isAutoReply
                  ? 'Chatbot will automatically send validated replies to allowed contacts within configured rate limits.'
                  : 'Chatbot only logs incoming messages and generates proposed replies without sending them.'}
              </p>
            </div>
          </div>

          <button
            onClick={handleToggleAutoReply}
            disabled={actionLoading}
            style={{
              padding: '0.5rem 1.2rem',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '0.85rem',
              cursor: actionLoading ? 'not-allowed' : 'pointer',
              background: isAutoReply ? 'rgba(239, 68, 68, 0.2)' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: isAutoReply ? '#fca5a5' : '#ffffff',
              border: isAutoReply ? '1px solid #ef4444' : 'none',
              boxShadow: isAutoReply ? 'none' : '0 2px 10px rgba(16, 185, 129, 0.3)',
            }}
          >
            {isAutoReply ? 'Disable Automatic Replies' : 'Enable Automatic Replies'}
          </button>
        </div>
      </div>

      {/* Grid: Allowlist & Configuration */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem' }}>
        {/* Contact Allowlist Manager */}
        <div className="glass-panel" style={{ padding: '1.25rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.7)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Shield size={18} color="#00a884" />
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
                Contact Allowlist ({contacts.length})
              </h3>
            </div>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              Only monitored contacts
            </span>
          </div>

          {/* Add Contact Form */}
          <form onSubmit={handleAddContact} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                placeholder="Exact Contact Name (e.g. Joy Boy)"
                value={newContactName}
                onChange={e => setNewContactName(e.target.value)}
                style={{
                  flex: 1,
                  padding: '0.55rem 0.85rem',
                  borderRadius: '8px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
              <button
                type="submit"
                disabled={!newContactName.trim() || actionLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.55rem 1rem',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  border: 'none',
                  cursor: !newContactName.trim() || actionLoading ? 'not-allowed' : 'pointer',
                }}
              >
                <UserPlus size={15} /> Add
              </button>
            </div>
            <input
              type="text"
              placeholder="Optional notes or relationship info"
              value={newContactNotes}
              onChange={e => setNewContactNotes(e.target.value)}
              style={{
                padding: '0.45rem 0.85rem',
                borderRadius: '8px',
                background: 'rgba(30, 41, 59, 0.4)',
                border: '1px solid rgba(255, 255, 255, 0.06)',
                color: '#cbd5e1',
                fontSize: '0.8rem',
              }}
            />
          </form>

          {/* Contact List */}
          {contacts.length === 0 ? (
            <div style={{
              background: 'rgba(245, 158, 11, 0.08)',
              border: '1px dashed rgba(245, 158, 11, 0.4)',
              borderRadius: '8px',
              padding: '1rem',
              textAlign: 'center',
              color: '#fbbf24',
              fontSize: '0.82rem',
            }}>
              <AlertTriangle size={20} style={{ margin: '0 auto 6px auto', display: 'block' }} />
              <strong>Allowlist is Empty</strong>
              <p style={{ margin: '4px 0 0 0', color: '#cbd5e1', fontSize: '0.78rem' }}>
                For your safety, the chatbot will never monitor or reply to conversations until at least one contact is added.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '260px', overflowY: 'auto' }}>
              {contacts.map(c => {
                const contactName = c.contact_name || c.name || '';
                return (
                  <div
                    key={contactName}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.65rem 0.85rem',
                      background: c.is_paused ? 'rgba(30, 41, 59, 0.3)' : 'rgba(30, 41, 59, 0.8)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                      borderRadius: '8px',
                      opacity: c.is_paused ? 0.7 : 1,
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.88rem' }}>
                          {contactName}
                        </span>
                        {c.is_paused ? (
                          <span style={{ fontSize: '0.7rem', color: '#fbbf24', background: 'rgba(245, 158, 11, 0.2)', padding: '1px 6px', borderRadius: '4px' }}>
                            Paused
                          </span>
                        ) : (
                          <span style={{ fontSize: '0.7rem', color: '#34d399', background: 'rgba(16, 185, 129, 0.2)', padding: '1px 6px', borderRadius: '4px' }}>
                            Active
                          </span>
                        )}
                      </div>
                      {c.notes && (
                        <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '2px' }}>
                          {c.notes}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <button
                        onClick={() => setResetContactModal(contactName)}
                        title={`Reset rate limit for ${contactName}`}
                        id={`reset-rate-limit-${contactName.toLowerCase().replace(/\s+/g, '-')}`}
                        disabled={actionLoading}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          background: 'rgba(59, 130, 246, 0.12)',
                          border: '1px solid rgba(59, 130, 246, 0.28)',
                          color: '#60a5fa',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          padding: '3px 8px',
                          fontSize: '0.72rem',
                          fontWeight: 500,
                          transition: 'all 0.2s ease',
                        }}
                      >
                        <RotateCcw size={12} />
                        <span>Reset Rate Limit</span>
                      </button>
                      <button
                        onClick={() => handleTogglePauseContact(contactName, c.is_paused)}
                        title={c.is_paused ? 'Resume monitoring' : 'Pause monitoring'}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: c.is_paused ? '#34d399' : '#fbbf24',
                          cursor: 'pointer',
                          padding: '4px',
                        }}
                      >
                        {c.is_paused ? <PlayCircle size={18} /> : <PauseCircle size={18} />}
                      </button>
                      <button
                        onClick={() => handleRemoveContact(contactName)}
                        title="Remove contact"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#f87171',
                          cursor: 'pointer',
                          padding: '4px',
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Safety & Rate Limits Configuration */}
        <div className="glass-panel" style={{ padding: '1.25rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.7)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Sliders size={18} color="#38bdf8" />
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
                Safety & Rate Limits
              </h3>
            </div>
            <button
              onClick={handleSaveConfig}
              disabled={configSaving}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.4rem 0.9rem',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.8rem',
                border: 'none',
                cursor: configSaving ? 'not-allowed' : 'pointer',
              }}
            >
              <Check size={14} /> Save Settings
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '4px' }}>
                Observation Interval (sec)
              </label>
              <input
                type="number"
                min="2"
                max="60"
                value={configEditing.poll_interval_seconds ?? 5}
                onChange={e => setConfigEditing({ ...configEditing, poll_interval_seconds: Number(e.target.value) })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '4px' }}>
                Max Reply Length (chars)
              </label>
              <input
                type="number"
                min="50"
                max="1000"
                value={configEditing.max_reply_length ?? 300}
                onChange={e => setConfigEditing({ ...configEditing, max_reply_length: Number(e.target.value) })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '4px' }}>
                Max Replies / Window
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={configEditing.max_replies_per_contact_window ?? configEditing.max_replies_per_window ?? 5}
                onChange={e => {
                  const val = Number(e.target.value);
                  setConfigEditing(prev => ({
                    ...prev,
                    max_replies_per_contact_window: val,
                    max_replies_per_window: val,
                  }));
                }}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '4px' }}>
                Rate Limit Window (min)
              </label>
              <input
                type="number"
                min="1"
                max="120"
                value={configEditing.rate_limit_window_minutes ?? 10}
                onChange={e => setConfigEditing({ ...configEditing, rate_limit_window_minutes: Number(e.target.value) })}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
            </div>
          </div>

          {/* Model info banner */}
          <div style={{
            background: 'rgba(30, 41, 59, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            borderRadius: '8px',
            padding: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.78rem',
            color: '#cbd5e1',
          }}>
            <span>Model: <strong style={{ color: '#38bdf8' }}>{health?.gemini_model || 'gemini-3.5-flash-lite'}</strong></span>
            <span>CDP: <strong style={{ color: '#34d399' }}>127.0.0.1:9222</strong></span>
            <span>Target: <strong style={{ color: '#00a884' }}>web.whatsapp.com</strong></span>
          </div>
        </div>
      </div>

      {/* Recent Incoming Messages & Audit Log */}
      <div className="glass-panel" style={{ padding: '1.25rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.7)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <MessageSquare size={18} color="#00a884" />
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
              Recent Messages & Reply Audit Log ({messages.length})
            </h3>
          </div>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            Durable deduplication across backend restarts
          </span>
        </div>

        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b', fontSize: '0.85rem' }}>
            No incoming messages observed yet. Start the chatbot and send a message from an allowed contact to view live detection.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: '#94a3b8' }}>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Status</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Sender</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Incoming Message</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Generated AI Reply</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Latency / Stages</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Skip Reason / Notes</th>
                  <th style={{ padding: '0.6rem 0.8rem' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {messages.map(m => (
                  <tr key={m.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                    <td style={{ padding: '0.75rem 0.8rem', whiteSpace: 'nowrap' }}>
                      {getStatusBadge(m.status)}
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', fontWeight: 600, color: '#f8fafc', whiteSpace: 'nowrap' }}>
                      {m.contact_name}
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', color: '#e2e8f0', maxWidth: '220px' }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.incoming_text}>
                        {m.incoming_text}
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', color: '#38bdf8', maxWidth: '240px' }}>
                      {m.reply_text ? (
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.reply_text}>
                          "{m.reply_text}"
                        </div>
                      ) : (
                        <span style={{ color: '#64748b' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', whiteSpace: 'nowrap' }}>
                      {m.total_duration_ms != null ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontWeight: 700,
                            color: m.total_duration_ms > 20000 ? '#f43f5e' : m.total_duration_ms > 10000 ? '#38bdf8' : '#34d399',
                            fontSize: '0.78rem'
                          }}>
                            <Zap size={12} />
                            {m.total_duration_ms >= 1000
                              ? `${(m.total_duration_ms / 1000).toFixed(1)}s`
                              : `${Math.round(m.total_duration_ms)}ms`}
                          </span>
                          {m.stage_timings && (
                            <div style={{ fontSize: '0.68rem', color: '#94a3b8', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                              {m.stage_timings.gemini_request_ms != null && (
                                <span title={`Gemini LLM: ${m.stage_timings.gemini_request_ms}ms`}>
                                  LLM: {(m.stage_timings.gemini_request_ms / 1000).toFixed(1)}s
                                </span>
                              )}
                              {m.stage_timings.playwright_send_ms != null && m.stage_timings.playwright_send_ms > 0 && (
                                <span title={`Browser Send: ${m.stage_timings.playwright_send_ms}ms`}>
                                  Send: {(m.stage_timings.playwright_send_ms / 1000).toFixed(1)}s
                                </span>
                              )}
                              {m.stage_timings.verification_ms != null && m.stage_timings.verification_ms > 0 && (
                                <span title={`Verification: ${m.stage_timings.verification_ms}ms`}>
                                  Verif: {(m.stage_timings.verification_ms / 1000).toFixed(1)}s
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      ) : m.status === 'GENERATING' ? (
                        <span style={{ fontSize: '0.75rem', color: '#38bdf8', fontStyle: 'italic', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <Sparkles size={11} /> Generating...
                        </span>
                      ) : m.status === 'SENDING' ? (
                        <span style={{ fontSize: '0.75rem', color: '#c084fc', fontStyle: 'italic', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <Bot size={11} /> Sending...
                        </span>
                      ) : (
                        <span style={{ color: '#64748b' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', color: '#94a3b8', maxWidth: '200px' }}>
                      {m.skip_reason ? (
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.skip_reason}>
                          {m.skip_reason}
                        </div>
                      ) : (
                        <span style={{ color: '#64748b' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.8rem', whiteSpace: 'nowrap' }}>
                      {m.status === 'READY_TO_SEND' && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <button
                            onClick={() => handleApproveSend(m.id)}
                            disabled={actionLoading}
                            title="Explicitly approve and dispatch this reply now"
                            style={{
                              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: '6px',
                              padding: '4px 10px',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              cursor: actionLoading ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Send size={12} /> Approve & Send
                          </button>
                          <button
                            onClick={() => handleDismiss(m.id)}
                            disabled={actionLoading}
                            title="Dismiss this reply proposal without sending"
                            style={{
                              background: 'rgba(239, 68, 68, 0.15)',
                              color: '#fca5a5',
                              border: '1px solid rgba(239, 68, 68, 0.4)',
                              borderRadius: '6px',
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              cursor: actionLoading ? 'not-allowed' : 'pointer',
                            }}
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                      {m.status === 'SEND_UNCONFIRMED' && (
                        <button
                          onClick={() => setReconcilingMsg(m)}
                          style={{
                            background: 'rgba(245, 158, 11, 0.2)',
                            color: '#fbbf24',
                            border: '1px solid #f59e0b',
                            borderRadius: '6px',
                            padding: '3px 8px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Reconcile
                        </button>
                      )}
                      {m.status !== 'READY_TO_SEND' && m.status !== 'SEND_UNCONFIRMED' && (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Reconciliation Modal */}
      {reconcilingMsg && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div className="glass-panel" style={{
            maxWidth: '500px',
            width: '100%',
            background: '#0f172a',
            border: '1px solid #f59e0b',
            borderRadius: '12px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fbbf24' }}>
              <AlertTriangle size={22} />
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>
                Reconcile Uncertain Send
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#cbd5e1', margin: 0 }}>
              The send outcome for incoming message from <strong>{reconcilingMsg.contact_name}</strong> was inconclusive during execution.
            </p>

            <div style={{ background: 'rgba(30, 41, 59, 0.8)', padding: '0.75rem', borderRadius: '8px', fontSize: '0.82rem' }}>
              <div><strong>Incoming:</strong> {reconcilingMsg.incoming_text}</div>
              <div style={{ marginTop: '4px' }}><strong>Proposed Reply:</strong> "{reconcilingMsg.reply_text}"</div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '4px' }}>
                Reconciliation Note (optional)
              </label>
              <input
                type="text"
                placeholder="e.g. Verified in WhatsApp that message was delivered"
                value={reconcileNotes}
                onChange={e => setReconcileNotes(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  background: 'rgba(30, 41, 59, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                onClick={() => setReconcilingMsg(null)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  background: 'transparent',
                  color: '#94a3b8',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleReconcileSubmit(false)}
                disabled={actionLoading}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  background: 'rgba(100, 116, 139, 0.25)',
                  color: '#cbd5e1',
                  border: '1px solid #64748b',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                }}
              >
                Mark as SKIPPED
              </button>
              <button
                onClick={() => handleReconcileSubmit(true)}
                disabled={actionLoading}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  color: '#ffffff',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                }}
              >
                Confirm as SENT
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Rate Limit Confirmation Modal */}
      {resetContactModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div className="glass-panel" style={{
            maxWidth: '480px',
            width: '100%',
            background: '#0f172a',
            border: '1px solid rgba(59, 130, 246, 0.4)',
            borderRadius: '12px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#60a5fa' }}>
              <RotateCcw size={22} />
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>
                Reset Rate Limit
              </h3>
            </div>

            <p style={{ fontSize: '0.88rem', color: '#cbd5e1', margin: 0, lineHeight: 1.5 }}>
              Are you sure you want to reset the rolling rate limit for <strong style={{ color: '#60a5fa' }}>{resetContactModal}</strong>?
            </p>

            <div style={{ background: 'rgba(30, 41, 59, 0.8)', padding: '0.75rem', borderRadius: '8px', fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.4 }}>
              This will clear sent-reply rate-limit history for <strong>{resetContactModal}</strong> in the current active time window ({statusData?.config?.rate_limit_window_minutes ?? 15} min). The configured limit ({statusData?.config?.max_replies_per_contact_window ?? 5} replies/window) and other contacts remain unaffected.
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                onClick={() => setResetContactModal(null)}
                disabled={actionLoading}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  background: 'transparent',
                  color: '#94a3b8',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleConfirmResetRateLimit(resetContactModal)}
                disabled={actionLoading}
                id="confirm-reset-rate-limit-button"
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
                  color: '#ffffff',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <RotateCcw size={14} />
                <span>{actionLoading ? 'Resetting...' : 'Confirm Reset'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

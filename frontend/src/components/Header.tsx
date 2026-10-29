import React from 'react';
import { Bot, Shield, Cpu, RefreshCw, ExternalLink, MessageSquare } from 'lucide-react';
import { HealthResponse } from '../types';

export type ActiveViewMode = 'agent' | 'whatsapp' | 'chatbot';

interface HeaderProps {
  health: HealthResponse | null;
  onRefreshHealth: () => void;
  onNewTaskClick: () => void;
  activeMode: ActiveViewMode;
  onModeChange: (mode: ActiveViewMode) => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  onRefreshHealth,
  onNewTaskClick,
  activeMode,
  onModeChange,
}) => {

  return (
    <header className="glass-panel" style={{ margin: '1rem', padding: '1rem 1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <div style={{
          width: '42px',
          height: '42px',
          borderRadius: '10px',
          background: 'linear-gradient(135deg, #0284c7 0%, #8b5cf6 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 15px rgba(14, 165, 233, 0.4)'
        }}>
          <Bot size={24} color="#ffffff" />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.02em', color: '#f8fafc' }}>
              Gemini + Playwright
            </h1>
            <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem', borderRadius: '4px', background: 'rgba(14, 165, 233, 0.2)', color: '#38bdf8', fontWeight: 600 }}>
              AI Web Agent
            </span>
          </div>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            Autonomous browser inspection, verified execution, and conversational AI WhatsApp monitoring
          </p>
        </div>
      </div>

      {/* Mode Switcher Tabs */}
      <div
        style={{
          display: 'flex',
          background: 'rgba(15, 23, 42, 0.8)',
          padding: '0.25rem',
          borderRadius: '10px',
          border: '1px solid var(--border-subtle)',
          gap: '0.25rem',
        }}
      >
        <button
          onClick={() => onModeChange('agent')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.45rem 0.9rem',
            borderRadius: '8px',
            fontSize: '0.82rem',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            background: activeMode === 'agent' ? 'rgba(14, 165, 233, 0.25)' : 'transparent',
            color: activeMode === 'agent' ? '#38bdf8' : '#94a3b8',
            boxShadow: activeMode === 'agent' ? '0 0 10px rgba(14, 165, 233, 0.2)' : 'none',
          }}
        >
          <Bot size={15} />
          <span>Web Automation</span>
        </button>

        <button
          onClick={() => onModeChange('whatsapp')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.45rem 0.9rem',
            borderRadius: '8px',
            fontSize: '0.82rem',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            background: activeMode === 'whatsapp' ? 'rgba(0, 168, 132, 0.25)' : 'transparent',
            color: activeMode === 'whatsapp' ? '#00a884' : '#94a3b8',
            boxShadow: activeMode === 'whatsapp' ? '0 0 10px rgba(0, 168, 132, 0.2)' : 'none',
          }}
        >
          <MessageSquare size={15} />
          <span>WhatsApp Sender</span>
        </button>

        <button
          onClick={() => onModeChange('chatbot')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.45rem 0.9rem',
            borderRadius: '8px',
            fontSize: '0.82rem',
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            background: activeMode === 'chatbot' ? 'rgba(168, 85, 247, 0.25)' : 'transparent',
            color: activeMode === 'chatbot' ? '#c084fc' : '#94a3b8',
            boxShadow: activeMode === 'chatbot' ? '0 0 10px rgba(168, 85, 247, 0.2)' : 'none',
          }}
        >
          <Bot size={15} />
          <span>AI Chatbot</span>
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        {health && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.8rem', background: 'rgba(15, 23, 42, 0.6)', padding: '0.4rem 0.8rem', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Cpu size={14} color="#38bdf8" />
              <span style={{ color: '#cbd5e1' }}>Model:</span>
              <strong style={{ color: '#f8fafc' }}>{health.gemini_model}</strong>
            </div>

            <div style={{ height: '14px', width: '1px', background: 'rgba(255, 255, 255, 0.15)' }} />

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Shield size={14} color="#34d399" />
              <span style={{ color: '#cbd5e1' }}>Gemini:</span>
              <span style={{ color: health.gemini_configured ? '#34d399' : '#fbbf24', fontWeight: 600 }}>
                {health.gemini_configured ? 'Configured' : 'Key Required'}
              </span>
            </div>

            <button 
              onClick={onRefreshHealth}
              title="Refresh health status"
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        )}

        <a
          href="/test-site"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: '0.8rem',
            color: '#38bdf8',
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            background: 'rgba(14, 165, 233, 0.1)',
            padding: '0.45rem 0.85rem',
            borderRadius: '8px',
            border: '1px solid rgba(14, 165, 233, 0.25)',
            fontWeight: 500
          }}
        >
          <span>Open Demo Site</span>
          <ExternalLink size={13} />
        </a>

        <button
          onClick={onNewTaskClick}
          className="btn-primary"
          style={{ padding: '0.5rem 1rem', borderRadius: '8px', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer' }}
        >
          + New Task
        </button>
      </div>
    </header>
  );
};

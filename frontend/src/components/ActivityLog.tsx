import React from 'react';
import { Activity, CheckCircle2, AlertCircle, Clock, ChevronRight, Eye, CornerDownRight } from 'lucide-react';
import { ActionLogItem } from '../types';

interface ActivityLogProps {
  logs: ActionLogItem[];
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ logs }) => {
  const getCategoryBadge = (category: string) => {
    switch (category?.toUpperCase()) {
      case 'READ_ONLY':
        return (
          <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', fontWeight: 600 }}>
            READ-ONLY
          </span>
        );
      case 'REVERSIBLE':
        return (
          <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', fontWeight: 600 }}>
            REVERSIBLE
          </span>
        );
      case 'CONSEQUENTIAL':
        return (
          <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', border: '1px solid rgba(245, 158, 11, 0.3)', fontWeight: 600 }}>
            CONSEQUENTIAL
          </span>
        );
      default:
        return (
          <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: '1px solid rgba(148, 163, 184, 0.3)', fontWeight: 600 }}>
            {category || 'SYSTEM'}
          </span>
        );
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '1.25rem', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={18} color="#0ea5e9" />
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
            Action Execution Stream
          </h3>
        </div>
        <span style={{ fontSize: '0.75rem', color: '#64748b', background: 'rgba(15, 23, 42, 0.8)', padding: '0.2rem 0.6rem', borderRadius: '12px' }}>
          {logs.length} Actions Logged
        </span>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, paddingRight: '0.35rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {logs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 1rem', color: '#64748b', fontSize: '0.85rem' }}>
            <Clock size={28} style={{ margin: '0 auto 0.75rem', opacity: 0.5 }} />
            <p>Waiting for agent to initialize browser and execute the first action...</p>
          </div>
        ) : (
          logs.map((log, idx) => {
            const hasError = !!log.error;
            return (
              <div
                key={idx}
                style={{
                  background: 'rgba(15, 23, 42, 0.6)',
                  border: `1px solid ${hasError ? 'rgba(244, 63, 94, 0.3)' : 'rgba(255, 255, 255, 0.06)'}`,
                  borderRadius: '10px',
                  padding: '0.85rem 1rem',
                  fontSize: '0.85rem',
                  transition: 'background 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.4rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', width: '20px' }}>
                      #{log.step}
                    </span>
                    <strong style={{ color: '#f8fafc', fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>
                      {log.tool_name}
                    </strong>
                    {getCategoryBadge(log.category)}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    {hasError ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#fb7185', fontSize: '0.75rem', fontWeight: 600 }}>
                        <AlertCircle size={13} />
                        Failed
                      </span>
                    ) : (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#34d399', fontSize: '0.75rem', fontWeight: 600 }}>
                        <CheckCircle2 size={13} />
                        Verified
                      </span>
                    )}
                  </div>
                </div>

                {log.explanation && (
                  <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: '0.5rem', fontStyle: 'italic', lineHeight: 1.4 }}>
                    "{log.explanation}"
                  </p>
                )}

                {/* Arguments Preview */}
                {log.arguments && Object.keys(log.arguments).length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.4rem', background: '#090d16', padding: '0.4rem 0.6rem', borderRadius: '6px', fontSize: '0.75rem', color: '#cbd5e1', marginBottom: '0.4rem', fontFamily: 'var(--font-mono)' }}>
                    <CornerDownRight size={13} style={{ marginTop: '2px', color: '#38bdf8', flexShrink: 0 }} />
                    <span style={{ wordBreak: 'break-all' }}>
                      {Object.entries(log.arguments).map(([k, v]) => `${k}="${String(v)}"`).join(', ')}
                    </span>
                  </div>
                )}

                {/* Error message if any */}
                {log.error && (
                  <div style={{ color: '#fb7185', fontSize: '0.75rem', background: 'rgba(244, 63, 94, 0.1)', padding: '0.4rem 0.6rem', borderRadius: '6px' }}>
                    {log.error}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

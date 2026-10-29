import React, { useState } from 'react';
import { AlertTriangle, Check, X, ShieldAlert, KeyRound } from 'lucide-react';
import { PendingApproval } from '../types';

interface ApprovalPanelProps {
  approval: PendingApproval;
  onApprove: () => Promise<void>;
  onReject: (reason?: string) => Promise<void>;
  isLoading: boolean;
}

export const ApprovalPanel: React.FC<ApprovalPanelProps> = ({
  approval,
  onApprove,
  onReject,
  isLoading,
}) => {
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  return (
    <div
      className="glass-panel"
      style={{
        border: '1px solid rgba(245, 158, 11, 0.5)',
        background: 'linear-gradient(180deg, rgba(30, 27, 20, 0.95) 0%, rgba(17, 24, 39, 0.95) 100%)',
        padding: '1.5rem',
        marginBottom: '1.5rem',
        borderRadius: '12px',
        boxShadow: '0 0 25px rgba(245, 158, 11, 0.25)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.85rem', marginBottom: '1rem' }}>
        <div style={{
          background: 'rgba(245, 158, 11, 0.2)',
          padding: '0.6rem',
          borderRadius: '10px',
          color: '#fbbf24',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <ShieldAlert size={24} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fbbf24' }}>
              Action Approval Required (Consequential State Mutation)
            </h3>
            <span style={{ fontSize: '0.7rem', padding: '0.15rem 0.45rem', borderRadius: '4px', background: 'rgba(245, 158, 11, 0.2)', color: '#fef3c7', fontWeight: 600 }}>
              POLICY ENFORCEMENT
            </span>
          </div>
          <p style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: 1.5 }}>
            {approval.description}
          </p>
        </div>
      </div>

      {/* Details Box */}
      <div style={{ background: 'rgba(10, 15, 26, 0.8)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '8px', padding: '1rem', marginBottom: '1.25rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
          <div>
            <span style={{ color: '#64748b', display: 'block' }}>Target Website:</span>
            <strong style={{ color: '#38bdf8' }}>{approval.target_url}</strong>
          </div>
          <div>
            <span style={{ color: '#64748b', display: 'block' }}>Tool:</span>
            <strong style={{ color: '#f8fafc', fontFamily: 'var(--font-mono)' }}>{approval.action_name}</strong>
          </div>
        </div>

        <div>
          <span style={{ color: '#64748b', fontSize: '0.75rem', display: 'block', marginBottom: '0.3rem' }}>Action Payload / Arguments:</span>
          <pre style={{ margin: 0, padding: '0.6rem', background: '#070a12', borderRadius: '6px', fontSize: '0.75rem', color: '#a5f3fc', overflowX: 'auto', fontFamily: 'var(--font-mono)' }}>
            {JSON.stringify(approval.action_args, null, 2)}
          </pre>
        </div>
      </div>

      {showRejectInput && (
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.3rem' }}>
            Optional rejection reason / instructions for agent:
          </label>
          <input
            type="text"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="e.g. Do not submit yet, change email to user@test.com"
            style={{
              width: '100%',
              padding: '0.6rem 0.8rem',
              background: '#0c1220',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '6px',
              color: '#f8fafc',
              fontSize: '0.85rem',
            }}
          />
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        {!showRejectInput ? (
          <button
            type="button"
            onClick={() => setShowRejectInput(true)}
            style={{
              background: 'rgba(244, 63, 94, 0.15)',
              border: '1px solid rgba(244, 63, 94, 0.4)',
              color: '#fb7185',
              padding: '0.6rem 1.25rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <X size={16} />
            Reject Action
          </button>
        ) : (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onReject(rejectReason)}
            style={{
              background: '#e11d48',
              border: 'none',
              color: 'white',
              padding: '0.6rem 1.25rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: isLoading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <X size={16} />
            Confirm Rejection
          </button>
        )}

        <button
          type="button"
          disabled={isLoading}
          onClick={() => onApprove()}
          style={{
            background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
            border: '1px solid rgba(52, 211, 153, 0.4)',
            color: 'white',
            padding: '0.6rem 1.5rem',
            borderRadius: '8px',
            fontSize: '0.85rem',
            fontWeight: 700,
            cursor: isLoading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            boxShadow: '0 4px 15px rgba(16, 185, 129, 0.3)',
          }}
        >
          <Check size={18} />
          {isLoading ? 'Processing...' : 'Approve & Execute Action'}
        </button>
      </div>
    </div>
  );
};

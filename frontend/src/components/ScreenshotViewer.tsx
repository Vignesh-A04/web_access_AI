import React, { useState } from 'react';
import { Camera, RefreshCw, Eye, ExternalLink } from 'lucide-react';

interface ScreenshotViewerProps {
  taskId: string;
  currentUrl?: string;
}

export const ScreenshotViewer: React.FC<ScreenshotViewerProps> = ({ taskId, currentUrl }) => {
  const [key, setKey] = useState(Date.now());
  const [hasError, setHasError] = useState(false);

  const refreshImage = () => {
    setKey(Date.now());
    setHasError(false);
  };

  const screenshotUrl = `/api/tasks/${taskId}/screenshot?t=${key}`;

  return (
    <div className="glass-panel" style={{ padding: '1.25rem', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Camera size={18} color="#38bdf8" />
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
            Live Browser View
          </h3>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {currentUrl && (
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', maxWidth: '250px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={currentUrl}>
              {currentUrl}
            </span>
          )}
          <button
            onClick={refreshImage}
            title="Reload live screenshot"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              color: '#94a3b8',
              padding: '0.3rem 0.5rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontSize: '0.75rem',
            }}
          >
            <RefreshCw size={12} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          background: '#070a12',
          borderRadius: '10px',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
          minHeight: '360px',
        }}
      >
        {!hasError ? (
          <img
            src={screenshotUrl}
            alt="Live Browser Screenshot"
            onError={() => setHasError(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              display: 'block',
            }}
          />
        ) : (
          <div style={{ textAlign: 'center', color: '#64748b', padding: '2rem' }}>
            <Camera size={36} style={{ margin: '0 auto 0.75rem', opacity: 0.4 }} />
            <p style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>Capturing initial browser viewport...</p>
            <span style={{ fontSize: '0.75rem', color: '#475569' }}>
              Screenshots will update automatically as actions execute.
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

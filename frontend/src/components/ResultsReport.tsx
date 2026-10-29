import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Download, ArrowRight, ShieldCheck, ListChecks } from 'lucide-react';
import { TaskResponse } from '../types';

interface ResultsReportProps {
  task: TaskResponse;
  onNewTask: () => void;
}

export const ResultsReport: React.FC<ResultsReportProps> = ({ task, onNewTask }) => {
  const isSuccess = task.status === 'COMPLETED';
  const isFailed = task.status === 'FAILED';
  const isCancelled = task.status === 'CANCELLED';

  const downloadJsonReport = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(task, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `agent-report-${task.task_id.slice(0, 8)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div
      className="glass-panel"
      style={{
        padding: '2rem',
        maxWidth: '900px',
        margin: '2rem auto',
        border: isSuccess
          ? '1px solid rgba(16, 185, 129, 0.4)'
          : isFailed
          ? '1px solid rgba(244, 63, 94, 0.4)'
          : '1px solid var(--border-subtle)',
      }}
    >
      {/* Header Banner */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {isSuccess && (
            <div style={{ background: 'rgba(16, 185, 129, 0.2)', padding: '0.6rem', borderRadius: '10px', color: '#34d399' }}>
              <CheckCircle2 size={26} />
            </div>
          )}
          {isFailed && (
            <div style={{ background: 'rgba(244, 63, 94, 0.2)', padding: '0.6rem', borderRadius: '10px', color: '#fb7185' }}>
              <XCircle size={26} />
            </div>
          )}
          {isCancelled && (
            <div style={{ background: 'rgba(148, 163, 184, 0.2)', padding: '0.6rem', borderRadius: '10px', color: '#cbd5e1' }}>
              <AlertTriangle size={26} />
            </div>
          )}

          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc' }}>
              {isSuccess && 'Task Completed & Outcomes Verified'}
              {isFailed && 'Task Execution Stopped / Failed'}
              {isCancelled && 'Task Cancelled by User'}
            </h2>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Executed {task.steps_taken} of max {task.max_steps} steps on target website
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button
            onClick={downloadJsonReport}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              color: '#f8fafc',
              padding: '0.5rem 0.9rem',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <Download size={14} />
            <span>Download Report</span>
          </button>

          <button
            onClick={onNewTask}
            className="btn-primary"
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '8px',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <span>Run New Task</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* Final Report Card */}
      {task.final_report && (
        <div style={{ background: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '10px', padding: '1.25rem', marginBottom: '1.5rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#38bdf8', display: 'block', marginBottom: '0.5rem' }}>
            Final Agent Report & Findings
          </span>
          <p style={{ color: '#f1f5f9', fontSize: '0.95rem', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
            {task.final_report}
          </p>
        </div>
      )}

      {/* Verified Outcomes List */}
      {task.verified_outcomes && task.verified_outcomes.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
            <ListChecks size={18} color="#10b981" />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc' }}>
              Specifically Verified Outcomes ({task.verified_outcomes.length})
            </h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {task.verified_outcomes.map((outcome, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: '8px',
                  padding: '0.6rem 0.85rem',
                  fontSize: '0.85rem',
                  color: '#e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                }}
              >
                <ShieldCheck size={16} color="#34d399" style={{ flexShrink: 0 }} />
                <span>{outcome}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Errors (if any) */}
      {task.errors && task.errors.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: '#fb7185', display: 'block', marginBottom: '0.5rem' }}>
            Execution Errors / Blockers
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {task.errors.map((err, idx) => (
              <div key={idx} style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', color: '#fb7185', padding: '0.6rem 0.85rem', borderRadius: '8px', fontSize: '0.85rem' }}>
                {err}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Task Metadata Footer */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.8rem', color: '#64748b' }}>
        <div>
          <span>Target URL: </span>
          <span style={{ color: '#94a3b8' }}>{task.url}</span>
        </div>
        <div>
          <span>Final Page URL: </span>
          <span style={{ color: '#94a3b8' }}>{task.current_url || task.url}</span>
        </div>
        <div>
          <span>Task ID: </span>
          <span style={{ color: '#94a3b8', fontFamily: 'var(--font-mono)' }}>{task.task_id.slice(0, 13)}...</span>
        </div>
      </div>
    </div>
  );
};

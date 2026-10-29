import React from 'react';
import { StopCircle, Globe, Compass, ExternalLink } from 'lucide-react';
import { ActionLogItem, TaskResponse } from '../types';
import { ApprovalPanel } from './ApprovalPanel';
import { ActivityLog } from './ActivityLog';
import { ScreenshotViewer } from './ScreenshotViewer';
import { ResultsReport } from './ResultsReport';

interface LiveExecutionViewProps {
  task: TaskResponse;
  logs: ActionLogItem[];
  onApproveAction: () => Promise<void>;
  onRejectAction: (reason?: string) => Promise<void>;
  onCancelTask: () => Promise<void>;
  onNewTask: () => void;
  isApprovalLoading: boolean;
}

export const LiveExecutionView: React.FC<LiveExecutionViewProps> = ({
  task,
  logs,
  onApproveAction,
  onRejectAction,
  onCancelTask,
  onNewTask,
  isApprovalLoading,
}) => {
  const isTerminal = ['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.status);

  const getStatusBadgeClass = () => {
    switch (task.status) {
      case 'RUNNING':
        return 'badge-running';
      case 'WAITING_FOR_APPROVAL':
        return 'badge-waiting';
      case 'COMPLETED':
        return 'badge-completed';
      case 'FAILED':
        return 'badge-failed';
      case 'CANCELLED':
        return 'badge-cancelled';
      default:
        return 'badge-queued';
    }
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '1rem auto', padding: '0 1rem' }}>
      {/* Task Control Bar */}
      <div
        className="glass-panel"
        style={{
          padding: '1.25rem 1.5rem',
          marginBottom: '1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              className={getStatusBadgeClass()}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '8px',
                fontSize: '0.8rem',
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              {task.status.replace(/_/g, ' ')}
            </span>

            <span style={{ fontSize: '0.85rem', color: '#94a3b8', background: 'rgba(15, 23, 42, 0.7)', padding: '0.35rem 0.65rem', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              Step {task.steps_taken} of {task.max_steps}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
            <Globe size={15} color="#38bdf8" />
            <span style={{ color: '#64748b' }}>Target:</span>
            <a
              href={task.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#38bdf8', textDecoration: 'none', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.25rem' }}
            >
              <span style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {task.url}
              </span>
              <ExternalLink size={12} />
            </a>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {!isTerminal && (
            <button
              onClick={onCancelTask}
              style={{
                background: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.3)',
                color: '#fb7185',
                padding: '0.45rem 0.9rem',
                borderRadius: '8px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <StopCircle size={15} />
              <span>Cancel Task</span>
            </button>
          )}

          {isTerminal && (
            <button
              onClick={onNewTask}
              className="btn-primary"
              style={{ padding: '0.45rem 1rem', borderRadius: '8px', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer' }}
            >
              + Start Another Task
            </button>
          )}
        </div>
      </div>

      {/* Consequential Action Approval Panel */}
      {task.status === 'WAITING_FOR_APPROVAL' && task.pending_approval && (
        <ApprovalPanel
          approval={task.pending_approval}
          onApprove={onApproveAction}
          onReject={onRejectAction}
          isLoading={isApprovalLoading}
        />
      )}

      {/* Terminal Results Report */}
      {isTerminal && (
        <ResultsReport task={task} onNewTask={onNewTask} />
      )}

      {/* Live 2-Column Split: Activity Stream & Browser Screenshot */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(350px, 1fr) minmax(450px, 1.2fr)', gap: '1.25rem', minHeight: '620px' }}>
        <ActivityLog logs={logs} />
        <ScreenshotViewer taskId={task.task_id} currentUrl={task.current_url} />
      </div>
    </div>
  );
};

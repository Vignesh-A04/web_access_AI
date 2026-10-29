import React, { useEffect, useState } from 'react';
import { Header, ActiveViewMode } from './components/Header';
import { TaskCreationForm } from './components/TaskCreationForm';
import { LiveExecutionView } from './components/LiveExecutionView';
import { WhatsAppAutomationView } from './components/WhatsAppAutomationView';
import { WhatsAppChatbotView } from './components/WhatsAppChatbotView';
import {
  ActionLogItem,
  HealthResponse,
  TaskCreateRequest,
  TaskResponse,
  WhatsAppTaskRequest,
  WhatsAppTaskResponse,
} from './types';
import {
  cancelTask,
  cancelWhatsAppTask,
  checkHealth,
  confirmWhatsAppSend,
  fetchTask,
  fetchTaskLogs,
  fetchWhatsAppTask,
  selectWhatsAppContact,
  sendApproval,
  startWhatsAppTask,
  submitTask,
} from './services/api';

export const App: React.FC = () => {
  const [activeMode, setActiveMode] = useState<ActiveViewMode>('chatbot');
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Generic agent state
  const [activeTask, setActiveTask] = useState<TaskResponse | null>(null);
  const [logs, setLogs] = useState<ActionLogItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isApprovalLoading, setIsApprovalLoading] = useState(false);

  // WhatsApp automation state
  const [whatsappTask, setWhatsappTask] = useState<WhatsAppTaskResponse | null>(null);
  const [isWhatsAppLoading, setIsWhatsAppLoading] = useState(false);

  // Initial health check
  const refreshHealth = async () => {
    try {
      const data = await checkHealth();
      setHealth(data);
    } catch (err) {
      console.error('Failed to load system health:', err);
    }
  };

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 20000);
    return () => clearInterval(interval);
  }, []);

  // Polling for generic active task updates
  useEffect(() => {
    if (!activeTask) return;

    const isTerminal = ['COMPLETED', 'FAILED', 'CANCELLED'].includes(activeTask.status);
    if (isTerminal) return;

    const pollInterval = setInterval(async () => {
      try {
        const [updatedTask, updatedLogs] = await Promise.all([
          fetchTask(activeTask.task_id),
          fetchTaskLogs(activeTask.task_id),
        ]);
        setActiveTask(updatedTask);
        setLogs(updatedLogs);
      } catch (err) {
        console.error('Error polling task updates:', err);
      }
    }, 1500);

    return () => clearInterval(pollInterval);
  }, [activeTask?.task_id, activeTask?.status]);

  // Polling for WhatsApp task updates
  useEffect(() => {
    if (!whatsappTask) return;

    const isTerminal = ['COMPLETED', 'FAILED', 'CANCELLED', 'CONTACT_NOT_FOUND', 'AWAITING_MANUAL_LOGIN'].includes(whatsappTask.status);
    const isPausedForInput = ['AMBIGUOUS_CONTACT', 'WAITING_FOR_SEND_APPROVAL'].includes(whatsappTask.status);

    // Continue polling when running, or check less frequently when waiting for user action
    const intervalTime = isPausedForInput ? 2500 : 1200;
    if (isTerminal) return;

    const pollInterval = setInterval(async () => {
      try {
        const updated = await fetchWhatsAppTask(whatsappTask.task_id);
        setWhatsappTask(updated);
      } catch (err) {
        console.error('Error polling WhatsApp task:', err);
      }
    }, intervalTime);

    return () => clearInterval(pollInterval);
  }, [whatsappTask?.task_id, whatsappTask?.status]);

  // Handle generic task creation
  const handleCreateTask = async (req: TaskCreateRequest) => {
    setIsSubmitting(true);
    try {
      const created = await submitTask(req);
      setActiveTask(created);
      setLogs([]);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle consequential action approval
  const handleApproveAction = async () => {
    if (!activeTask) return;
    setIsApprovalLoading(true);
    try {
      await sendApproval(activeTask.task_id, true);
      const [updatedTask, updatedLogs] = await Promise.all([
        fetchTask(activeTask.task_id),
        fetchTaskLogs(activeTask.task_id),
      ]);
      setActiveTask(updatedTask);
      setLogs(updatedLogs);
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setIsApprovalLoading(false);
    }
  };

  // Handle consequential action rejection
  const handleRejectAction = async (reason?: string) => {
    if (!activeTask) return;
    setIsApprovalLoading(true);
    try {
      await sendApproval(activeTask.task_id, false, reason);
      const [updatedTask, updatedLogs] = await Promise.all([
        fetchTask(activeTask.task_id),
        fetchTaskLogs(activeTask.task_id),
      ]);
      setActiveTask(updatedTask);
      setLogs(updatedLogs);
    } catch (err: any) {
      alert(`Rejection error: ${err.message}`);
    } finally {
      setIsApprovalLoading(false);
    }
  };

  // Handle generic task cancellation
  const handleCancelTask = async () => {
    if (!activeTask) return;
    try {
      await cancelTask(activeTask.task_id);
      const updated = await fetchTask(activeTask.task_id);
      setActiveTask(updated);
    } catch (err: any) {
      alert(`Cancellation failed: ${err.message}`);
    }
  };

  // =========================================================================
  // WhatsApp Automation Handlers
  // =========================================================================

  const handleStartWhatsAppTask = async (req: WhatsAppTaskRequest) => {
    setIsWhatsAppLoading(true);
    try {
      const created = await startWhatsAppTask(req);
      setWhatsappTask(created);
    } catch (err: any) {
      alert(`Failed to start WhatsApp workflow: ${err.message}`);
    } finally {
      setIsWhatsAppLoading(false);
    }
  };

  const handleSelectWhatsAppCandidate = async (selectedContact: string) => {
    if (!whatsappTask) return;
    try {
      const updated = await selectWhatsAppContact(whatsappTask.task_id, selectedContact);
      setWhatsappTask(updated);
    } catch (err: any) {
      alert(`Candidate selection failed: ${err.message}`);
    }
  };

  const handleConfirmWhatsAppSend = async (approved: boolean, reason?: string) => {
    if (!whatsappTask) return;
    try {
      const updated = await confirmWhatsAppSend(whatsappTask.task_id, approved, reason);
      setWhatsappTask(updated);
    } catch (err: any) {
      alert(`Send confirmation error: ${err.message}`);
    }
  };

  const handleCancelWhatsAppTask = async () => {
    if (!whatsappTask) return;
    try {
      const updated = await cancelWhatsAppTask(whatsappTask.task_id);
      setWhatsappTask(updated);
    } catch (err: any) {
      alert(`WhatsApp cancellation error: ${err.message}`);
    }
  };

  const handleResetWhatsAppTask = () => {
    setWhatsappTask(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        health={health}
        onRefreshHealth={refreshHealth}
        onNewTaskClick={() => {
          if (activeMode === 'agent') setActiveTask(null);
          else setWhatsappTask(null);
        }}
        activeMode={activeMode}
        onModeChange={(mode) => setActiveMode(mode)}
      />

      <main style={{ flex: 1 }}>
        {activeMode === 'chatbot' ? (
          <WhatsAppChatbotView health={health} />
        ) : activeMode === 'whatsapp' ? (
          <WhatsAppAutomationView
            task={whatsappTask}
            isLoading={isWhatsAppLoading}
            onStartTask={handleStartWhatsAppTask}
            onSelectCandidate={handleSelectWhatsAppCandidate}
            onConfirmSend={handleConfirmWhatsAppSend}
            onCancelTask={handleCancelWhatsAppTask}
            onResetTask={handleResetWhatsAppTask}
          />
        ) : !activeTask ? (
          <TaskCreationForm onSubmit={handleCreateTask} isLoading={isSubmitting} />
        ) : (
          <LiveExecutionView
            task={activeTask}
            logs={logs}
            onApproveAction={handleApproveAction}
            onRejectAction={handleRejectAction}
            onCancelTask={handleCancelTask}
            onNewTask={() => setActiveTask(null)}
            isApprovalLoading={isApprovalLoading}
          />
        )}
      </main>

      <footer
        style={{
          textAlign: 'center',
          padding: '1.5rem',
          fontSize: '0.8rem',
          color: '#64748b',
          borderTop: '1px solid var(--border-subtle)',
          marginTop: '2rem',
        }}
      >
        <p>
          AI Web Automation AgentOS &bull; WhatsApp Web CDP Integration &bull; Google Gemini API &bull; Human-in-the-Loop Send Approval
        </p>
      </footer>
    </div>
  );
};

export default App;


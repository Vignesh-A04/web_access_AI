import React, { useState } from 'react';
import { Globe, Terminal, Database, Sparkles, Play, ShieldAlert } from 'lucide-react';
import { TaskCreateRequest } from '../types';

interface TaskCreationFormProps {
  onSubmit: (req: TaskCreateRequest) => Promise<void>;
  isLoading: boolean;
}

export const TaskCreationForm: React.FC<TaskCreationFormProps> = ({ onSubmit, isLoading }) => {
  const [url, setUrl] = useState('http://127.0.0.1:8000/test-site');
  const [instruction, setInstruction] = useState(
    'Open the registration form on this authorized demo website, fill in the name, email, and message fields using the information I provide, select the business tier, accept the terms, and prepare the form for submission.'
  );
  const [taskDataStr, setTaskDataStr] = useState(
    JSON.stringify({ name: 'Alex Rivera', email: 'alex.rivera@example.com', account_type: 'business', message: 'Scale web automation workloads' }, null, 2)
  );
  const [headless, setHeadless] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);

  const applyTemplate = (
    templateUrl: string,
    templateInstruction: string,
    templateData: Record<string, any> | null
  ) => {
    setUrl(templateUrl);
    setInstruction(templateInstruction);
    setTaskDataStr(templateData ? JSON.stringify(templateData, null, 2) : '');
    setValidationError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    if (!url.trim()) {
      setValidationError('Target website URL is required');
      return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setValidationError('URL must start with http:// or https://');
      return;
    }

    if (!instruction.trim()) {
      setValidationError('Please provide a natural-language task instruction');
      return;
    }

    let parsedData: Record<string, any> | undefined = undefined;
    if (taskDataStr.trim()) {
      try {
        parsedData = JSON.parse(taskDataStr);
      } catch (err) {
        setValidationError('Invalid JSON in optional task data field. Please correct the syntax.');
        return;
      }
    }

    try {
      await onSubmit({
        url: url.trim(),
        instruction: instruction.trim(),
        task_data: parsedData,
        headless,
      });
    } catch (err: any) {
      setValidationError(err.message || 'Failed to submit task');
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '2rem', maxWidth: '850px', margin: '2rem auto' }}>
      <div style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
          <Sparkles size={20} color="#0ea5e9" />
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f8fafc' }}>
            Start an Autonomous Automation Task
          </h2>
        </div>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
          Provide any target web URL and describe your task in natural language. The agent inspects the page, plans actions, and safely executes them.
        </p>
      </div>

      {/* Quick Template Suggestion Pills */}
      <div style={{ marginBottom: '1.75rem' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b', display: 'block', marginBottom: '0.6rem' }}>
          Quick Example Presets:
        </span>
        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => applyTemplate(
              'http://127.0.0.1:8000/test-site',
              'Open the registration form on this authorized demo website, fill in the name, email, and message fields using the information I provide, select the business tier, accept the terms, and prepare the form for submission.',
              { name: 'Alex Rivera', email: 'alex.rivera@example.com', account_type: 'business', message: 'Scale web automation workloads' }
            )}
            style={{
              background: 'rgba(14, 165, 233, 0.1)',
              border: '1px solid rgba(14, 165, 233, 0.3)',
              color: '#38bdf8',
              padding: '0.4rem 0.8rem',
              borderRadius: '20px',
              fontSize: '0.8rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            📋 Demo Form Fill & Submit
          </button>

          <button
            type="button"
            onClick={() => applyTemplate(
              'http://127.0.0.1:8000/test-site',
              'Inspect this website and extract the inventory table data, then tell me what items are listed and their current status.',
              null
            )}
            style={{
              background: 'rgba(139, 92, 246, 0.1)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#c084fc',
              padding: '0.4rem 0.8rem',
              borderRadius: '20px',
              fontSize: '0.8rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            📊 Extract Inventory Table
          </button>

          <button
            type="button"
            onClick={() => applyTemplate(
              'https://example.com',
              'Inspect this website and tell me what information its main page contains, including heading and purpose.',
              null
            )}
            style={{
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              color: '#34d399',
              padding: '0.4rem 0.8rem',
              borderRadius: '20px',
              fontSize: '0.8rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            🌐 Inspect Example.com
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {/* URL Input */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.4rem' }}>
            <Globe size={16} color="#38bdf8" />
            Website URL
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com or http://127.0.0.1:8000/test-site"
            style={{
              width: '100%',
              padding: '0.75rem 1rem',
              background: 'var(--bg-input)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '8px',
              color: '#f8fafc',
              fontSize: '0.9rem',
              outline: 'none',
              fontFamily: 'var(--font-mono)'
            }}
          />
        </div>

        {/* Natural Language Instruction */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.4rem' }}>
            <Terminal size={16} color="#a855f7" />
            Natural Language Instruction
          </label>
          <textarea
            rows={4}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Describe step-by-step what the agent should inspect, fill, or extract..."
            style={{
              width: '100%',
              padding: '0.75rem 1rem',
              background: 'var(--bg-input)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '8px',
              color: '#f8fafc',
              fontSize: '0.9rem',
              outline: 'none',
              fontFamily: 'inherit',
              lineHeight: 1.5,
              resize: 'vertical'
            }}
          />
        </div>

        {/* Optional Task Data */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', fontWeight: 600, color: '#cbd5e1' }}>
              <Database size={16} color="#10b981" />
              Optional User Input Data (JSON)
            </label>
            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Used to map values to form fields</span>
          </div>
          <textarea
            rows={3}
            value={taskDataStr}
            onChange={(e) => setTaskDataStr(e.target.value)}
            placeholder='{"key": "value"}'
            style={{
              width: '100%',
              padding: '0.75rem 1rem',
              background: 'var(--bg-input)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '8px',
              color: '#f8fafc',
              fontSize: '0.85rem',
              outline: 'none',
              fontFamily: 'var(--font-mono)'
            }}
          />
        </div>

        {/* Headless Mode & Security Warning */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 0', marginBottom: '1.25rem', borderTop: '1px solid var(--border-subtle)', flexWrap: 'wrap', gap: '0.5rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.85rem', color: '#cbd5e1' }}>
            <input
              type="checkbox"
              checked={headless}
              onChange={(e) => setHeadless(e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#0ea5e9' }}
            />
            <span>Headless Browser (Run without visible browser window)</span>
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: '#94a3b8' }}>
            <ShieldAlert size={14} color="#f59e0b" />
            <span>Strict SSRF protection active</span>
          </div>
        </div>

        {/* Validation Error Banner */}
        {validationError && (
          <div style={{ background: 'rgba(244, 63, 94, 0.15)', border: '1px solid rgba(244, 63, 94, 0.4)', color: '#fb7185', padding: '0.75rem 1rem', borderRadius: '8px', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
            {validationError}
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading}
          className="btn-primary"
          style={{
            width: '100%',
            padding: '0.85rem 1.5rem',
            borderRadius: '10px',
            fontSize: '1rem',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
            cursor: isLoading ? 'not-allowed' : 'pointer'
          }}
        >
          <Play size={18} fill="currentColor" />
          {isLoading ? 'Initializing Automation...' : 'Launch Automation Task'}
        </button>
      </form>
    </div>
  );
};

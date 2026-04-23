import React from 'react';
import './ModeSelector.css';

const ModeSelector = ({ mode, loading, onModeChange }) => {
  const modes = [
    { id: 'extract-gpt', label: 'Extract (GPT)' },
    { id: 'extract', label: 'Extract Q&A' },
    { id: 'evaluate', label: 'Evaluate (PDFs)' },
    { id: 'evaluate-excel', label: 'Evaluate (Excel)' },
    { id: 'clean-excel', label: 'Clean Excel' },
  ];

  return (
    <div className="mode-tabs">
      {modes.map((m) => (
        <button
          key={m.id}
          type="button"
          className={`mode-tab ${mode === m.id ? 'active' : ''}`}
          onClick={() => onModeChange(m.id)}
          disabled={loading}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
};

export default ModeSelector;

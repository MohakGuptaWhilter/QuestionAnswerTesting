import React, { useRef } from 'react';
import '../common/FileInputGroup.css';
import '../common/AgentConfig.css';
import './ExcelProcessor.css';

const ExcelProcessor = ({
  mode, // 'evaluate-excel' or 'clean-excel'
  qaExcel,
  agentId,
  deploymentSlug,
  loading,
  error,
  success,
  onExcelChange,
  onAgentIdChange,
  onDeploymentSlugChange,
  onSubmit,
  canSubmit,
}) => {
  const excelInputRef = useRef(null);
  const isEvaluateMode = mode === 'evaluate-excel';

  const titles = {
    'evaluate-excel': 'Evaluate via AI (Excel)',
    'clean-excel': 'Clean Questions in Excel',
  };

  const infos = {
    'evaluate-excel': (
      <>
        Upload the Excel file produced by <strong>Extract Q&amp;A</strong>. Each
        question will be sent to the knowledge base API and the response
        compared against the correct answer already in the file.
      </>
    ),
    'clean-excel': (
      <>
        Upload an Excel file produced by <strong>Extract Q&amp;A</strong>. Noise
        such as anchor tags, marketing text, and page-break markers will be
        stripped from the <strong>Question</strong> column. All other columns
        are left untouched.
      </>
    ),
  };

  const buttonLabels = {
    'evaluate-excel': { idle: 'Evaluate & Download Results', busy: 'Evaluating… this may take a while' },
    'clean-excel': { idle: 'Clean & Download Excel', busy: 'Cleaning...' },
  };

  const successMessages = {
    'evaluate-excel': 'Evaluation complete. Results Excel downloaded.',
    'clean-excel': 'Questions cleaned. Cleaned Excel downloaded.',
  };

  return (
    <div className="excel-processor-form">
      <h2>{titles[mode]}</h2>

      <div className="evaluate-info">
        {infos[mode]}
      </div>

      <div className="file-input-group">
        <label htmlFor="qaExcel">Q&amp;A Excel file *</label>
        <input
          ref={excelInputRef}
          id="qaExcel"
          type="file"
          accept=".xlsx,.xls"
          onChange={onExcelChange}
          disabled={loading}
          className="file-input"
        />
        {qaExcel && (
          <div className="file-info">
            {qaExcel.name} ({(qaExcel.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

      {isEvaluateMode && (
        <div className="agent-config">
          <div className="file-input-group">
            <label htmlFor="agentId">Agent ID *</label>
            <input
              id="agentId"
              type="text"
              value={agentId}
              onChange={(e) => onAgentIdChange(e.target.value)}
              disabled={loading}
              className="text-input"
              placeholder="e.g. 524829a7-ad2d-4bd4-b094-3a8ef5b62a9e"
              autoComplete="off"
            />
          </div>
          <div className="file-input-group">
            <label htmlFor="deploymentSlug">Deployment Slug *</label>
            <input
              id="deploymentSlug"
              type="text"
              value={deploymentSlug}
              onChange={(e) => onDeploymentSlugChange(e.target.value)}
              disabled={loading}
              className="text-input"
              placeholder="e.g. test123"
              autoComplete="off"
            />
          </div>
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      {success && (
        <div className="success-message">
          {successMessages[mode]}
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !canSubmit}
        onClick={onSubmit}
        className={`submit-button ${isEvaluateMode ? 'evaluate' : ''}`}
      >
        {loading ? buttonLabels[mode].busy : buttonLabels[mode].idle}
      </button>
    </div>
  );
};

export default ExcelProcessor;

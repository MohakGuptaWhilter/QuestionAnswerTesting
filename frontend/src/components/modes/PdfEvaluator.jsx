import React, { useRef } from 'react';
import '../common/FileInputGroup.css';
import '../common/AgentConfig.css';
import './PdfEvaluator.css';

const PdfEvaluator = ({
  questionsPdf,
  answersPdf,
  agentId,
  deploymentSlug,
  loading,
  error,
  success,
  onPdfChange,
  onAgentIdChange,
  onDeploymentSlugChange,
  onSubmit,
  canSubmit,
}) => {
  const questionsInputRef = useRef(null);
  const answersInputRef = useRef(null);

  return (
    <div className="pdf-evaluator-form">
      <h2>Evaluate via AI (PDFs)</h2>

      <div className="evaluate-info">
        Each question is sent to the knowledge base API and the response is
        compared against the correct answer from the answer key PDF. Results
        are colour-coded in the downloaded Excel.
      </div>

      <div className="file-input-group">
        <label htmlFor="questions">Questions PDF *</label>
        <input
          ref={questionsInputRef}
          id="questions"
          type="file"
          accept=".pdf"
          onChange={(e) => onPdfChange(e, 'Questions PDF', 'questions')}
          disabled={loading}
          className="file-input"
        />
        {questionsPdf && (
          <div className="file-info">
            {questionsPdf.name} ({(questionsPdf.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

      <div className="file-input-group">
        <label htmlFor="answers">Answers PDF *</label>
        <input
          ref={answersInputRef}
          id="answers"
          type="file"
          accept=".pdf"
          onChange={(e) => onPdfChange(e, 'Answers PDF', 'answers')}
          disabled={loading}
          className="file-input"
        />
        {answersPdf && (
          <div className="file-info">
            {answersPdf.name} ({(answersPdf.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

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

      {error && <div className="error-message">{error}</div>}

      {success && (
        <div className="success-message">
          Evaluation complete. Results Excel downloaded.
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !canSubmit}
        onClick={onSubmit}
        className="submit-button evaluate"
      >
        {loading ? 'Evaluating… this may take a while' : 'Evaluate & Download Results'}
      </button>
    </div>
  );
};

export default PdfEvaluator;

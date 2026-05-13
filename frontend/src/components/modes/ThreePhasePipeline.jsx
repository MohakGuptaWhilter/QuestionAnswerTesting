import React from 'react';
import '../common/FileInputGroup.css';
import './ThreePhasePipeline.css';

const MODEL_OPTIONS = [
  { value: 'claude-haiku',              label: 'Claude Haiku (fast, default)' },
  { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
  { value: 'claude-sonnet-4-6',         label: 'Claude Sonnet (accurate)' },
  { value: 'gpt-4o-mini',              label: 'GPT-4o-mini (fast, cheap)' },
  { value: 'gpt-4o',                   label: 'GPT-4o (best accuracy)' },
  { value: 'qwen2.5vl:7b',             label: 'Qwen2.5-VL 7B (local / Ollama)' },
];

const ThreePhasePipeline = ({
  singlePdf,
  model,
  loading,
  error,
  success,
  onPdfChange,
  onModelChange,
  onSubmit,
  canSubmit,
}) => (
  <div className="three-phase-form">
    <h2>Three-Phase Extraction</h2>
    <p className="form-description">
      Upload a single exam PDF. Phase 1 classifies each page (question, answer
      key, rubric answer, filler, or continuation). Phase 2 sends each relevant
      page to the vision model for structured JSON extraction. Phase 3 joins
      questions to answers by question number and exports to Excel.
    </p>

    <div className="pipeline-phases">
      <span className="phase-badge phase-1">Phase 1 — Page Classification</span>
      <span className="phase-badge phase-2">Phase 2 — Structured OCR</span>
      <span className="phase-badge phase-3">Phase 3 — Join + Export</span>
    </div>

    <div className="file-input-group">
      <label htmlFor="three-phase-pdf">PDF *</label>
      <input
        id="three-phase-pdf"
        type="file"
        accept=".pdf"
        onChange={onPdfChange}
        disabled={loading}
        className="file-input"
      />
      {singlePdf && (
        <div className="file-info">
          {singlePdf.name} ({(singlePdf.size / 1024).toFixed(1)} KB)
        </div>
      )}
    </div>

    <div className="file-input-group">
      <label htmlFor="three-phase-model">Vision Model</label>
      <select
        id="three-phase-model"
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        disabled={loading}
        className="model-select"
      >
        {MODEL_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>

    {error && <div className="error-message">{error}</div>}

    {success && (
      <div className="success-message">
        Extraction complete — your Excel file has been downloaded.
      </div>
    )}

    <button
      type="submit"
      disabled={loading || !canSubmit}
      onClick={onSubmit}
      className="submit-button three-phase"
    >
      {loading ? 'Processing…' : 'Extract to Excel'}
    </button>
  </div>
);

export default ThreePhasePipeline;

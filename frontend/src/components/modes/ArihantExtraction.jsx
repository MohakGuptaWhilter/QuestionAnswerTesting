import React from 'react';
import '../common/FileInputGroup.css';
import './ArihantExtraction.css';

const MODEL_OPTIONS = [
  { value: 'claude-haiku',               label: 'Claude Haiku (fast, default)' },
  { value: 'claude-haiku-4-5-20251001',  label: 'Claude Haiku 4.5' },
  { value: 'claude-sonnet-4-6',          label: 'Claude Sonnet (accurate)' },
  { value: 'gpt-4o-mini',               label: 'GPT-4o-mini (fast, cheap)' },
  { value: 'gpt-4o',                    label: 'GPT-4o (best accuracy)' },
  { value: 'qwen2.5vl:7b',              label: 'Qwen2.5-VL 7B (local / Ollama)' },
];

const ArihantExtraction = ({
  singlePdf,
  model,
  loading,
  error,
  success,
  onPdfChange,
  onModelChange,
  onSubmit,
  canSubmit,
}) => {
  return (
    <div className="arihant-form">
      <h2>Arihant PDF Extraction</h2>
      <p className="form-description">
        Upload an Arihant PDF. The pipeline classifies and extracts questions
        and solutions, then exports the results as an Excel file.
      </p>

      <div className="file-input-group">
        <label htmlFor="arihant-pdf">PDF *</label>
        <input
          id="arihant-pdf"
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
        <label htmlFor="arihant-model">Vision Model</label>
        <select
          id="arihant-model"
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
        className="submit-button arihant"
      >
        {loading ? 'Extracting…' : 'Extract to Excel'}
      </button>
    </div>
  );
};

export default ArihantExtraction;

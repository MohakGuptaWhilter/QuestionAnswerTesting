import React, { useRef } from 'react';
import '../common/FileInputGroup.css';
import './GeneralPurposeExtraction.css';

const MODEL_OPTIONS = [
  { value: 'qwen2.5vl:7b',              label: 'Qwen2.5-VL 7B (local / Ollama)' },
  { value: 'gpt-4o-mini',               label: 'GPT-4o-mini (fast, cheap)' },
  { value: 'gpt-4o',                    label: 'GPT-4o (best accuracy)' },
  { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku (fast)' },
  { value: 'claude-sonnet-4-6',         label: 'Claude Sonnet (accurate)' },
];

const TYPE_LABELS = {
  theory:    { label: 'Theory',    cls: 'badge-theory' },
  questions: { label: 'Questions', cls: 'badge-questions' },
  solutions: { label: 'Solutions', cls: 'badge-solutions' },
  misc:      { label: 'Misc',      cls: 'badge-misc' },
};

const GeneralPurposeExtraction = ({
  singlePdf,
  model,
  loading,
  error,
  result,
  onPdfChange,
  onModelChange,
  onSubmit,
  canSubmit,
}) => {
  const inputRef = useRef(null);

  return (
    <div className="gpe-form">
      <h2>General Purpose Extraction</h2>
      <p className="form-description">
        Upload a PDF. Each page is classified as <strong>theory</strong>,{' '}
        <strong>questions</strong>, <strong>solutions</strong>, or{' '}
        <strong>misc</strong>. Question and solution pages are also analysed for
        single- vs. multi-column layout, and cropped images are saved to{' '}
        <code>questions/</code> and <code>solutions/</code>.
      </p>

      <div className="file-input-group">
        <label htmlFor="gpe-pdf">PDF *</label>
        <input
          ref={inputRef}
          id="gpe-pdf"
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
        <label htmlFor="gpe-model">Vision Model</label>
        <select
          id="gpe-model"
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

      <button
        type="submit"
        disabled={loading || !canSubmit}
        onClick={onSubmit}
        className="submit-button gpe"
      >
        {loading ? 'Classifying pages…' : 'Classify & Extract'}
      </button>

      {result && (
        <div className="gpe-results">
          <h3>Results — {result.total_pages} page{result.total_pages !== 1 ? 's' : ''}</h3>
          <div className="gpe-table-wrapper">
            <table className="gpe-table">
              <thead>
                <tr>
                  <th>Page</th>
                  <th>Type</th>
                  <th>Layout</th>
                  <th>Cols</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {result.pages.map((p) => {
                  const typeMeta = TYPE_LABELS[p.page_type] || { label: p.page_type, cls: '' };
                  return (
                    <tr key={p.page}>
                      <td className="gpe-cell-center">{p.page}</td>
                      <td className="gpe-cell-center">
                        <span className={`gpe-badge ${typeMeta.cls}`}>{typeMeta.label}</span>
                      </td>
                      <td className="gpe-cell-center">
                        {p.layout ? p.layout.type.replace('_', ' ') : '—'}
                      </td>
                      <td className="gpe-cell-center">
                        {p.layout ? p.layout.columns : '—'}
                      </td>
                      <td className="gpe-cell-center">
                        {(p.confidence * 100).toFixed(0)}%
                      </td>
                      <td className="gpe-cell-reason">{p.reason}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default GeneralPurposeExtraction;

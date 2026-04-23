import React, { useRef } from 'react';
import '../common/FileInputGroup.css';
import './GptExtractor.css';

const GptExtractor = ({
  singlePdf,
  gptModel,
  loading,
  error,
  success,
  onPdfChange,
  onModelChange,
  onSubmit,
  canSubmit,
}) => {
  const singlePdfInputRef = useRef(null);

  return (
    <div className="gpt-extractor-form">
      <h2>Extract Q&A — GPT-4o-mini (Single PDF)</h2>

      <div className="evaluate-info">
        Upload a single PDF. GPT-4o-mini reads the document in page chunks and
        extracts <strong>all</strong> questions — including worked{' '}
        <strong>Examples</strong> with inline solutions and numbered practice
        problems whose answers appear in a separate <strong>Solutions</strong>{' '}
        section. Requires <code>OPENAI_API_KEY</code> to be set on the server.
      </div>

      <div className="file-input-group">
        <label htmlFor="singlePdf">Textbook PDF *</label>
        <input
          ref={singlePdfInputRef}
          id="singlePdf"
          type="file"
          accept=".pdf"
          onChange={(e) => onPdfChange(e, 'PDF')}
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
        <label htmlFor="gptModel">Model</label>
        <select
          id="gptModel"
          value={gptModel}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={loading}
          className="text-input"
        >
          <option value="gpt-4o-mini">gpt-4o-mini (fast, cheap)</option>
          <option value="gpt-4o">gpt-4o (best accuracy for complex math)</option>
        </select>
      </div>

      {error && <div className="error-message">{error}</div>}

      {success && (
        <div className="success-message">
          GPT extraction complete. Excel downloaded.
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !canSubmit}
        onClick={onSubmit}
        className="submit-button gpt"
      >
        {loading ? 'Extracting with GPT… this may take a while' : 'Extract & Download Excel'}
      </button>
    </div>
  );
};

export default GptExtractor;

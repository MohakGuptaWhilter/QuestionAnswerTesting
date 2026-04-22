import React, { useState, useRef } from 'react';
import './PDFUploader.css';

const PDFUploader = () => {
  // 'extract' | 'evaluate' | 'evaluate-excel' | 'clean-excel'
  const [mode, setMode] = useState('extract');
  const [questionsPdf, setQuestionsPdf] = useState(null);
  const [answersPdf, setAnswersPdf] = useState(null);
  const [qaExcel, setQaExcel] = useState(null);
  const [agentId, setAgentId] = useState('');
  const [deploymentSlug, setDeploymentSlug] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const questionsInputRef = useRef(null);
  const answersInputRef = useRef(null);
  const excelInputRef = useRef(null);

  const handleModeChange = (newMode) => {
    setMode(newMode);
    setError(null);
    setSuccess(false);
  };

  const handlePdfChange = (e, setter, label) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setError(`${label}: please select a PDF file.`);
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError(`${label}: file exceeds the 50 MB limit.`);
      return;
    }
    setter(file);
    setError(null);
  };

  const handleExcelChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      setError('Please select an Excel file (.xlsx).');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setError('File exceeds the 50 MB limit.');
      return;
    }
    setQaExcel(file);
    setError(null);
  };

  const resetInputs = () => {
    setQuestionsPdf(null);
    setAnswersPdf(null);
    setQaExcel(null);
    if (questionsInputRef.current) questionsInputRef.current.value = '';
    if (answersInputRef.current) answersInputRef.current.value = '';
    if (excelInputRef.current) excelInputRef.current.value = '';
  };

  const triggerDownload = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  // ── mode handlers ──────────────────────────────────────────────────────────

  const handleExtract = async () => {
    const fd = new FormData();
    fd.append('questions_pdf', questionsPdf);
    fd.append('answers_pdf', answersPdf);

    const res = await fetch('/api/extract', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to extract Q&A');
    }
    triggerDownload(await res.blob(), 'qa_extract.xlsx');
  };

  const handleEvaluate = async () => {
    const fd = new FormData();
    fd.append('questions_pdf', questionsPdf);
    fd.append('answers_pdf', answersPdf);
    fd.append('agent_id', agentId.trim());
    fd.append('deployment_slug', deploymentSlug.trim());

    const res = await fetch('/api/evaluate', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${res.status}`);
    }
    triggerDownload(await res.blob(), 'evaluation_results.xlsx');
  };

  const handleCleanExcel = async () => {
    const fd = new FormData();
    fd.append('qa_excel', qaExcel);

    const res = await fetch('/api/clean-excel', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${res.status}`);
    }
    triggerDownload(await res.blob(), 'cleaned_qa.xlsx');
  };

  const handleEvaluateExcel = async () => {
    const fd = new FormData();
    fd.append('qa_excel', qaExcel);
    fd.append('agent_id', agentId.trim());
    fd.append('deployment_slug', deploymentSlug.trim());

    const res = await fetch('/api/evaluate-excel', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${res.status}`);
    }
    triggerDownload(await res.blob(), 'evaluation_results.xlsx');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (mode === 'extract' && (!questionsPdf || !answersPdf)) {
      setError('Please select both PDF files.');
      return;
    }
    if (mode === 'evaluate' && (!questionsPdf || !answersPdf)) {
      setError('Please select both PDF files.');
      return;
    }
    if ((mode === 'evaluate-excel' || mode === 'clean-excel') && !qaExcel) {
      setError('Please select an Excel file.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      if (mode === 'extract') await handleExtract();
      else if (mode === 'evaluate') await handleEvaluate();
      else if (mode === 'evaluate-excel') await handleEvaluateExcel();
      else await handleCleanExcel();
      setSuccess(true);
      resetInputs();
    } catch (err) {
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  const canSubmit =
    mode === 'extract'
      ? questionsPdf && answersPdf
      : mode === 'evaluate'
      ? questionsPdf && answersPdf && agentId.trim() && deploymentSlug.trim()
      : mode === 'clean-excel'
      ? !!qaExcel
      : qaExcel && agentId.trim() && deploymentSlug.trim();

  const isEvaluateMode = mode === 'evaluate' || mode === 'evaluate-excel';

  // ── labels / button text ───────────────────────────────────────────────────

  const titles = {
    extract: 'Extract Q&A to Excel',
    evaluate: 'Evaluate via AI (PDFs)',
    'evaluate-excel': 'Evaluate via AI (Excel)',
    'clean-excel': 'Clean Questions in Excel',
  };

  const buttonLabels = {
    extract: { idle: 'Extract & Download Excel', busy: 'Processing...' },
    evaluate: { idle: 'Evaluate & Download Results', busy: 'Evaluating… this may take a while' },
    'evaluate-excel': { idle: 'Evaluate & Download Results', busy: 'Evaluating… this may take a while' },
    'clean-excel': { idle: 'Clean & Download Excel', busy: 'Cleaning...' },
  };

  return (
    <div className="uploader-container">
      {/* ── Mode tabs ── */}
      <div className="mode-tabs">
        <button
          type="button"
          className={`mode-tab ${mode === 'extract' ? 'active' : ''}`}
          onClick={() => handleModeChange('extract')}
          disabled={loading}
        >
          Extract Q&amp;A
        </button>
        <button
          type="button"
          className={`mode-tab ${mode === 'evaluate' ? 'active' : ''}`}
          onClick={() => handleModeChange('evaluate')}
          disabled={loading}
        >
          Evaluate (PDFs)
        </button>
        <button
          type="button"
          className={`mode-tab ${mode === 'evaluate-excel' ? 'active' : ''}`}
          onClick={() => handleModeChange('evaluate-excel')}
          disabled={loading}
        >
          Evaluate (Excel)
        </button>
        <button
          type="button"
          className={`mode-tab ${mode === 'clean-excel' ? 'active' : ''}`}
          onClick={() => handleModeChange('clean-excel')}
          disabled={loading}
        >
          Clean Excel
        </button>
      </div>

      <form onSubmit={handleSubmit} className="upload-form">
        <h2>{titles[mode]}</h2>

        {/* Info banners */}
        {mode === 'evaluate' && (
          <div className="evaluate-info">
            Each question is sent to the knowledge base API and the response is
            compared against the correct answer from the answer key PDF. Results
            are colour-coded in the downloaded Excel.
          </div>
        )}
        {mode === 'evaluate-excel' && (
          <div className="evaluate-info">
            Upload the Excel file produced by <strong>Extract Q&amp;A</strong>. Each
            question will be sent to the knowledge base API and the response
            compared against the correct answer already in the file.
          </div>
        )}
        {mode === 'clean-excel' && (
          <div className="evaluate-info">
            Upload an Excel file produced by <strong>Extract Q&amp;A</strong>. Noise
            such as anchor tags, marketing text, and page-break markers will be
            stripped from the <strong>Question</strong> column. All other columns
            are left untouched.
          </div>
        )}

        {/* PDF inputs (extract + evaluate modes) */}
        {(mode === 'extract' || mode === 'evaluate') && (
          <>
            <div className="file-input-group">
              <label htmlFor="questions">Questions PDF *</label>
              <input
                ref={questionsInputRef}
                id="questions"
                type="file"
                accept=".pdf"
                onChange={(e) => handlePdfChange(e, setQuestionsPdf, 'Questions PDF')}
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
                onChange={(e) => handlePdfChange(e, setAnswersPdf, 'Answers PDF')}
                disabled={loading}
                className="file-input"
              />
              {answersPdf && (
                <div className="file-info">
                  {answersPdf.name} ({(answersPdf.size / 1024).toFixed(1)} KB)
                </div>
              )}
            </div>
          </>
        )}

        {/* Excel input (evaluate-excel + clean-excel modes) */}
        {(mode === 'evaluate-excel' || mode === 'clean-excel') && (
          <div className="file-input-group">
            <label htmlFor="qaExcel">Q&amp;A Excel file *</label>
            <input
              ref={excelInputRef}
              id="qaExcel"
              type="file"
              accept=".xlsx,.xls"
              onChange={handleExcelChange}
              disabled={loading}
              className="file-input"
            />
            {qaExcel && (
              <div className="file-info">
                {qaExcel.name} ({(qaExcel.size / 1024).toFixed(1)} KB)
              </div>
            )}
          </div>
        )}

        {/* Agent config (evaluate modes) */}
        {isEvaluateMode && (
          <>
            <div className="file-input-group">
              <label htmlFor="agentId">Agent ID *</label>
              <input
                id="agentId"
                type="text"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
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
                onChange={(e) => setDeploymentSlug(e.target.value)}
                disabled={loading}
                className="text-input"
                placeholder="e.g. test123"
                autoComplete="off"
              />
            </div>
          </>
        )}

        {error && <div className="error-message">{error}</div>}

        {success && (
          <div className="success-message">
            {mode === 'extract'
              ? 'Successfully extracted Q&A. Excel downloaded.'
              : mode === 'clean-excel'
              ? 'Questions cleaned. Cleaned Excel downloaded.'
              : 'Evaluation complete. Results Excel downloaded.'}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !canSubmit}
          className={`submit-button ${isEvaluateMode ? 'evaluate' : ''}`}
        >
          {loading ? buttonLabels[mode].busy : buttonLabels[mode].idle}
        </button>
      </form>

    </div>
  );
};

export default PDFUploader;

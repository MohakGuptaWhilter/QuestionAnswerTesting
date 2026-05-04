import React, { useState } from 'react';
import ModeSelector from './common/ModeSelector';
import PdfExtractor from './modes/PdfExtractor';
import PdfEvaluator from './modes/PdfEvaluator';
import ExcelProcessor from './modes/ExcelProcessor';
import PdfToImages from './modes/PdfToImages';
import './PDFUploader.css';

const PDFUploader = () => {
  // State management
  const [mode, setMode] = useState('extract');
  const [questionsPdf, setQuestionsPdf] = useState(null);
  const [answersPdf, setAnswersPdf] = useState(null);
  const [qaExcel, setQaExcel] = useState(null);
  const [agentId, setAgentId] = useState('');
  const [deploymentSlug, setDeploymentSlug] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [pdfToImagesResult, setPdfToImagesResult] = useState(null);

  // ── Mode change handler ────────────────────────────────────────────────────

  const handleModeChange = (newMode) => {
    setMode(newMode);
    setError(null);
    setSuccess(false);
  };

  // ── File handlers ──────────────────────────────────────────────────────────

  const handlePdfChange = (e, setter, label) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setError(`${label}: please select a PDF file.`);
      return;
    }
    if (file.size > 500 * 1024 * 1024) {
      setError(`${label}: file exceeds the 500 MB limit.`);
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
    if (file.size > 500 * 1024 * 1024) {
      setError('File exceeds the 500 MB limit.');
      return;
    }
    setQaExcel(file);
    setError(null);
  };

  const resetInputs = () => {
    setQuestionsPdf(null);
    setAnswersPdf(null);
    setQaExcel(null);
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

  // ── API handlers (mode-specific logic) ─────────────────────────────────────

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

  const handlePdfToImages = async () => {
    const fd = new FormData();
    fd.append('questions_pdf', questionsPdf);
    fd.append('answers_pdf', answersPdf);

    const res = await fetch('/api/pdf-to-images', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${res.status}`);
    }
    triggerDownload(await res.blob(), 'questions_output.xlsx');
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

  // ── Unified submit handler ─────────────────────────────────────────────────

  const handleSubmit = async () => {
    // Validation
    if ((mode === 'extract' || mode === 'evaluate' || mode === 'pdf-to-images') && (!questionsPdf || !answersPdf)) {
      setError('Please select both PDF files.');
      return;
    }
    if ((mode === 'evaluate-excel' || mode === 'clean-excel') && !qaExcel) {
      setError('Please select an Excel file.');
      return;
    }
    if ((mode === 'evaluate' || mode === 'evaluate-excel') && (!agentId.trim() || !deploymentSlug.trim())) {
      setError('Please provide Agent ID and Deployment Slug.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      // Route to appropriate handler based on mode
      if (mode === 'extract') await handleExtract();
      else if (mode === 'pdf-to-images') await handlePdfToImages();
      else if (mode === 'evaluate') await handleEvaluate();
      else if (mode === 'evaluate-excel') await handleEvaluateExcel();
      else if (mode === 'clean-excel') await handleCleanExcel();

      setSuccess(true);
      resetInputs();
    } catch (err) {
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  // ── Compute canSubmit logic ────────────────────────────────────────────────

  const canSubmit =
    mode === 'extract' || mode === 'pdf-to-images'
      ? questionsPdf && answersPdf
      : mode === 'evaluate'
      ? questionsPdf && answersPdf && agentId.trim() && deploymentSlug.trim()
      : mode === 'clean-excel'
      ? !!qaExcel
      : qaExcel && agentId.trim() && deploymentSlug.trim(); // evaluate-excel

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="uploader-container">
      <ModeSelector mode={mode} loading={loading} onModeChange={handleModeChange} />

      {mode === 'extract' && (
        <PdfExtractor
          questionsPdf={questionsPdf}
          answersPdf={answersPdf}
          loading={loading}
          error={error}
          success={success}
          onPdfChange={(e, label, fileType) => {
            if (fileType === 'questions') handlePdfChange(e, setQuestionsPdf, label);
            else handlePdfChange(e, setAnswersPdf, label);
          }}
          onSubmit={handleSubmit}
          canSubmit={canSubmit}
        />
      )}

      {mode === 'pdf-to-images' && (
        <PdfToImages
          questionsPdf={questionsPdf}
          answersPdf={answersPdf}
          loading={loading}
          error={error}
          success={success}
          result={pdfToImagesResult}
          onPdfChange={(e, label, fileType) => {
            if (fileType === 'questions') handlePdfChange(e, setQuestionsPdf, label);
            else handlePdfChange(e, setAnswersPdf, label);
          }}
          onSubmit={handleSubmit}
          canSubmit={canSubmit}
        />
      )}

      {mode === 'evaluate' && (
        <PdfEvaluator
          questionsPdf={questionsPdf}
          answersPdf={answersPdf}
          agentId={agentId}
          deploymentSlug={deploymentSlug}
          loading={loading}
          error={error}
          success={success}
          onPdfChange={(e, label, fileType) => {
            if (fileType === 'questions') handlePdfChange(e, setQuestionsPdf, label);
            else handlePdfChange(e, setAnswersPdf, label);
          }}
          onAgentIdChange={setAgentId}
          onDeploymentSlugChange={setDeploymentSlug}
          onSubmit={handleSubmit}
          canSubmit={canSubmit}
        />
      )}

      {(mode === 'evaluate-excel' || mode === 'clean-excel') && (
        <ExcelProcessor
          mode={mode}
          qaExcel={qaExcel}
          agentId={agentId}
          deploymentSlug={deploymentSlug}
          loading={loading}
          error={error}
          success={success}
          onExcelChange={handleExcelChange}
          onAgentIdChange={setAgentId}
          onDeploymentSlugChange={setDeploymentSlug}
          onSubmit={handleSubmit}
          canSubmit={canSubmit}
        />
      )}
    </div>
  );
};

export default PDFUploader;



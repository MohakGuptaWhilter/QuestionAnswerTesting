import React, { useRef } from 'react';
import '../common/FileInputGroup.css';
import './ValidateQA.css';

const ValidateQA = ({
  questionsPdf,
  answersPdf,
  excelFile,
  loading,
  error,
  success,
  onPdfChange,
  onExcelChange,
  onSubmit,
  canSubmit,
}) => {
  const questionsInputRef = useRef(null);
  const answersInputRef   = useRef(null);
  const excelInputRef     = useRef(null);

  return (
    <div className="validate-qa-form">
      <h2>Validate Q&amp;A</h2>
      <p className="form-description">
        Upload the original exam PDFs and an Excel sheet to validate.
        Each question and answer in the Excel is compared against what is extracted
        from the PDFs using fuzzy matching and LLM verification.
      </p>

      <div className="file-input-group">
        <label htmlFor="v-q-pdf">Questions PDF <span className="required">*</span></label>
        <input
          ref={questionsInputRef}
          id="v-q-pdf"
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
        <label htmlFor="v-a-pdf">Answers PDF <span className="required">*</span></label>
        <input
          ref={answersInputRef}
          id="v-a-pdf"
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

      <div className="file-input-group">
        <label htmlFor="v-excel">Excel Sheet <span className="required">*</span></label>
        <input
          ref={excelInputRef}
          id="v-excel"
          type="file"
          accept=".xlsx,.xls"
          onChange={onExcelChange}
          disabled={loading}
          className="file-input"
        />
        {excelFile && (
          <div className="file-info">
            {excelFile.name} ({(excelFile.size / 1024).toFixed(1)} KB)
          </div>
        )}
        <p className="field-hint">
          Expected columns: <code>question_number</code>, <code>question_text</code>, <code>answer</code>
        </p>
      </div>

      {error && <div className="error-message">{error}</div>}

      {success && (
        <div className="success-message">
          <strong>Done!</strong> Validation report downloaded.
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !canSubmit}
        onClick={onSubmit}
        className="submit-button"
      >
        {loading ? 'Validating...' : 'Validate'}
      </button>
    </div>
  );
};

export default ValidateQA;

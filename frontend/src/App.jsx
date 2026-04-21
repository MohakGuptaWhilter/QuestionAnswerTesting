import React, { useState, useEffect } from 'react';
import PDFUploader from './components/PDFUploader';
import './App.css';

function App() {
  const [apiStatus, setApiStatus] = useState('checking');

  useEffect(() => {
    // Check if API is running
    fetch('/health')
      .then(res => {
        if (res.ok) {
          setApiStatus('online');
        } else {
          setApiStatus('offline');
        }
      })
      .catch(() => {
        setApiStatus('offline');
      });
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>📄 QA PDF Extractor</h1>
          <p>Extract questions and answers from PDFs to Excel</p>
        </div>
        <div className={`api-status ${apiStatus}`}>
          <span className="status-dot"></span>
          {apiStatus === 'online' ? 'API Connected' : apiStatus === 'checking' ? 'Checking API...' : 'API Offline'}
        </div>
      </header>

      <main className="app-main">
        {apiStatus === 'offline' && (
          <div className="warning-banner">
            ⚠️ API Server is not running. Start it with:
            <code>python api.py</code>
          </div>
        )}
        
        <PDFUploader />

        <section className="info-section">
          <h2>How it works</h2>
          <div className="steps">
            <div className="step">
              <div className="step-number">1</div>
              <div className="step-content">
                <h3>Upload PDFs</h3>
                <p>Select two PDF files (questions and answers)</p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">2</div>
              <div className="step-content">
                <h3>Extract Data</h3>
                <p>Server extracts questions and correct answers</p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">3</div>
              <div className="step-content">
                <h3>Download Excel</h3>
                <p>Get a formatted Excel file with all Q&A</p>
              </div>
            </div>
          </div>
        </section>

        <section className="features-section">
          <h2>Features</h2>
          <ul className="features-list">
            <li>✓ Upload two PDF files (questions and answers)</li>
            <li>✓ Automatic text extraction and parsing</li>
            <li>✓ Returns formatted Excel file</li>
            <li>✓ Preview extracted questions before download</li>
            <li>✓ Supports up to 50MB per file</li>
            <li>✓ Clean, user-friendly interface</li>
          </ul>
        </section>
      </main>

      <footer className="app-footer">
        <p>QA PDF Extractor • Built with React & Flask</p>
      </footer>
    </div>
  );
}

export default App;

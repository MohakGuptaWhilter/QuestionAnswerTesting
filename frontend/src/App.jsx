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
          <h1>QA PDF Extractor</h1>
          <p>Extract questions and answers from exam PDFs to Excel</p>
        </div>
        <div className={`api-status ${apiStatus}`}>
          <span className="status-dot"></span>
          {apiStatus === 'online' ? 'API Connected' : apiStatus === 'checking' ? 'Checking…' : 'API Offline'}
        </div>
      </header>

      <main className="app-main">
        {apiStatus === 'offline' && (
          <div className="warning-banner">
            API server is not running. Start it with: <code>python api.py</code>
          </div>
        )}
        <PDFUploader />
      </main>

      <footer className="app-footer">
        QA PDF Extractor &mdash; React + Flask
      </footer>
    </div>
  );
}

export default App;

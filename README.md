# QA Testing System

A Flask API + React frontend for extracting questions and answers from PDF documents and evaluating them against a knowledge base API.

## Project Structure

```
qa_test/
├── api.py                  # Flask API (entry point)
├── frontend/               # React frontend
│   └── src/
│       └── components/
│           └── PDFUploader.jsx
├── src/
│   ├── pdf_processor.py    # PDF text extraction and parsing
│   ├── quickstart.py       # LandingAI PDF parsing client
│   └── helpers.py          # Shared utilities (sanitize, search API, Excel builders)
├── tests/
│   └── test_qa_system.py
└── requirements.txt
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/extract` | Extract Q&A from two PDFs → Excel download |
| POST | `/api/evaluate` | Extract Q&A from two PDFs, evaluate via search API → Excel download |
| POST | `/api/evaluate-excel` | Evaluate Q&A from an existing Excel file via search API → Excel download |
| POST | `/api/clean-excel` | Strip noise from the Question column of an Excel file → Excel download |

### Request formats

**`/api/extract` and `/api/evaluate`** — `multipart/form-data`
- `questions_pdf` (file, required)
- `answers_pdf` (file, required)
- `agent_id` (string, evaluate only)
- `deployment_slug` (string, evaluate only)

**`/api/evaluate-excel` and `/api/clean-excel`** — `multipart/form-data`
- `qa_excel` (file, required) — `.xlsx` produced by `/api/extract`
- `agent_id` (string, evaluate-excel only)
- `deployment_slug` (string, evaluate-excel only)

## Installation

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running

**Backend**
```bash
python api.py
# Runs on http://localhost:5000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

## Dependencies

- **Flask** — API server
- **openpyxl** — Excel file creation and manipulation
- **PyMuPDF / PyPDF2** — PDF text extraction
- **landingai-ade** — LandingAI document parsing (questions PDF)
- **requests** — HTTP calls to the external search API
- **python-dotenv** — Environment variable management

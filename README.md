# QA PDF Extractor API

A Flask API for extracting questions and answers from exam PDFs using vision models, with validation support.

## Project Structure

```
qa_test/
├── api.py                    # Flask API — routes only
├── src/
│   ├── vision.py             # Ollama (local) vision backend + model dispatcher
│   ├── claude_vision.py      # Anthropic Claude vision backend
│   ├── gpt_vision.py         # OpenAI GPT vision backend
│   ├── mathpix.py            # Mathpix OCR backend
│   ├── pdf_utils.py          # PDF → PNG cropping, figure extraction, question mapping
│   ├── pdf_processor.py      # PDF text extraction and Q&A parsing
│   ├── quickstart.py         # LandingAI PDF parsing client
│   └── helpers.py            # Shared utilities: sanitize, latex_to_unicode, Excel builders
├── questions/                # Per-question crop images (generated at runtime)
├── figures/                  # Extracted figure images (generated at runtime)
├── frontend/
│   └── src/
│       └── components/
│           └── PDFUploader.jsx
├── tests/
│   └── test_qa_system.py
└── requirements.txt
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/extract` | Extract Q&A from two PDFs via LandingAI → Excel |
| POST | `/api/pdf-to-images` | Crop each question to an image, run vision model → Excel |
| POST | `/api/extract-mathpix` | Crop each question to an image, run Mathpix OCR → Excel |
| POST | `/api/validate` | Validate an existing Excel Q&A sheet against the source PDFs → Excel |

### `/api/pdf-to-images` — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `questions_pdf` | file | yes | PDF of exam questions |
| `answers_pdf` | file | yes | PDF of answer key |
| `model` | string | no | Vision model to use (default: `qwen2.5vl:7b`) |

**Supported `model` values:**

| Value | Backend | Notes |
|-------|---------|-------|
| `qwen2.5vl:7b` | Ollama (local) | Default — requires Ollama running on port 11434 |
| `haiku` | Anthropic Claude | `claude-haiku-4-5-20251001` — fast, lower cost |
| `sonnet` | Anthropic Claude | `claude-sonnet-4-6` — best accuracy for complex math/chemistry |
| `gpt-4o` | OpenAI | Best OpenAI vision model |
| `gpt-4o-mini` | OpenAI | Faster, lower cost OpenAI option |
| Any full model ID | Auto-detected | e.g. `claude-sonnet-4-6`, `gpt-4o-mini` |

### `/api/extract-mathpix` — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `questions_pdf` | file | yes | PDF of exam questions |
| `answers_pdf` | file | yes | PDF of answer key |
| `model` | string | no | Mathpix model: `text` (default) or `latex` |

### `/api/validate` — `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `questions_pdf` | file | yes | Source-of-truth questions PDF |
| `answers_pdf` | file | yes | Source-of-truth answer key PDF |
| `excel` | file | yes | `.xlsx` to validate (must have `question_number`, `question_text`, `answer` columns) |

## Installation

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment variables

| Variable | Required for |
|----------|-------------|
| `ANTHROPIC_API_KEY` | `model=haiku` / `model=sonnet` |
| `OPENAI_API_KEY` | `model=gpt-4o` / `model=gpt-4o-mini` |

For local Ollama, no API key is needed — just have `ollama serve` running.

## Running

```bash
python api.py
# Runs on http://localhost:5000
```

## Dependencies

- **Flask** — API server
- **PyMuPDF** — PDF rendering and text extraction
- **openpyxl** / **pandas** — Excel I/O
- **anthropic** — Anthropic Claude API (optional, for Claude models)
- **openai** — OpenAI API (optional, for GPT models)
- **requests** — Ollama HTTP calls
- **rapidfuzz** — Answer similarity scoring in validation
- **landingai-ade** — LandingAI document parsing (`/api/extract`)

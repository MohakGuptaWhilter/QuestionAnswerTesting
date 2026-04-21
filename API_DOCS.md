# QA PDF Extractor API

A simple Flask API that accepts two PDF files (questions and answers) and returns an Excel file with extracted data, or JSON format.

## Quick Start

### 1. Start the API Server

```bash
# Activate virtual environment
source venv/bin/activate

# Start the API
python api.py
```

Server will run at: `http://localhost:5000`

### 2. Use the API

#### Using cURL (Command Line)

```bash
curl -F "questions_pdf=@questions.pdf" \
     -F "answers_pdf=@answers.pdf" \
     http://localhost:5000/api/extract \
     -o output.xlsx
```

#### Using Python

```python
import requests

files = {
    'questions_pdf': open('questions.pdf', 'rb'),
    'answers_pdf': open('answers.pdf', 'rb')
}

response = requests.post(
    'http://localhost:5000/api/extract',
    files=files
)

with open('output.xlsx', 'wb') as f:
    f.write(response.content)
```

#### Using the Provided Client

```python
from api_client import APIClient

client = APIClient('http://localhost:5000')
client.extract_to_excel('questions.pdf', 'answers.pdf', 'output.xlsx')
```

---

## API Endpoints

### 1. Health Check
```
GET /health
```

**Response (200)**:
```json
{
    "status": "healthy",
    "service": "QA-PDF-Extractor-API",
    "version": "1.0.0"
}
```

---

### 2. Extract Q&A (Returns Excel)
```
POST /api/extract
```

**Request**:
- Content-Type: `multipart/form-data`
- Fields:
  - `questions_pdf` (file, required): PDF containing questions
  - `answers_pdf` (file, required): PDF containing answers

**Response (200)**:
- Returns Excel file (.xlsx) for download
- Filename: `qa_extract_{count}q.xlsx`

**Response (400)**:
```json
{
    "error": "Missing required files: 'questions_pdf' and 'answers_pdf'"
}
```

**Response (500)**:
```json
{
    "error": "Processing error: message"
}
```

**Example cURL**:
```bash
curl -X POST \
  -F "questions_pdf=@questions.pdf" \
  -F "answers_pdf=@answers.pdf" \
  http://localhost:5000/api/extract \
  -o output.xlsx
```

---

### 3. Extract Q&A (Returns JSON)
```
POST /api/extract-json
```

**Request**:
- Content-Type: `multipart/form-data`
- Fields:
  - `questions_pdf` (file, required): PDF containing questions
  - `answers_pdf` (file, required): PDF containing answers

**Response (200)**:
```json
{
    "status": "success",
    "summary": {
        "total_questions": 5,
        "total_answers": 5,
        "matched_pairs": 5,
        "timestamp": "2024-04-15T10:30:45.123456"
    },
    "data": [
        {
            "id": 1,
            "question": "What is the capital of France?",
            "correct_answer": "A"
        },
        {
            "id": 2,
            "question": "Which planet is closest to the Sun?",
            "correct_answer": "B"
        }
    ]
}
```

**Response (400)**:
```json
{
    "error": "Missing required files: 'questions_pdf' and 'answers_pdf'"
}
```

**Example cURL**:
```bash
curl -X POST \
  -F "questions_pdf=@questions.pdf" \
  -F "answers_pdf=@answers.pdf" \
  http://localhost:5000/api/extract-json
```

**Example Python**:
```python
import requests
import json

files = {
    'questions_pdf': open('questions.pdf', 'rb'),
    'answers_pdf': open('answers.pdf', 'rb')
}

response = requests.post(
    'http://localhost:5000/api/extract-json',
    files=files
)

data = response.json()
print(f"Total questions: {data['summary']['total_questions']}")
for item in data['data']:
    print(f"{item['id']}. {item['question']} → {item['correct_answer']}")
```

---

### 4. API Documentation
```
GET /api/info
```

**Response (200)**:
```json
{
    "service": "QA PDF Extractor API",
    "version": "1.0.0",
    "description": "Extracts questions and answers from PDF files",
    "endpoints": {
        "GET /health": "Health check",
        "POST /api/extract": "Extract from PDFs and return Excel file",
        "POST /api/extract-json": "Extract from PDFs and return JSON",
        "GET /api/info": "This documentation"
    },
    "usage": { ... }
}
```

---

## Error Handling

| Status | Error | Meaning |
|--------|-------|---------|
| 400 | Invalid request or missing files | Check request format and required fields |
| 404 | Endpoint not found | Check the API path |
| 413 | File too large | Max 50MB per file |
| 500 | Processing error | Check PDF format or contact support |

---

## Features

✅ Upload two PDF files  
✅ Extract questions and answers  
✅ Returns Excel (.xlsx) or JSON format  
✅ Automatic file cleanup  
✅ Error handling and validation  
✅ Health check endpoint  
✅ API documentation endpoint  

---

## Configuration

Edit `api.py` to customize:

```python
# Maximum file size (default: 50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Server host/port
app.run(debug=True, host='localhost', port=5000)
```

---

## Troubleshooting

### API won't start
```bash
# Make sure Flask is installed
pip install flask

# Run the API
python api.py
```

### PDF parsing issues
The API uses regex patterns to extract questions and answers. If your PDFs have a different format:

1. Open `src/pdf_processor.py`
2. Modify these methods:
   - `parse_questions()` - for custom question parsing
   - `parse_answers()` - for custom answer parsing

### File too large
Increase the limit in `api.py`:
```python
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
```

---

## Examples

### Complete Workflow

```python
from api_client import APIClient

# Create client
client = APIClient('http://localhost:5000')

# Check if API is running
if not client.check_health():
    print("API is not running!")
    exit(1)

# Extract Q&A to Excel
excel_file = client.extract_to_excel(
    'data/input/questions.pdf',
    'data/input/answers.pdf',
    'data/output/results.xlsx'
)

# Or extract as JSON
json_data = client.extract_to_json(
    'data/input/questions.pdf',
    'data/input/answers.pdf'
)

if json_data:
    print(f"Found {json_data['summary']['total_questions']} questions")
    for q in json_data['data'][:3]:
        print(f"  {q['id']}. {q['question']}")
```

### Integration with Other Services

**Save to Database**:
```python
response = client.extract_to_json('q.pdf', 'a.pdf')
for item in response['data']:
    save_to_database(item)
```

**Generate Report**:
```python
excel_file = client.extract_to_excel('q.pdf', 'a.pdf', 'report.xlsx')
send_email(excel_file, recipient='admin@example.com')
```

---

## Development

### Run Tests
```bash
python -m pytest tests/test_qa_system.py
```

### Access API Documentation
Visit: `http://localhost:5000/api/info`

### View Server Logs
Check console output when running `python api.py`

---

## Architecture

```
client.extract_to_excel()
         ↓
  API /api/extract
         ↓
  validate_request()
         ↓
  PDFProcessor.process_and_export()
         ↓
  openpyxl creates .xlsx
         ↓
  send_file() returns Excel
```

---

## Limits

- **Max file size**: 50MB per file
- **Supported format**: PDF only
- **Processing time**: ~5-10 seconds per PDF
- **Concurrent requests**: Limited by Flask/server resources

---

## License

Open source - modify and use as needed.

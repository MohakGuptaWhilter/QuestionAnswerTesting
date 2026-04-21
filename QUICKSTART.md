# Quick Start Guide

## Setup (One-time)

```bash
# 1. Navigate to project
cd qa_test

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt
pip install flask  # For API server
```

---

## **SIMPLE API: Extract PDFs → Excel** (NEW!)

This is the easiest way to use the system.

### Start the API Server

```bash
source venv/bin/activate
python api.py
```

Server runs at: `http://localhost:5000`

### Use the API

**Option 1: Using cURL (Command line)**

```bash
curl -F "questions_pdf=@questions.pdf" \
     -F "answers_pdf=@answers.pdf" \
     http://localhost:5000/api/extract \
     -o output.xlsx
```

**Option 2: Using Python**

```python
import requests

files = {
    'questions_pdf': open('questions.pdf', 'rb'),
    'answers_pdf': open('answers.pdf', 'rb')
}

response = requests.post('http://localhost:5000/api/extract', files=files)

with open('output.xlsx', 'wb') as f:
    f.write(response.content)

print("✓ Excel file saved!")
```

**Option 3: Using Python API Client (Provided)**

```python
from api_client import APIClient

client = APIClient('http://localhost:5000')
client.extract_to_excel('questions.pdf', 'answers.pdf', 'output.xlsx')
```

**Option 4: Get JSON Instead of Excel**

```bash
curl -F "questions_pdf=@questions.pdf" \
     -F "answers_pdf=@answers.pdf" \
     http://localhost:5000/api/extract-json
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Check if API is running |
| `/api/info` | GET | View API documentation |
| `/api/extract` | POST | Upload 2 PDFs → Get Excel file |
| `/api/extract-json` | POST | Upload 2 PDFs → Get JSON |

### Response (Excel version)
- Downloads an Excel file with columns:
  - Question # (ID)
  - Question (Full text)
  - Correct Answer (A/B/C/D)

### Response (JSON version)
```json
{
    "status": "success",
    "summary": {
        "total_questions": 5,
        "total_answers": 5
    },
    "data": [
        {
            "id": 1,
            "question": "What is the capital of France?",
            "correct_answer": "A"
        },
        ...
    ]
}
```

For full API documentation, see [API_DOCS.md](API_DOCS.md)

---

**Create file**: `extract_qa.py`

```python
from src.pdf_processor import PDFProcessor

# Initialize with your PDF files
processor = PDFProcessor(
    questions_pdf_path="path/to/questions.pdf",
    answers_pdf_path="path/to/answers.pdf"
)

# Process and export to Excel
output_file = processor.process_and_export("data/output/questions_and_answers.xlsx")

# Get statistics
summary = processor.get_summary()
print(f"Extracted {summary['total_questions']} questions")
print(f"Extracted {summary['total_answers']} answers")
print(f"Excel file saved to: {output_file}")
```

**Run it**:
```bash
python extract_qa.py
```

**Output**: `questions_and_answers.xlsx` with columns:
- Question # (ID)
- Question (Full question text)
- Correct Answer (A, B, C, or D)

---

## Function 2: Test Answers via API

**Step 1**: Start the sample API server

```bash
pip install flask  # If not already installed
python sample_api.py
```

This starts a server at `http://localhost:5000` with sample data.

**Step 2**: Create file `test_answers.py`

```python
from src.quiz_evaluator import QuizEvaluator

# Initialize evaluator
evaluator = QuizEvaluator(
    excel_file_path="data/output/questions_and_answers.xlsx",
    api_endpoint="http://localhost:5000/api/validate"
)

# Load questions from Excel
questions = evaluator.load_questions_from_excel()
print(f"Loaded {len(questions)} questions")

# Provide answers (order matters!)
user_answers = ["A", "B", "D", "C", "A"]  # Example answers

# Test answers
results = evaluator.test_answers(user_answers)
print(f"Testing complete: {len(results)} answers evaluated")

# Export results to Excel
output_file = evaluator.export_results_to_excel("data/output/test_results.xlsx")

# Show summary
summary = evaluator.get_summary()
print(f"\n✓ Results saved to: {output_file}")
print(f"  Accuracy: {summary['accuracy']:.1f}%")
print(f"  Correct: {summary['correct_answers']}/{summary['total_questions']}")
```

**Run it**:
```bash
python test_answers.py
```

**Output**: `test_results.xlsx` with columns:
- Question # (ID)
- Question
- Correct Answer (from PDF)
- User Answer (your answer)
- **Result** (✓ Correct / ✗ Incorrect / ⚠ Error) - **Color-coded**
- Expected Answer (from API)
- Error (if any)

---

## Project Structure

```
qa_test/
├── src/
│   ├── pdf_processor.py      ← Function 1: Extract from PDFs
│   ├── quiz_evaluator.py     ← Function 2: Test via API
│   ├── utils.py              ← Helpers
│   └── __init__.py
├── data/
│   ├── input/   ← Put your PDFs here
│   └── output/  ← Generated Excel files go here
├── tests/       ← Unit tests
├── sample_api.py            ← Reference API implementation
├── examples.py              ← Usage examples
├── main.py                  ← Entry point
├── requirements.txt         ← Dependencies
└── README.md               ← Full documentation
```

---

## Common Tasks

### Task 1: Process Your PDFs
```bash
# Place PDFs in data/input/
# Create a Python script or use Python shell:

from src.pdf_processor import PDFProcessor
processor = PDFProcessor("data/input/questions.pdf", "data/input/answers.pdf")
processor.process_and_export("data/output/qa.xlsx")
```

### Task 2: Test with Your API
```bash
# Update the API endpoint URL:

from src.quiz_evaluator import QuizEvaluator
evaluator = QuizEvaluator(
    "data/output/qa.xlsx",
    "http://your-api-server.com/validate"  # ← Change this
)
user_answers = ["A", "B", "C", "D", "A"]  # ← Provide real answers
evaluator.test_answers(user_answers)
evaluator.export_results_to_excel("data/output/results.xlsx")
```

### Task 3: View Generated Reports
The Excel files are self-explanatory and color-coded:
- 🟢 Green cells = Correct answer
- 🔴 Red cells = Incorrect answer  
- 🟡 Yellow cells = Error

---

## Testing

Run unit tests:
```bash
python -m pytest tests/test_qa_system.py -v
# OR
python tests/test_qa_system.py
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'PyPDF2'` | Activate venv and run `pip install -r requirements.txt` |
| PDFs not being parsed correctly | Modify `parse_questions()` and `parse_answers()` in `pdf_processor.py` to match your PDF format |
| API connection errors | Check your API endpoint URL. Use `sample_api.py` to test locally first |
| Empty Excel file | PDFs might not have detectable questions/answers. Customize the parsing regex patterns |

---

## Next Steps

1. **Extract from your PDFs**: Place PDFs in `data/input/` and run extraction
2. **Set up your API**: Update the API endpoint URL in your test script
3. **Test answers**: Provide user answers and run the testing function
4. **Review results**: Open the Excel file to see color-coded results

For more details, see [README.md](README.md)

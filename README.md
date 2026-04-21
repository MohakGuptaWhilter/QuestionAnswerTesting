# QA Testing System

A Python-based system for extracting questions and answers from PDF documents and testing them via an API endpoint with detailed result reporting.

## Features

### 1. PDF Processing (`PDFProcessor`)
- Extract questions from PDF documents
- Extract correct answers from PDF documents
- Parse and structure the extracted data
- Export questions and answers to Excel format
- Handle multiple PDF formats and structures

### 2. Quiz Evaluation (`QuizEvaluator`)
- Load questions from Excel files
- Submit answers to API endpo for validation
- Collect and analyze results
- Generate detailed Excel reports with color-coded results
- Provide accuracy statistics and summaries

## Installation

1. **Clone or navigate to the project directory**
   ```bash
   cd qa_test
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Setup

```python
from src.pdf_processor import PDFProcessor
from src.quiz_evaluator import QuizEvaluator
```

### Function 1: Extract Questions and Answers from PDFs

```python
# Initialize the PDF processor
processor = PDFProcessor(
    questions_pdf_path="path/to/questions.pdf",
    answers_pdf_path="path/to/answers.pdf"
)

# Process and export to Excel
output_file = processor.process_and_export("path/to/output.xlsx")

# Get summary
summary = processor.get_summary()
print(f"Questions extracted: {summary['total_questions']}")
print(f"Answers extracted: {summary['total_answers']}")
```

**Output**: Excel file with columns:
- Question # (ID)
- Question (Full question text)
- Correct Answer (Extracted correct option)

### Function 2: Test Answers via API and Generate Report

```python
# Initialize the quiz evaluator
evaluator = QuizEvaluator(
    excel_file_path="path/to/questions.xlsx",
    api_endpoint="http://your-api.com/validate"  # Your API endpoint
)

# Load questions
questions = evaluator.load_questions_from_excel()

# Your user answers (in order matching the Excel file)
user_answers = ["A", "B", "C", "D", "A"]  # Example

# Test answers via API
results = evaluator.test_answers(user_answers)

# Export results to Excel
output_file = evaluator.export_results_to_excel("path/to/results.xlsx")

# Get summary statistics
summary = evaluator.get_summary()
print(f"Accuracy: {summary['accuracy']:.1f}%")
print(f"Correct: {summary['correct_answers']}/{summary['total_questions']}")
```

**Output**: Excel file with columns:
- Question # (ID)
- Question (Full question text)
- Correct Answer (From PDF)
- User Answer (Provided answer)
- Result (Correct/Incorrect/Error) - Color coded
- Expected Answer (From API)
- Error (Any error message if applicable)

## API Endpoint Requirements

The API endpoint should:

1. **Accept POST requests** with JSON body:
   ```json
   {
       "question_id": 1,
       "user_answer": "A"
   }
   ```

2. **Return JSON response**:
   ```json
   {
       "correct": true,
       "correct_answer": "A"
   }
   ```

## Directory Structure

```
qa_test/
├── src/
│   ├── __init__.py
│   ├── pdf_processor.py      # PDF extraction logic
│   ├── quiz_evaluator.py     # API validation logic
│   └── utils.py              # Utility functions
├── tests/                    # Test files
├── data/
│   ├── input/               # Input PDFs
│   ├── output/              # Generated Excel files
│   └── test/                # Test data
├── main.py                  # Main entry point
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Dependencies

- **PyPDF2**: PDF file processing
- **openpyxl**: Excel file creation and manipulation
- **requests**: HTTP API calls
- **python-dotenv**: Environment variable management

## Project File Descriptions

| File | Purpose |
|------|---------|
| `pdf_processor.py` | Extracts text from PDFs, parses questions/answers, exports to Excel |
| `quiz_evaluator.py` | Loads questions, validates via API, generates test reports |
| `utils.py` | Helper functions for file/directory management |
| `main.py` | Example usage and entry point |

## Error Handling

The system handles various error scenarios:

- **File not found**: Raises `FileNotFoundError` with clear message
- **PDF read errors**: Catches and reports PDF processing issues
- **API connection errors**: Marks responses as errors, doesn't crash
- **API timeout**: Gracefully handles slow API responses
- **Missing data**: Uses "N/A" for missing values

## Example Workflow

1. **Prepare PDFs** with questions and answers
2. **Run PDF processor** to extract and create Excel
3. **Set up API endpoint** for answer validation
4. **Run quiz evaluator** with the extracted questions
5. **Review results** in the generated Excel report

## Customization

### Parsing Custom PDF Formats

Modify `parse_questions()` and `parse_answers()` methods in `PDFProcessor`:

```python
def parse_questions(self, text: str) -> List[str]:
    # Add your custom parsing logic here
    pass
```

### API Integration

Modify the `validate_answer_with_api()` method in `QuizEvaluator` to match your API spec:

```python
def validate_answer_with_api(self, question_id: int, user_answer: str) -> Dict:
    # Customize request/response handling
    pass
```

## Troubleshooting

**Q: "PDF file not found" error**
- A: Verify the PDF file path exists and is correct

**Q: Empty questions/answers extracted**
- A: Your PDF format may not match expected patterns. Modify `parse_questions()` and `parse_answers()` methods

**Q: API connection errors**
- A: Check your API endpoint URL and ensure the server is running

**Q: Excel file not created**
- A: Ensure output directory exists and you have write permissions

## License

This project is provided as-is for educational and commercial use.

## Support

For issues or questions, refer to the docstrings in the source code files or modify the parsing/validation logic to match your specific requirements.
# QuestionAnswerTesting

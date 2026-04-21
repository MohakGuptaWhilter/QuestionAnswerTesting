"""
Flask API for PDF Question & Answer Extraction
Accepts two PDF files and returns an Excel file with extracted Q&A
"""

import os
import re
import tempfile
import requests as http_requests
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from src.pdf_processor import PDFProcessor
from src.quickstart import parse_pdf, extract_questions


app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


_ILLEGAL_EXCEL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿]')

def _sanitize(text: str) -> str:
    """Remove characters that Excel/openpyxl cannot store in a cell."""
    return _ILLEGAL_EXCEL_CHARS.sub('', text) if text else text


def allowed_file(filename):
    """Check if file has allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_request():
    """Validate incoming request has required files."""
    if 'questions_pdf' not in request.files or 'answers_pdf' not in request.files:
        return False, "Missing required files: 'questions_pdf' and 'answers_pdf'"
    
    questions_file = request.files['questions_pdf']
    answers_file = request.files['answers_pdf']
    
    if questions_file.filename == '' or answers_file.filename == '':
        return False, "File names cannot be empty"
    
    if not (allowed_file(questions_file.filename) and allowed_file(answers_file.filename)):
        return False, "Only PDF files are allowed"
    
    return True, None


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "QA-PDF-Extractor-API",
        "version": "1.0.0"
    }), 200


@app.route('/api/extract', methods=['POST'])
def extract_qa():
    """
    Extract questions and answers from uploaded PDFs.
    
    Request:
        - Form data with two file uploads:
            - 'questions_pdf': PDF containing questions
            - 'answers_pdf': PDF containing answers
    
    Response:
        - Excel file download on success
        - JSON error message on failure
    
    Example cURL:
        curl -F "questions_pdf=@questions.pdf" \\
             -F "answers_pdf=@answers.pdf" \\
             http://localhost:5000/api/extract -o output.xlsx
    """
    questions_path = None
    answers_path = None
    try:
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        questions_file = request.files['questions_pdf']
        answers_file = request.files['answers_pdf']

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))

        questions_file.save(questions_path)
        answers_file.save(answers_path)

        # Parse questions PDF with LandingAI, extract answers PDF with PDFProcessor
        questions_md = parse_pdf(questions_path)["markdown"]
        questions_list = extract_questions(questions_md)

        processor = PDFProcessor(questions_path, answers_path)
        answers_text = processor.extract_text_from_pdf(answers_path)
        answers_list = processor.parse_answers(answers_text)

        if not questions_list:
            return jsonify({"error": "No questions could be extracted from the PDF"}), 422

        # Deduplicate — keep first occurrence of each unique question
        seen = set()
        unique_pairs = []
        for i, q in enumerate(questions_list):
            key = q.strip().lower()
            if key not in seen:
                seen.add(key)
                answer = answers_list[i] if i < len(answers_list) else "N/A"
                unique_pairs.append((q, answer))

        # Build Excel output
        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted_qa.xlsx')
        wb = Workbook()
        ws = wb.active
        ws.title = "Q&A"

        ws.append(["Question #", "Question", "Correct Answer"])
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for idx, (question, answer) in enumerate(unique_pairs, start=1):
            ws.append([idx, _sanitize(question), _sanitize(answer)])
            ws.cell(idx + 1, 1).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(idx + 1, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            ws.cell(idx + 1, 3).alignment = Alignment(horizontal="center", vertical="center")

        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 60
        ws.column_dimensions['C'].width = 18
        wb.save(output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'qa_extract_{len(unique_pairs)}q.xlsx'
        )

    except FileNotFoundError as e:
        return jsonify({"error": f"File not found: {str(e)}"}), 404

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

    finally:
        for path in (questions_path, answers_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


@app.route('/api/extract-json', methods=['POST'])
def extract_qa_json():
    """
    Extract questions and answers from PDFs and return as JSON.
    
    Request:
        - Form data with two file uploads:
            - 'questions_pdf': PDF containing questions
            - 'answers_pdf': PDF containing answers
    
    Response:
        - JSON with extracted questions and answers
    
    Example:
        {
            "status": "success",
            "summary": {
                "total_questions": 5,
                "total_answers": 5,
                "matched_pairs": 5
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
    """
    try:
        # Validate request
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
        # Get uploaded files
        questions_file = request.files['questions_pdf']
        answers_file = request.files['answers_pdf']
        
        # Save temporarily
        questions_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            secure_filename(questions_file.filename)
        )
        answers_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            secure_filename(answers_file.filename)
        )
        
        questions_file.save(questions_path)
        answers_file.save(answers_path)
        
        # Process PDFs
        processor = PDFProcessor(questions_path, answers_path)
        
        # Extract text
        questions_text = processor.extract_text_from_pdf(questions_path)
        answers_text = processor.extract_text_from_pdf(answers_path)
        
        # Parse content
        questions_list = processor.parse_questions(questions_text)
        answers_list = processor.parse_answers(answers_text)
        
        # Build response data
        data = []
        for idx, question in enumerate(questions_list, 1):
            answer = answers_list[idx - 1] if idx - 1 < len(answers_list) else "N/A"
            data.append({
                "id": idx,
                "question": question,
                "correct_answer": answer
            })
        
        summary = processor.get_summary()
        
        return jsonify({
            "status": "success",
            "summary": summary,
            "data": data
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500
    
    finally:
        # Cleanup
        try:
            if os.path.exists(questions_path):
                os.remove(questions_path)
            if os.path.exists(answers_path):
                os.remove(answers_path)
        except:
            pass


@app.route('/api/info', methods=['GET'])
def api_info():
    """Get API documentation and usage information."""
    return jsonify({
        "service": "QA PDF Extractor API",
        "version": "1.0.0",
        "description": "Extracts questions and answers from PDF files",
        "endpoints": {
            "GET /health": "Health check",
            "POST /api/extract": "Extract from PDFs and return Excel file",
            "POST /api/extract-json": "Extract from PDFs and return JSON",
            "GET /api/info": "This documentation"
        },
        "usage": {
            "extract": {
                "method": "POST",
                "path": "/api/extract",
                "description": "Upload two PDFs and receive Excel file",
                "request": {
                    "content-type": "multipart/form-data",
                    "fields": {
                        "questions_pdf": "PDF file containing questions",
                        "answers_pdf": "PDF file containing answers"
                    }
                },
                "response": {
                    "success": "Excel file (.xlsx) with extracted Q&A",
                    "error": {
                        "400": "Invalid request or missing files",
                        "500": "Processing error"
                    }
                },
                "example_curl": 'curl -F "questions_pdf=@questions.pdf" -F "answers_pdf=@answers.pdf" http://localhost:5000/api/extract -o output.xlsx'
            },
            "extract_json": {
                "method": "POST",
                "path": "/api/extract-json",
                "description": "Upload two PDFs and receive JSON response",
                "request": {
                    "content-type": "multipart/form-data",
                    "fields": {
                        "questions_pdf": "PDF file containing questions",
                        "answers_pdf": "PDF file containing answers"
                    }
                },
                "response": {
                    "status": "success",
                    "summary": {
                        "total_questions": "int",
                        "total_answers": "int",
                        "matched_pairs": "int"
                    },
                    "data": [
                        {
                            "id": "int",
                            "question": "string",
                            "correct_answer": "string"
                        }
                    ]
                }
            }
        }
    }), 200


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    return jsonify({
        "error": f"File too large. Maximum file size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
    }), 413


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": "/api/info"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        "error": "Internal server error"
    }), 500


# ---------------------------------------------------------------------------
# Evaluate endpoint — calls external search API per question
# ---------------------------------------------------------------------------

SEARCH_API_URL = "https://dev.api.kb.whilter.ai/api/search"


_FIXED_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMGZkY2M5YmMtYzY0OC00YzRiLWE5NDUtNWE1NGJhZmYyZWI1IiwiZXhwIjoxNzc4OTkyNjI4fQ.vXssK0Dg3xWdOoVnq3zlZ1txrXtzjy7vZlQneeUmqHU"


def _call_search_api(question: str, agent_id: str, deployment_slug: str) -> str:
    """
    Send one question to the external search API and return the answer text.
    Returns an error string if the call fails.
    """
    payload = {
        "query": question,
        "agent_id": agent_id,
        "tenant_id": "e6475d6e-f357-443f-8ab9-f0f61081191e",
        "top_k": 5,
        "filters": {"additionalProp1": {}},
        "chat_history": [],
        "deployment_slug": deployment_slug,
        "llm_provider": {
            "provider": "openai",
            "model": "intellirag-gpt-5.2",
            "api_key": "string",
            "base_url": "string"
        },
        "embedding_provider": {
            "provider": "openai",
            "model": "intellirag-text-embedding-3-small"
        },
        "llm_routing": "true",
        "system_prompt": "string",
        "summary_prompt": False,
        "followup_questions": False
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {_FIXED_AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        resp = http_requests.post(SEARCH_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            return f"[API error {resp.status_code}]"
        data = resp.json()
        answer = data.get("answer") or ""
        if not answer:
            return "[No answer returned]"
        # Strip citation markers like [1], [2], [3]
        answer = re.sub(r'\[\d+\]', '', answer)
        # Strip markdown heading markers (##, ###, etc.)
        answer = re.sub(r'^#{1,6}\s+', '', answer, flags=re.MULTILINE)
        return answer.strip()
    except http_requests.exceptions.Timeout:
        return "[timeout]"
    except Exception as exc:
        return f"[error: {exc}]"


def _check_correctness(api_response: str, correct_answer: str) -> str:
    """
    Compare the search API's free-text response to the correct answer.

    Returns one of:
      'Correct'        — confident match
      'Incorrect'      — confident mismatch
      'Manual Review'  — MCQ or ambiguous (cannot auto-determine)
    """
    if not api_response or api_response.startswith("["):
        return "Manual Review"

    correct = (correct_answer or "").strip()
    response_lower = api_response.lower()

    # MCQ answer: (1), (2), (3), (4) — cannot reliably match free text
    if re.match(r'^\(\d+\)$', correct):
        return "Manual Review"

    # Numerical answer (integer or decimal)
    try:
        correct_num = float(correct)
        found_nums = re.findall(r'-?\d+(?:\.\d+)?', api_response)
        for n in found_nums:
            if abs(float(n) - correct_num) < 0.01:
                return "Correct"
        return "Incorrect"
    except ValueError:
        pass

    # Plain-text answer — simple substring check
    if correct.lower() in response_lower:
        return "Correct"

    return "Manual Review"


def _build_evaluation_excel(
    questions: list,
    answers: list,
    api_responses: list,
    statuses: list,
    output_path: str
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Evaluation"

    headers = ["Question #", "Question", "Correct Answer", "API Response", "Status"]
    ws.append(headers)

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    status_styles = {
        "Correct":       (PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
                          Font(color="006100", bold=True)),
        "Incorrect":     (PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
                          Font(color="9C0006", bold=True)),
        "Manual Review": (PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
                          Font(color="9C6500", bold=True)),
    }

    for idx, (question, answer, api_resp, status) in enumerate(
        zip(questions, answers, api_responses, statuses), start=1
    ):
        ws.append([idx, _sanitize(question), _sanitize(answer), _sanitize(api_resp), status])
        row = ws.max_row
        # Style question and API response cells
        ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        ws.cell(row, 3).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row, 4).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        # Colour-code the status cell
        fill, font = status_styles.get(status, status_styles["Manual Review"])
        status_cell = ws.cell(row, 5)
        status_cell.fill = fill
        status_cell.font = font
        status_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 60
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 55
    ws.column_dimensions['E'].width = 18

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)


@app.route('/api/evaluate', methods=['POST'])
def evaluate_qa():
    """
    Extract Q&A from uploaded PDFs, call the external search API for every
    question, and return an Excel file showing whether each answer is correct.

    Form fields:
        questions_pdf  (file, required)
        answers_pdf    (file, required)
        auth_token     (string, required) — Bearer token for the search API

    Response:
        Excel file (.xlsx) with columns:
            Question # | Question | Correct Answer | API Response | Status
        Status is one of: Correct / Incorrect / Manual Review
    """
    questions_path = None
    answers_path = None
    try:
        # --- validate files ---
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        agent_id        = request.form.get("agent_id", "524829a7-ad2d-4bd4-b094-3a8ef5b62a9e")
        deployment_slug = request.form.get("deployment_slug", "test123")

        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))

        questions_file.save(questions_path)
        answers_file.save(answers_path)

        # --- extract Q&A from PDFs ---
        processor = PDFProcessor(questions_path, answers_path)
        questions_text = processor.extract_text_from_pdf(questions_path)
        answers_text   = processor.extract_text_from_pdf(answers_path)
        questions_list = processor.parse_questions(questions_text)
        answers_list   = processor.parse_answers(answers_text)

        if not questions_list:
            return jsonify({"error": "No questions could be parsed from the PDF"}), 422

        # --- call search API for each question ---
        api_responses = []
        statuses = []
        for idx, question in enumerate(questions_list):
            correct_answer = answers_list[idx] if idx < len(answers_list) else "N/A"
            api_resp = _call_search_api(question, agent_id, deployment_slug)
            status   = _check_correctness(api_resp, correct_answer)
            api_responses.append(api_resp)
            statuses.append(status)
            print(f"  Q{idx+1}: {status}")

        # --- build Excel ---
        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_results.xlsx')
        _build_evaluation_excel(
            questions_list,
            [answers_list[i] if i < len(answers_list) else "N/A" for i in range(len(questions_list))],
            api_responses,
            statuses,
            output_excel
        )

        correct_count = statuses.count("Correct")
        incorrect_count = statuses.count("Incorrect")
        manual_count = statuses.count("Manual Review")
        total = len(statuses)
        print(f"\nEvaluation complete: {correct_count} correct, {incorrect_count} incorrect, "
              f"{manual_count} manual review (total {total})")

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'evaluation_{total}q.xlsx'
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

    finally:
        for path in (questions_path, answers_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


@app.route('/api/evaluate-excel', methods=['POST'])
def evaluate_from_excel():
    """
    Take a single Excel file (columns: Question #, Question, Correct Answer),
    call the search API for every question, and return an enriched Excel with
    the API response and a Correct / Incorrect / Manual Review status.

    Form fields:
        qa_excel    (file, required)  — .xlsx with Q&A already extracted
        auth_token  (string, required) — Bearer token for the search API

    Expected Excel format (produced by /api/extract):
        Col A: Question #
        Col B: Question
        Col C: Correct Answer

    Response:
        Excel file with two extra columns appended:
            Col D: API Response
            Col E: Status  (green = Correct, red = Incorrect, yellow = Manual Review)

    Example cURL:
        curl -F "qa_excel=@extracted_qa.xlsx" \\
             -F "auth_token=eyJ..." \\
             http://localhost:5000/api/evaluate-excel -o results.xlsx
    """
    excel_path = None
    try:
        # --- validate file ---
        if 'qa_excel' not in request.files:
            return jsonify({"error": "Missing required file: 'qa_excel'"}), 400

        excel_file = request.files['qa_excel']
        if excel_file.filename == '':
            return jsonify({"error": "File name cannot be empty"}), 400
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Only Excel files (.xlsx) are accepted"}), 400

        agent_id        = request.form.get("agent_id", "524829a7-ad2d-4bd4-b094-3a8ef5b62a9e")
        deployment_slug = request.form.get("deployment_slug", "test123")

        # --- save and load the Excel ---
        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
        excel_file.save(excel_path)

        wb_in = load_workbook(excel_path)
        ws_in = wb_in.active

        rows = list(ws_in.iter_rows(min_row=2, values_only=True))
        rows = [r for r in rows if r[0] is not None]   # skip blank rows

        if not rows:
            return jsonify({"error": "No data rows found in the Excel file"}), 422

        questions_list = [str(r[1]) if r[1] is not None else "" for r in rows]
        answers_list   = [str(r[2]) if r[2] is not None else "N/A" for r in rows]

        # --- call search API for each question ---
        api_responses = []
        statuses = []
        for idx, (question, correct_answer) in enumerate(zip(questions_list, answers_list)):
            api_resp = _call_search_api(question, agent_id, deployment_slug)
            status   = _check_correctness(api_resp, correct_answer)
            api_responses.append(api_resp)
            statuses.append(status)
            print(f"  Q{idx+1}: {status}")

        # --- build output Excel ---
        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_from_excel.xlsx')
        _build_evaluation_excel(
            questions_list,
            answers_list,
            api_responses,
            statuses,
            output_excel
        )

        correct_count   = statuses.count("Correct")
        incorrect_count = statuses.count("Incorrect")
        manual_count    = statuses.count("Manual Review")
        total           = len(statuses)
        print(f"\nEvaluation complete: {correct_count} correct, {incorrect_count} incorrect, "
              f"{manual_count} manual review (total {total})")

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'evaluation_{total}q.xlsx'
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

    finally:
        try:
            if excel_path and os.path.exists(excel_path):
                os.remove(excel_path)
        except Exception:
            pass


if __name__ == '__main__':
    print("\n" + "="*70)
    print("QA PDF Extractor API")
    print("="*70)
    print("\nEndpoints:")
    print("  GET  /health                         - Health check")
    print("  GET  /api/info                       - API documentation")
    print("  POST /api/extract                    - Extract Q&A from PDFs, returns Excel")
    print("  POST /api/extract-json               - Extract Q&A from PDFs, returns JSON")
    print("  POST /api/evaluate                   - Evaluate Q&A via search API (PDFs in), returns Excel")
    print("  POST /api/evaluate-excel             - Evaluate Q&A via search API (Excel in), returns Excel")
    print("\nServer running on http://localhost:5000")
    print("\nUsage example:")
    print('  curl -F "qa_excel=@extracted_qa.xlsx" \\')
    print('       -F "auth_token=eyJ..." \\')
    print('       http://localhost:5000/api/evaluate-excel -o results.xlsx')
    print("\n" + "="*70 + "\n")

    app.run(debug=True, host='localhost', port=5000)

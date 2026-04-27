import os
import re
import tempfile
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from src.pdf_processor import PDFProcessor
from src.quickstart import parse_pdf
from src.helpers import (
    sanitize, clean_question,
    call_search_api, check_correctness, build_evaluation_excel,
    latex_to_unicode,
)
from src.gpt_processor import extract_qa_with_gpt

app = Flask(__name__)

_FIGURE_URL_RE = re.compile(r'\[\[FIGURE_URL:([^\]]+)\]\]')
_FIG_FONT = Font(color='0070C0', underline='single')


def _inline_fig_labels(question: str) -> str:
    """Replace each [[FIGURE_URL:...]] with [FIGURE1], [FIGURE2], … in reading order."""
    counter = 0
    def _sub(_):
        nonlocal counter
        counter += 1
        return f'[FIGURE{counter}]'
    return _FIGURE_URL_RE.sub(_sub, question)

UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_request():
    if 'questions_pdf' not in request.files or 'answers_pdf' not in request.files:
        return False, "Missing required files: 'questions_pdf' and 'answers_pdf'"
    questions_file = request.files['questions_pdf']
    answers_file = request.files['answers_pdf']
    if questions_file.filename == '' or answers_file.filename == '':
        return False, "File names cannot be empty"
    if not (allowed_file(questions_file.filename) and allowed_file(answers_file.filename)):
        return False, "Only PDF files are allowed"
    return True, None


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": f"File too large. Maximum file size is {MAX_FILE_SIZE // (1024 * 1024)}MB"}), 413

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "QA-PDF-Extractor-API", "version": "1.0.0"}), 200


@app.route('/api/extract', methods=['POST'])
def extract_qa():
    questions_path = None
    answers_path = None
    try:
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))

        questions_file.save(questions_path)
        answers_file.save(answers_path)

        questions_md  = parse_pdf(questions_path)["markdown"]
        processor     = PDFProcessor(questions_path, answers_path)
        questions_list = processor.parse_questions(questions_md)
        answers_list   = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

        if not questions_list:
            return jsonify({"error": "No questions could be extracted from the PDF"}), 422

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted_qa.xlsx')
        wb = Workbook()
        ws = wb.active
        ws.title = "Q&A"

        max_figs = max((len(_FIGURE_URL_RE.findall(q)) for q in questions_list), default=0)
        ans_col  = 3 + max_figs
        header   = ["Question #", "Question"] + [f"Figure {n}" for n in range(1, max_figs + 1)] + ["Correct Answer"]
        ws.append(header)
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for idx, question in enumerate(questions_list, start=1):
            answer = answers_list[idx - 1] if idx - 1 < len(answers_list) else "N/A"
            urls   = _FIGURE_URL_RE.findall(question)
            q_text = latex_to_unicode(sanitize(_inline_fig_labels(question)))

            ws.append([idx, q_text] + [None] * max_figs + [sanitize(answer)])
            row = ws.max_row
            ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            for n, url in enumerate(urls):
                fig_cell            = ws.cell(row, 3 + n)
                fig_cell.value      = f"View Figure {n + 1}"
                fig_cell.hyperlink  = url
                fig_cell.font       = _FIG_FONT
                fig_cell.alignment  = Alignment(horizontal="center", vertical="top")
            ws.cell(row, ans_col).alignment = Alignment(horizontal="center", vertical="center")

        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 60
        for n in range(max_figs):
            ws.column_dimensions[get_column_letter(3 + n)].width = 15
        ws.column_dimensions[get_column_letter(ans_col)].width = 18
        wb.save(output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'qa_extract_{len(questions_list)}q.xlsx',
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

@app.route('/api/evaluate', methods=['POST'])
def evaluate_qa():
    questions_path = None
    answers_path = None
    try:
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

        processor = PDFProcessor(questions_path, answers_path)
        questions_list = processor.parse_questions(processor.extract_text_from_pdf(questions_path))
        answers_list   = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

        if not questions_list:
            return jsonify({"error": "No questions could be parsed from the PDF"}), 422

        api_responses, statuses = [], []
        for idx, question in enumerate(questions_list):
            correct_answer = answers_list[idx] if idx < len(answers_list) else "N/A"
            api_resp = call_search_api(question, agent_id, deployment_slug)
            api_responses.append(api_resp)
            statuses.append(check_correctness(api_resp, correct_answer))

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_results.xlsx')
        build_evaluation_excel(
            questions_list,
            [answers_list[i] if i < len(answers_list) else "N/A" for i in range(len(questions_list))],
            api_responses,
            statuses,
            output_excel,
        )

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'evaluation_{len(statuses)}q.xlsx',
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
    excel_path = None
    try:
        if 'qa_excel' not in request.files:
            return jsonify({"error": "Missing required file: 'qa_excel'"}), 400

        excel_file = request.files['qa_excel']
        if excel_file.filename == '':
            return jsonify({"error": "File name cannot be empty"}), 400
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Only Excel files (.xlsx) are accepted"}), 400

        agent_id        = request.form.get("agent_id", "524829a7-ad2d-4bd4-b094-3a8ef5b62a9e")
        deployment_slug = request.form.get("deployment_slug", "test123")

        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
        excel_file.save(excel_path)

        ws_in = load_workbook(excel_path).active
        rows = [r for r in ws_in.iter_rows(min_row=2, values_only=True) if r[0] is not None]

        if not rows:
            return jsonify({"error": "No data rows found in the Excel file"}), 422

        questions_list = [str(r[1]) if r[1] is not None else "" for r in rows]
        answers_list   = [str(r[2]) if r[2] is not None else "N/A" for r in rows]

        api_responses, statuses = [], []
        for question, correct_answer in zip(questions_list, answers_list):
            api_resp = call_search_api(question, agent_id, deployment_slug)
            api_responses.append(api_resp)
            statuses.append(check_correctness(api_resp, correct_answer))

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_from_excel.xlsx')
        build_evaluation_excel(questions_list, answers_list, api_responses, statuses, output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'evaluation_{len(statuses)}q.xlsx',
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        try:
            if excel_path and os.path.exists(excel_path):
                os.remove(excel_path)
        except Exception:
            pass


@app.route('/api/clean-excel', methods=['POST'])
def clean_excel():
    excel_path = None
    try:
        if 'qa_excel' not in request.files:
            return jsonify({"error": "Missing required file: 'qa_excel'"}), 400

        excel_file = request.files['qa_excel']
        if excel_file.filename == '':
            return jsonify({"error": "File name cannot be empty"}), 400
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Only Excel files (.xlsx) are accepted"}), 400

        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
        excel_file.save(excel_path)

        wb = load_workbook(excel_path)
        ws = wb.active
        for row in ws.iter_rows(min_row=2):
            cell = row[1]  # column B — Question
            if cell.value:
                cell.value = sanitize(clean_question(str(cell.value)))

        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cleaned_qa.xlsx')
        wb.save(output_path)

        return send_file(
            output_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='cleaned_qa.xlsx',
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        try:
            if excel_path and os.path.exists(excel_path):
                os.remove(excel_path)
        except Exception:
            pass


@app.route('/api/extract-gpt', methods=['POST'])
def extract_gpt():
    pdf_path = None
    try:
        if 'pdf' not in request.files:
            return jsonify({"error": "Missing required file: 'pdf'"}), 400

        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"error": "File name cannot be empty"}), 400
        if not allowed_file(pdf_file.filename):
            return jsonify({"error": "Only PDF files are allowed"}), 400

        model = request.form.get("model", "gpt-4o-mini")

        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(pdf_file.filename))
        pdf_file.save(pdf_path)

        pairs = extract_qa_with_gpt(pdf_path, model=model)

        if not pairs:
            return jsonify({"error": "No question-answer pairs found in the PDF."}), 422

        wb = Workbook()
        ws = wb.active
        ws.title = "Q&A"

        max_figs = max((len(_FIGURE_URL_RE.findall(p["question"])) for p in pairs), default=0)
        ans_col  = 3 + max_figs
        header   = ["Question #", "Question"] + [f"Figure {n}" for n in range(1, max_figs + 1)] + ["Answer / Solution"]
        ws.append(header)
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for idx, pair in enumerate(pairs, start=1):
            urls   = _FIGURE_URL_RE.findall(pair["question"])
            q_text = latex_to_unicode(sanitize(_inline_fig_labels(pair["question"])))
            a_text = latex_to_unicode(sanitize(pair["answer"]))

            ws.append([idx, q_text] + [None] * max_figs + [a_text])
            row = ws.max_row
            ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            for n, url in enumerate(urls):
                fig_cell            = ws.cell(row, 3 + n)
                fig_cell.value      = f"View Figure {n + 1}"
                fig_cell.hyperlink  = url
                fig_cell.font       = _FIG_FONT
                fig_cell.alignment  = Alignment(horizontal="center", vertical="top")
            ws.cell(row, ans_col).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 60
        for n in range(max_figs):
            ws.column_dimensions[get_column_letter(3 + n)].width = 15
        ws.column_dimensions[get_column_letter(ans_col)].width = 70

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'gpt_qa.xlsx')
        wb.save(output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'gpt_qa_{len(pairs)}q.xlsx',
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        try:
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass


if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5000)

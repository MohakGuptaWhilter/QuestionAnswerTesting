import os
import re
import json
import base64
import tempfile
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import pandas as pd
import requests as _http
from rapidfuzz import fuzz as _fuzz
from arihant_pipeline.exporter import Exporter
from arihant_pipeline.general_purpose_extraction_pipeline import GeneralPurposeExtractionPipeline
from src.pdf_processor import PDFProcessor
from src.quickstart import parse_pdf
from src.helpers import (
    sanitize,
    # clean_question,       # only used by /api/clean-excel (disabled)
    # call_search_api,      # only used by /api/evaluate*   (disabled)
    check_correctness,
    # build_evaluation_excel,  # only used by /api/evaluate* (disabled)
    build_validation_excel,
    latex_to_unicode, FIGURE_URL_RE, FIG_FONT, inline_fig_labels,
)
from src.pdf_utils import (
    extract_figures_from_pdf,
    build_question_mapping, crop_questions_from_pdf,
    extract_figures_per_question,
    pdf_pages_to_png, save_page_crops, detect_layout_fitz,
    crop_questions_from_pages,
    crop_questions_and_answers_from_pages,
    extract_figures_from_pages, map_figures_to_questions_on_pages,
)
from src.vision import call_vision, call_vision_with_prompt, _MODEL_ALIASES
from src.mathpix import call_mathpix
from src.page_classifier import classify_page_with_gpt
from arihant_pipeline.pipeline_config import PipelineConfig


app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


_VISION_MAX_WORKERS = 8

_VLM_VALIDATE_URL   = "http://localhost:11434/api/chat"
_VLM_VALIDATE_MODEL = "qwen2.5vl:7b"

_VLM_COMPARE_PROMPT = (
    "You are a precise exam-question validator.\n\n"
    "The image shows a question cropped from the original exam PDF.\n"
    "Below is the text that was transcribed for this question:\n\n"
    "TRANSCRIPTION:\n{excel_text}\n\n"
    "FIGURE PLACEHOLDERS: The transcription may contain tokens like [Figure 1], "
    "[Figure 2], etc. Each token represents an embedded visual element (figure, "
    "diagram, graph, or image-based answer option) at that position in the question. "
    "A placeholder is correct if a visual element appears at the corresponding "
    "position in the image, and the numbering follows reading order (top-to-bottom).\n\n"
    "Decide whether the transcription is an accurate and complete representation "
    "of the question in the image.\n\n"
    "Evaluate:\n"
    "1. Is the question stem word-for-word correct (wording, numbers, math, units)?\n"
    "2. Are all answer choices present and correctly transcribed?\n"
    "3. Is mathematical notation (fractions, exponents, symbols) accurately captured?\n"
    "4. Are [Figure N] placeholders present wherever a visual appears, in the right positions?\n\n"
    "If the transcription is not a perfect match, list each specific discrepancy in the "
    "'issues' array. Each issue must be concrete and quote the conflicting text, e.g. "
    "\"PDF says '4 m/s²' but transcription says '4 m/s'\", "
    "\"Answer choice (3) is missing\", "
    "\"[Figure 1] placeholder missing before the diagram\". "
    "If there are no issues, return an empty array.\n\n"
    'Return ONLY valid JSON with no surrounding text:\n'
    '{{"match": true/false, "issues": ["specific discrepancy 1", "..."], "confidence": 0.0-1.0, "figure_count": N}}\n'
    'where figure_count is the number of distinct visual elements (figures, diagrams, graphs) '
    'visible in the image (not in the transcription).'
)


def _vlm_compare_question(image_path: str, excel_text: str) -> dict:
    """Send the PDF question crop + Excel transcription to a VLM and get a match verdict."""
    prompt = _VLM_COMPARE_PROMPT.format(excel_text=excel_text.strip() or "(empty)")
    try:
        with open(image_path, "rb") as fh:
            image_b64 = base64.b64encode(fh.read()).decode()
        payload = {
            "model": _VLM_VALIDATE_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512},
        }
        resp = _http.post(_VLM_VALIDATE_URL, json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()
        return json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except Exception as exc:
        return {"match": False, "issues": [f"VLM error: {exc}"], "confidence": 0.0, "error": True}



def _normalise_cols(df: pd.DataFrame) -> dict:
    """Return {normalised_name: original_column_name} for all columns."""
    return {
        c.strip().lower().replace(" ", "_").replace("#", "num"): c
        for c in df.columns
    }


def _pick_col(norm: dict, aliases: list):
    for a in aliases:
        if a in norm:
            return norm[a]
    return None


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

        questions_md   = parse_pdf(questions_path)["markdown"]
        processor      = PDFProcessor(questions_path, answers_path)
        questions_list = processor.parse_questions(questions_md)
        answers_list   = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

        if not questions_list:
            return jsonify({"error": "No questions could be extracted from the PDF"}), 422

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'extracted_qa.xlsx')
        wb = Workbook()
        ws = wb.active
        ws.title = "Q&A"

        max_figs = max((len(FIGURE_URL_RE.findall(q)) for q in questions_list), default=0)
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
            urls   = FIGURE_URL_RE.findall(question)
            q_text = latex_to_unicode(sanitize(inline_fig_labels(question)))

            ws.append([idx, q_text] + [None] * max_figs + [sanitize(answer)])
            row = ws.max_row
            ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            for n, url in enumerate(urls):
                fig_cell           = ws.cell(row, 3 + n)
                fig_cell.value     = f"View Figure {n + 1}"
                fig_cell.hyperlink = url
                fig_cell.font      = FIG_FONT
                fig_cell.alignment = Alignment(horizontal="center", vertical="top")
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


# ── DISABLED: Evaluate (PDFs) ─────────────────────────────────────────────────
# @app.route('/api/evaluate', methods=['POST'])
# def evaluate_qa():
#     questions_path = None
#     answers_path = None
#     try:
#         is_valid, error_msg = validate_request()
#         if not is_valid:
#             return jsonify({"error": error_msg}), 400
#
#         agent_id        = request.form.get("agent_id", "524829a7-ad2d-4bd4-b094-3a8ef5b62a9e")
#         deployment_slug = request.form.get("deployment_slug", "test123")
#
#         questions_file = request.files['questions_pdf']
#         answers_file   = request.files['answers_pdf']
#
#         questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
#         answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))
#
#         questions_file.save(questions_path)
#         answers_file.save(answers_path)
#
#         processor      = PDFProcessor(questions_path, answers_path)
#         questions_list = processor.parse_questions(processor.extract_text_from_pdf(questions_path))
#         answers_list   = processor.parse_answers(processor.extract_text_from_pdf(answers_path))
#
#         if not questions_list:
#             return jsonify({"error": "No questions could be parsed from the PDF"}), 422
#
#         api_responses, statuses = [], []
#         for idx, question in enumerate(questions_list):
#             correct_answer = answers_list[idx] if idx < len(answers_list) else "N/A"
#             api_resp = call_search_api(question, agent_id, deployment_slug)
#             api_responses.append(api_resp)
#             statuses.append(check_correctness(api_resp, correct_answer))
#
#         output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_results.xlsx')
#         build_evaluation_excel(
#             questions_list,
#             [answers_list[i] if i < len(answers_list) else "N/A" for i in range(len(questions_list))],
#             api_responses,
#             statuses,
#             output_excel,
#         )
#
#         return send_file(
#             output_excel,
#             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
#             as_attachment=True,
#             download_name=f'evaluation_{len(statuses)}q.xlsx',
#         )
#
#     except Exception as e:
#         return jsonify({"error": f"Processing error: {str(e)}"}), 500
#     finally:
#         for path in (questions_path, answers_path):
#             try:
#                 if path and os.path.exists(path):
#                     os.remove(path)
#             except Exception:
#                 pass


# ── DISABLED: Evaluate (Excel) ────────────────────────────────────────────────
# @app.route('/api/evaluate-excel', methods=['POST'])
# def evaluate_from_excel():
#     excel_path = None
#     try:
#         if 'qa_excel' not in request.files:
#             return jsonify({"error": "Missing required file: 'qa_excel'"}), 400
#
#         excel_file = request.files['qa_excel']
#         if excel_file.filename == '':
#             return jsonify({"error": "File name cannot be empty"}), 400
#         if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
#             return jsonify({"error": "Only Excel files (.xlsx) are accepted"}), 400
#
#         agent_id        = request.form.get("agent_id", "524829a7-ad2d-4bd4-b094-3a8ef5b62a9e")
#         deployment_slug = request.form.get("deployment_slug", "test123")
#
#         excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
#         excel_file.save(excel_path)
#
#         ws_in = load_workbook(excel_path).active
#         rows = [r for r in ws_in.iter_rows(min_row=2, values_only=True) if r[0] is not None]
#
#         if not rows:
#             return jsonify({"error": "No data rows found in the Excel file"}), 422
#
#         questions_list = [str(r[1]) if r[1] is not None else "" for r in rows]
#         answers_list   = [str(r[2]) if r[2] is not None else "N/A" for r in rows]
#
#         api_responses, statuses = [], []
#         for question, correct_answer in zip(questions_list, answers_list):
#             api_resp = call_search_api(question, agent_id, deployment_slug)
#             api_responses.append(api_resp)
#             statuses.append(check_correctness(api_resp, correct_answer))
#
#         output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'evaluation_from_excel.xlsx')
#         build_evaluation_excel(questions_list, answers_list, api_responses, statuses, output_excel)
#
#         return send_file(
#             output_excel,
#             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
#             as_attachment=True,
#             download_name=f'evaluation_{len(statuses)}q.xlsx',
#         )
#
#     except Exception as e:
#         return jsonify({"error": f"Processing error: {str(e)}"}), 500
#     finally:
#         try:
#             if excel_path and os.path.exists(excel_path):
#                 os.remove(excel_path)
#         except Exception:
#             pass


# ── DISABLED: Clean Excel ─────────────────────────────────────────────────────
# @app.route('/api/clean-excel', methods=['POST'])
# def clean_excel():
#     excel_path = None
#     try:
#         if 'qa_excel' not in request.files:
#             return jsonify({"error": "Missing required file: 'qa_excel'"}), 400
#
#         excel_file = request.files['qa_excel']
#         if excel_file.filename == '':
#             return jsonify({"error": "File name cannot be empty"}), 400
#         if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
#             return jsonify({"error": "Only Excel files (.xlsx) are accepted"}), 400
#
#         excel_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
#         excel_file.save(excel_path)
#
#         wb = load_workbook(excel_path)
#         ws = wb.active
#         for row in ws.iter_rows(min_row=2):
#             cell = row[1]  # column B — Question
#             if cell.value:
#                 cell.value = sanitize(clean_question(str(cell.value)))
#
#         output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'cleaned_qa.xlsx')
#         wb.save(output_path)
#
#         return send_file(
#             output_path,
#             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
#             as_attachment=True,
#             download_name='cleaned_qa.xlsx',
#         )
#
#     except Exception as e:
#         return jsonify({"error": f"Processing error: {str(e)}"}), 500
#     finally:
#         try:
#             if excel_path and os.path.exists(excel_path):
#                 os.remove(excel_path)
#         except Exception:
#             pass


def _prepare_work_dirs(base_dir: str) -> tuple:
    questions_dir = os.path.join(base_dir, 'questions')
    figures_dir   = os.path.join(base_dir, 'figures')
    os.makedirs(questions_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)
    return questions_dir, figures_dir


def _run_pdf_pipeline(questions_path: str, answers_path: str,
                      questions_dir: str, figures_dir: str) -> tuple:
    crop_by_qnum = crop_questions_from_pdf(questions_path, questions_dir)
    fig_data     = extract_figures_from_pdf(questions_path, figures_dir)
    mapping      = build_question_mapping(questions_path, answers_path, fig_data)
    return crop_by_qnum, mapping


def _transcribe_entry(entry: dict, crop_by_qnum: dict, model: str) -> dict:
    crop_path = crop_by_qnum.get(entry["question_num"])
    figs = entry.get("figure") or []
    if crop_path and os.path.exists(crop_path):
        try:
            q_text = call_vision(crop_path, figure_count=len(figs), model=model)
        except Exception as exc:
            q_text = f"[vision error: {exc}]"
    else:
        q_text = ""
    return {
        "question_num":  str(entry["question_num"]),
        "question_text": sanitize(latex_to_unicode(q_text)),
        "answers":       sanitize(latex_to_unicode(entry.get("answer", "N/A") or "N/A")),
        "figures":       ", ".join(os.path.basename(p) for p in figs),
    }


def _transcribe_all_parallel(mapping: list, crop_by_qnum: dict, model: str) -> list:
    resolved = model if not model.startswith("claude") else model
    workers = 3 if resolved.startswith("claude") else _VISION_MAX_WORKERS
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_transcribe_entry, entry, crop_by_qnum, model) for entry in mapping]
    return [f.result() for f in futures]


def _write_questions_excel(result: list, output_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"

    ws.append(["question_num", "question_text", "figures", "answers"])
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for entry in result:
        ws.append([entry["question_num"], entry["question_text"], entry["figures"], entry["answers"]])
        row = ws.max_row
        ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row, 2).alignment = Alignment(horizontal="left",   vertical="top", wrap_text=True)
        ws.cell(row, 3).alignment = Alignment(horizontal="left",   vertical="top", wrap_text=True)
        ws.cell(row, 4).alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 70
    ws.column_dimensions['C'].width = 35
    ws.column_dimensions['D'].width = 18
    wb.save(output_path)


@app.route('/api/pdf-to-images', methods=['POST'])
def pdf_to_images():
    questions_path = None
    answers_path = None
    try:
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        model          = request.form.get("model", "qwen2.5vl:7b")
        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))
        questions_file.save(questions_path)
        answers_file.save(answers_path)

        questions_dir, figures_dir = _prepare_work_dirs(os.getcwd())
        crop_by_qnum, mapping = _run_pdf_pipeline(
            questions_path, answers_path, questions_dir, figures_dir,
        )
        result = _transcribe_all_parallel(mapping, crop_by_qnum, model)

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'questions_output.xlsx')
        _write_questions_excel(result, output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='questions_output.xlsx',
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


def _transcribe_entry_mathpix(entry: dict, crop_by_qnum: dict, model: str) -> dict:
    crop_path = crop_by_qnum.get(entry["question_num"])
    figs = entry.get("figure") or []
    if crop_path and os.path.exists(crop_path):
        try:
            q_text = call_mathpix(crop_path, model=model)
        except Exception as exc:
            q_text = f"[mathpix error: {exc}]"
    else:
        q_text = ""
    return {
        "question_num":  str(entry["question_num"]),
        "question_text": sanitize(latex_to_unicode(q_text)),
        "answers":       sanitize(latex_to_unicode(entry.get("answer", "N/A") or "N/A")),
        "figures":       ", ".join(os.path.basename(p) for p in figs),
    }


def _transcribe_all_mathpix_parallel(mapping: list, crop_by_qnum: dict, model: str) -> list:
    with ThreadPoolExecutor(max_workers=_VISION_MAX_WORKERS) as executor:
        futures = [executor.submit(_transcribe_entry_mathpix, entry, crop_by_qnum, model)
                   for entry in mapping]
    return [f.result() for f in futures]


@app.route('/api/extract-mathpix', methods=['POST'])
def extract_mathpix():
    questions_path = None
    answers_path = None
    try:
        is_valid, error_msg = validate_request()
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        model = request.form.get("model", "text")

        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))
        questions_file.save(questions_path)
        answers_file.save(answers_path)

        questions_dir, figures_dir = _prepare_work_dirs(os.getcwd())
        crop_by_qnum, mapping = _run_pdf_pipeline(
            questions_path, answers_path, questions_dir, figures_dir,
        )
        result = _transcribe_all_mathpix_parallel(mapping, crop_by_qnum, model)

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'mathpix_output.xlsx')
        _write_questions_excel(result, output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='mathpix_output.xlsx',
        )

    except RuntimeError as e:
        return jsonify({"error": str(e)}), 501
    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        for path in (questions_path, answers_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


@app.route('/api/validate', methods=['POST'])
def validate_qa():
    """Validate an Excel Q&A sheet against questions_pdf and answers_pdf.

    Inputs (multipart/form-data):
        questions_pdf  — PDF of exam questions (source of truth)
        answers_pdf    — PDF of answer key  (source of truth)
        excel          — .xlsx/.xls with columns: question_number, question_text, answer

    Returns an Excel workbook with validation results per question.
    """
    questions_path = answers_path = excel_path = None
    upload_folder = app.config['UPLOAD_FOLDER']
    try:
        # ── Input validation ──────────────────────────────────────────────────
        for field in ('questions_pdf', 'answers_pdf', 'excel'):
            if field not in request.files:
                return jsonify({"error": f"Missing required field: '{field}'"}), 400

        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']
        excel_file     = request.files['excel']

        if not (allowed_file(questions_file.filename) and allowed_file(answers_file.filename)):
            return jsonify({"error": "questions_pdf and answers_pdf must be PDF files"}), 400
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "excel must be an .xlsx or .xls file"}), 400

        # ── Save uploads ──────────────────────────────────────────────────────
        questions_path = os.path.join(upload_folder, secure_filename(questions_file.filename))
        answers_path   = os.path.join(upload_folder, secure_filename(answers_file.filename))
        excel_path     = os.path.join(upload_folder, secure_filename(excel_file.filename))

        questions_file.save(questions_path)
        answers_file.save(answers_path)
        excel_file.save(excel_path)

        # ── Crop question images + extract figures per question ───────────────
        base_dir         = os.getcwd()
        questions_dir    = os.path.join(base_dir, 'questions')
        check_images_dir = os.path.join(base_dir, 'check_images')
        os.makedirs(questions_dir, exist_ok=True)
        os.makedirs(check_images_dir, exist_ok=True)

        crop_by_qnum     = crop_questions_from_pdf(questions_path, questions_dir)
        q_figures_by_num = extract_figures_per_question(questions_path, check_images_dir)

        if not crop_by_qnum:
            return jsonify({"error": "No questions could be detected in questions_pdf"}), 422

        # ── Parse answers from answers PDF (index-based: Q1 → index 0) ───────
        processor    = PDFProcessor(questions_path, answers_path)
        answers_list = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

        # ── Load Excel ────────────────────────────────────────────────────────
        df   = pd.read_excel(excel_path)
        norm = _normalise_cols(df)

        q_num_col  = _pick_col(norm, ['question_number', 'question_num', 'q_num', 'qnum', 'num'])
        q_text_col = _pick_col(norm, ['question_text', 'question', 'q_text', 'qtext'])
        ans_col    = _pick_col(norm, ['answer', 'correct_answer', 'answers'])
        fig_col    = _pick_col(norm, ['figures', 'figure', 'figure_names'])

        if not q_num_col or not q_text_col:
            return jsonify({"error": "Excel must have question_number and question_text columns"}), 422

        excel_by_qnum: dict = {}
        for _, row in df.iterrows():
            raw_num = row.get(q_num_col)
            if raw_num is None:
                continue
            try:
                q_num = int(raw_num)
            except (ValueError, TypeError):
                continue
            excel_by_qnum[q_num] = {
                "question_text": "" if pd.isna(row[q_text_col]) else str(row[q_text_col]),
                "answer":        ("" if pd.isna(row[ans_col]) else str(row[ans_col])) if ans_col else "",
                "figures":       ("" if pd.isna(row[fig_col]) else str(row[fig_col])) if fig_col else "",
            }

        # ── VLM: for each Excel question, compare crop image + check figures ──
        results = []

        for q_num in sorted(excel_by_qnum.keys()):
            exc_entry  = excel_by_qnum[q_num]
            excel_q    = exc_entry["question_text"]
            excel_a    = exc_entry["answer"]
            excel_figs = exc_entry["figures"]

            pdf_a          = sanitize(latex_to_unicode(
                answers_list[q_num - 1] if (q_num - 1) < len(answers_list) else "N/A"
            ))
            crop_path      = crop_by_qnum.get(q_num)
            extracted_figs = q_figures_by_num.get(q_num, [])

            if crop_path and os.path.exists(crop_path):
                vlm_result      = _vlm_compare_question(crop_path, excel_q)
                match_type      = "VLM"
                match_score     = round(vlm_result.get("confidence", 0.0) * 100)
                q_match         = None if vlm_result.get("error") else vlm_result.get("match", False)
                issues          = vlm_result.get("issues") or []
                reason          = "; ".join(issues) if issues else ""
                image_fig_count = 0 if vlm_result.get("error") else int(vlm_result.get("figure_count", 0))
            else:
                match_type      = "No Image"
                match_score     = 0
                q_match         = None
                reason          = "No question image available"
                image_fig_count = 0

            # Figure match: compare extracted figure count vs Excel figure entries
            excel_fig_names = [n.strip() for n in excel_figs.split(",") if n.strip()]
            extracted_count = len(extracted_figs)
            figures_match   = extracted_count == len(excel_fig_names)

            if not figures_match:
                fig_reason = (
                    f"Figure mismatch: image has {extracted_count} figure(s), "
                    f"Excel lists {len(excel_fig_names)}"
                )
                reason = f"{reason}; {fig_reason}" if reason else fig_reason

            ans_sim = _fuzz.ratio(pdf_a.strip(), excel_a.strip())
            if q_match is None:
                status = "Manual Review"
            elif not q_match:
                status = "Incorrect"
            elif not excel_a:
                status = "Manual Review"
            elif ans_sim >= 80:
                status = "Correct"
            else:
                status = "Incorrect"

            results.append({
                "q_num":             q_num,
                "excel_question":    excel_q,
                "pdf_answer":        pdf_a,
                "excel_answer":      excel_a,
                "match_type":        match_type,
                "match_score":       match_score,
                "status":            status,
                "reason":            reason,
                "image_fig_count":   image_fig_count,
                "validated_figures": ", ".join(os.path.basename(p) for p in extracted_figs),
                "excel_figures":     excel_figs,
                "figures_match":     figures_match,
            })

        if not results:
            return jsonify({"error": "No matching questions found between Excel and PDF"}), 422

        output_excel = os.path.join(upload_folder, 'validation_output.xlsx')
        build_validation_excel(results, output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'validation_{len(results)}q.xlsx',
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        for path in (questions_path, answers_path, excel_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass



# ---------------------------------------------------------------------------
# Prompts for the robust two-step question extraction pipeline
# ---------------------------------------------------------------------------

_QUESTION_TRANSCRIBE_PROMPT = """\
This image shows exactly one exam question. Extract it completely.

Rules:
1. Include the question number, the full question stem, and ALL answer choices \
   (e.g. (1)(2)(3)(4) or (A)(B)(C)(D)) exactly as printed.
2. If a figure, diagram, graph, or image appears anywhere in the question, \
   insert [Figure 1], [Figure 2], etc. at that exact position in the text.
3. Write mathematics in plain Unicode — fractions as a/b, square roots as √x, \
   powers as x² — no LaTeX, no backslashes.
4. Ignore watermarks, page numbers, footers, and any text outside this question.
5. Output ONLY the extracted question text, nothing else.
"""

_SOLUTION_CROP_PROMPT = """\
This image shows exactly one solution or answer entry from an exam paper.
Extract the complete answer or solution text.

Rules:
1. Include the question number and the full answer/solution text exactly as printed.
2. If the answer is a single option (e.g. (a), (b), (c), (d)), output just that.
3. If it is a worked solution, include all steps.
4. Write mathematics in plain Unicode — fractions as a/b, square roots as √x, \
   powers as x² — no LaTeX, no backslashes.
5. Ignore watermarks, page numbers, or any text outside this solution entry.
6. Output ONLY the extracted answer text, nothing else.
"""


# Matches compact answer-key entries: "1.(a)", "2. (c)", "3.b", "10) d", "18.(14.00)", "19.(2130)"
# Group 1 = question number, Group 2 = answer (letter a-d/A-D OR numeric value)
_ANS_KEY_ENTRY_RE = re.compile(
    r'(?<!\d)(\d{1,3})\s*[.)]\s*\(?\s*([a-dA-D]|\d+(?:\.\d+)?)\s*\)?(?!\w)',
)


def _extract_answer_key_from_text(pdf_path: str, s_indices: list) -> dict:
    """Scan solution pages for compact answer-key entries via PyMuPDF text.

    Handles grid-style keys like '1.(a)  2.(c)  3.(b)' that appear inline in
    table rows and cannot be individually cropped by crop_questions_from_pages.

    A page is treated as a key page only when >= 3 entries are found, which
    prevents false positives from incidental number-letter pairs in prose.

    Returns {q_num: "(a)"} — lowercase, parenthesised.
    """
    import fitz as _fitz
    doc = _fitz.open(pdf_path)
    answers: dict = {}
    try:
        for page_idx in s_indices:
            if page_idx >= len(doc):
                continue
            text = doc[page_idx].get_text("text")
            matches = _ANS_KEY_ENTRY_RE.findall(text)
            if len(matches) < 3:
                continue
            for q_str, ans_letter in matches:
                q_num = int(q_str)
                if q_num not in answers:          # first occurrence per question wins
                    answers[q_num] = f"({ans_letter.lower()})"
    finally:
        doc.close()
    return answers


def _extract_question_texts(pdf_path: str, q_indices: list,
                             layout_by_page: dict, model: str,
                             output_crops_dir: str = None,
                             answers_dir: str = None) -> tuple:
    """Crop each question with PyMuPDF text detection, then VLM transcribes each crop.

    When answers_dir is provided, uses crop_questions_and_answers_from_pages to split
    each block at its Sol./Ans. line — question part → output_crops_dir,
    answer part → answers_dir.

    Returns (texts_dict, crops_dict) where texts_dict = {q_num: text}
    and crops_dict = {q_num: absolute_path} for the question crops only.
    """
    import shutil

    use_temp = output_crops_dir is None
    crop_dir = tempfile.mkdtemp() if use_temp else output_crops_dir
    if not use_temp:
        os.makedirs(crop_dir, exist_ok=True)

    try:
        if answers_dir is not None:
            os.makedirs(answers_dir, exist_ok=True)
            crops, _ = crop_questions_and_answers_from_pages(
                pdf_path, q_indices, crop_dir, answers_dir,
                layout_by_page=layout_by_page,
            )
        else:
            crops = crop_questions_from_pages(
                pdf_path, q_indices, crop_dir,
                prefix="question", layout_by_page=layout_by_page,
            )

        if not crops:
            return {}, {}

        resolved = _MODEL_ALIASES.get(model, model)
        workers = 3 if resolved.startswith("claude") else _VISION_MAX_WORKERS

        def _do(item):
            q_num, crop_path = item
            try:
                text = call_vision_with_prompt(crop_path, _QUESTION_TRANSCRIBE_PROMPT, model)
                return q_num, text.strip()
            except Exception:
                return q_num, ""

        texts = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for q_num, text in pool.map(_do, crops.items()):
                if text:
                    texts[q_num] = text
        return texts, crops

    finally:
        if use_temp:
            shutil.rmtree(crop_dir, ignore_errors=True)


def _extract_solution_texts(pdf_path: str, s_indices: list,
                             layout_by_page: dict, model: str,
                             output_crops_dir: str = None) -> tuple:
    """Crop each solution entry with PyMuPDF text detection, then VLM transcribes each crop.

    Returns (texts_dict, crops_dict) where texts_dict = {q_num: text}
    and crops_dict = {q_num: absolute_image_path}.
    When output_crops_dir is given the crops are saved there permanently;
    otherwise a temp dir is used and cleaned up.
    """
    import shutil

    use_temp = output_crops_dir is None
    crop_dir = tempfile.mkdtemp() if use_temp else output_crops_dir
    if not use_temp:
        os.makedirs(crop_dir, exist_ok=True)

    try:
        crops = crop_questions_from_pages(
            pdf_path, s_indices, crop_dir,
            prefix="solution", layout_by_page=layout_by_page,
        )

        if not crops:
            return {}, {}

        resolved = _MODEL_ALIASES.get(model, model)
        workers = 3 if resolved.startswith("claude") else _VISION_MAX_WORKERS

        def _do(item):
            q_num, crop_path = item
            try:
                text = call_vision_with_prompt(crop_path, _SOLUTION_CROP_PROMPT, model)
                return q_num, text.strip()
            except Exception:
                return q_num, ""

        texts = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for q_num, text in pool.map(_do, crops.items()):
                if text:
                    texts[q_num] = text
        return texts, crops

    finally:
        if use_temp:
            shutil.rmtree(crop_dir, ignore_errors=True)


@app.route('/api/general-purpose-extraction', methods=['POST'])
def general_purpose_extraction():
    """Classify each page of an uploaded PDF as theory, questions, solutions, or misc."""
    pdf_path = None
    tmp_dir = None
    try:
        if 'pdf' not in request.files:
            return jsonify({"error": "Missing required file: pdf"}), 400

        pdf_file = request.files['pdf']
        if not pdf_file.filename or not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Uploaded file must be a PDF"}), 400

        model    = request.form.get("model", "qwen2.5vl:7b")
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(pdf_file.filename))
        pdf_file.save(pdf_path)

        tmp_dir = tempfile.mkdtemp()
        page_images = pdf_pages_to_png(pdf_path, tmp_dir, prefix="page")

        results = []
        for page_num, image_path in enumerate(page_images, start=1):
            classification = classify_page_with_gpt(image_path)
            page_type = classification.get("page_type")

            entry = {
                "page": page_num,
                "page_type": page_type,
                "confidence": classification.get("confidence"),
                "reason": classification.get("reason"),
                "layout": None,
            }

            if page_type in ("questions", "solutions"):
                layout = detect_layout_fitz(pdf_path, page_num - 1)
                layout_type = layout.get("layout", "single_column")
                entry["layout"] = {
                    "type": layout_type,
                    "columns": layout.get("columns"),
                    "confidence": layout.get("confidence"),
                    "reason": layout.get("reason"),
                }
                saved = save_page_crops(
                    pdf_path, page_num - 1, layout_type, page_type, base_dir=os.getcwd()
                )
                entry["saved_images"] = saved

            results.append(entry)

        q_indices = [p["page"] - 1 for p in results if p["page_type"] == "questions"]
        s_indices = [p["page"] - 1 for p in results if p["page_type"] == "solutions"]

        q_layout = {
            p["page"] - 1: (p["layout"]["type"] if p["layout"] else "single_column")
            for p in results if p["page_type"] == "questions"
        }
        s_layout = {
            p["page"] - 1: (p["layout"]["type"] if p["layout"] else "single_column")
            for p in results if p["page_type"] == "solutions"
        }

        q_images_dir = os.path.join(os.getcwd(), "question_images")
        a_images_dir = os.path.join(os.getcwd(), "answer_images")
        os.makedirs(q_images_dir, exist_ok=True)
        os.makedirs(a_images_dir, exist_ok=True)

        q_texts, q_crops = _extract_question_texts(
            pdf_path, q_indices, q_layout, model, q_images_dir, answers_dir=a_images_dir,
        )
        s_texts, s_crops = _extract_solution_texts(pdf_path, s_indices, s_layout, model, a_images_dir)

        # Fallback: when per-entry marker detection found nothing, save the full
        # pre-rendered page PNG so the output dirs are never empty.
        import shutil as _shutil
        if not q_crops:
            for page_idx in q_indices:
                src = page_images[page_idx]
                _shutil.copy2(src, os.path.join(q_images_dir, f"question_page_{page_idx + 1:03d}.png"))
        if not s_crops:
            for page_idx in s_indices:
                src = page_images[page_idx]
                _shutil.copy2(src, os.path.join(a_images_dir, f"answer_page_{page_idx + 1:03d}.png"))

        # Compact answer key (e.g. "1.(a)  2.(c)  3.(b)") is extracted via text
        # scan — no cropping needed — and overrides crop+VLM answers when present.
        key_answers = _extract_answer_key_from_text(pdf_path, s_indices)
        merged_answers = {**s_texts, **key_answers}   # key_answers wins on conflict

        # Extract figures embedded in question pages and map to question numbers.
        figs_dir = os.path.join(tmp_dir, "figures")
        q_fig_data = extract_figures_from_pages(pdf_path, q_indices, figs_dir)
        q_fig_map = map_figures_to_questions_on_pages(pdf_path, q_indices, q_fig_data)

        excel_rows = [
            {
                "question_num":  str(q_num),
                "question_text": sanitize(latex_to_unicode(q_texts.get(q_num, ""))),
                "figures":       ", ".join(os.path.basename(p) for p in q_fig_map.get(q_num, [])),
                "answers":       sanitize(latex_to_unicode(merged_answers.get(q_num, ""))),
            }
            for q_num in sorted(set(q_texts) | set(merged_answers))
        ]

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'general_extraction_output.xlsx')
        _write_questions_excel(excel_rows, output_excel)

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='general_extraction_output.xlsx',
        )

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500
    finally:
        import shutil
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


@app.route('/api/arihant-pdfs', methods=['POST'])
def arihant_pdfs():
    pdf_path = None

    try:
        # -----------------------------
        # Validate request
        # -----------------------------
        if 'pdf' not in request.files:
            return jsonify({"error": "Missing required file: pdf"}), 400

        pdf_file = request.files['pdf']

        if (
            not pdf_file.filename
            or not pdf_file.filename.lower().endswith('.pdf')
        ):
            return jsonify({"error": "Uploaded file must be a PDF"}), 400

        # -----------------------------
        # Save uploaded PDF
        # -----------------------------
        model_name = request.form.get(
            "model",
            "claude-haiku"
        )

        pdf_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            secure_filename(pdf_file.filename)
        )

        pdf_file.save(pdf_path)

        # -----------------------------
        # Build pipeline config
        # -----------------------------
        config = PipelineConfig(
            vlm_model=model_name,
            dpi=300,
            crop_padding=12,
            enable_mathpix=True,
            pipeline_type="arihant"
        )

        # -----------------------------
        # Run pipeline
        # -----------------------------
        pipeline = GeneralPurposeExtractionPipeline(config)

        result = pipeline.run(pdf_path)

        # -----------------------------
        # Export
        # -----------------------------
        exporter = Exporter(config)

        output_excel = exporter.export(
            result,
            output_dir=app.config['UPLOAD_FOLDER']
        )

        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='arihant_extraction.xlsx',
        )

    except Exception as e:
        return jsonify({
            "error": f"Processing error: {str(e)}"
        }), 500

    finally:
        import shutil

        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass
if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5000)

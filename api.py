import os
import re
import base64
import tempfile
import requests
import fitz  # PyMuPDF
from difflib import SequenceMatcher
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

_Q_PATTERN = re.compile(r'^\s*(?:Q\.?\s*)?(\d+)[.)]\s', re.IGNORECASE)
_DPI = 150
_MAT = fitz.Matrix(_DPI / 72, _DPI / 72)


def _pdf_pages_to_png(pdf_path: str, output_dir: str, prefix: str) -> list:
    """Render every page of a PDF to a PNG file and return the list of saved paths."""
    doc = fitz.open(pdf_path)
    paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=_MAT)
        out_path = os.path.join(output_dir, f'{prefix}_page_{i + 1:03d}.png')
        pix.save(out_path)
        paths.append(out_path)
    doc.close()
    return paths


def _extract_figures_from_pdf(pdf_path: str, output_dir: str) -> list:
    """Extract every embedded image from the PDF and save to output_dir.

    Returns a list of (page_idx, y_top, saved_path) so callers can do
    position-based question assignment.
    """
    doc = fitz.open(pdf_path)
    results = []
    seen_xrefs = set()
    fig_idx = 1
    for page_idx, page in enumerate(doc):
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            rects = page.get_image_rects(xref)
            y_top = rects[0].y0 if rects else 0.0
            base_image = doc.extract_image(xref)
            ext = base_image["ext"]
            out_path = os.path.join(output_dir, f'figure_{fig_idx:03d}.{ext}')
            with open(out_path, 'wb') as f:
                f.write(base_image["image"])
            results.append((page_idx, y_top, out_path))
            fig_idx += 1
    doc.close()
    return results


def _build_question_mapping(questions_path: str, answers_path: str, fig_data: list) -> list:
    """
    Return [{"question_num": N, "figure": [...] | None, "answer": "..."}, ...].

    fig_data: list of (page_idx, y_top, path) from _extract_figures_from_pdf.
    Figures are matched to questions by comparing their (page, y) position
    against the question markers detected in the questions PDF.
    """
    processor = PDFProcessor(questions_path, answers_path)
    answers_list = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

    doc = fitz.open(questions_path)
    markers = []          # [(q_num, page_idx, y_top), ...] in reading order
    expected_num = None
    for page_idx, page in enumerate(doc):
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        for block in blocks:
            if block[6] != 0:
                continue
            first_line = block[4].strip().split('\n')[0]
            m = _Q_PATTERN.match(first_line)
            if not m:
                continue
            num = int(m.group(1))
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, block[1]))
                expected_num = num + 1
    doc.close()

    def _find_question(img_page: int, img_y: float):
        """Last marker whose start is at or before (img_page, img_y)."""
        result = None
        for q_num, q_page, q_y in markers:
            if q_page < img_page or (q_page == img_page and q_y <= img_y):
                result = q_num
            else:
                break
        return result

    q_figures: dict = {q_num: [] for q_num, _, _ in markers}
    for img_page, img_y, path in sorted(fig_data, key=lambda x: (x[0], x[1])):
        q_num = _find_question(img_page, img_y)
        if q_num is not None and q_num in q_figures:
            q_figures[q_num].append(path)

    mapping = []
    for i, (q_num, _, _) in enumerate(markers):
        figs = q_figures.get(q_num, [])
        mapping.append({
            "question_num": q_num,
            "figure":       figs if figs else None,
            "answer":       answers_list[i] if i < len(answers_list) else "N/A",
        })
    return mapping


def _crop_questions_from_pdf(pdf_path: str, output_dir: str) -> list:
    """
    Detect question boundaries via sequential numbered patterns (e.g. "1.", "Q2.")
    and crop each question region to its own PNG file.

    Key invariant: only a block whose number equals expected_next is accepted as a
    question marker. This prevents answer-choice labels, sub-items, or any stray
    "N." text inside a question body from being mistaken for a new question start.

    Falls back to one PNG per page when no question markers are found.
    """
    doc = fitz.open(pdf_path)
    markers = []          # [(page_idx, y0), ...]
    expected_num = None   # set to first matched number; then incremented by 1 each time

    for page_idx, page in enumerate(doc):
        # Sort blocks top-to-bottom, left-to-right to guarantee reading order
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        for block in blocks:
            if block[6] != 0:  # skip image blocks
                continue
            first_line = block[4].strip().split('\n')[0]
            m = _Q_PATTERN.match(first_line)
            if not m:
                continue
            num = int(m.group(1))
            # Accept the very first match at any number; after that only accept num == expected
            if expected_num is None or num == expected_num:
                markers.append((page_idx, block[1]))
                expected_num = num + 1

    paths = []

    if not markers:
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=_MAT)
            out_path = os.path.join(output_dir, f'question_{page_idx + 1:03d}.png')
            pix.save(out_path)
            paths.append(out_path)
        doc.close()
        return paths

    for q_idx, (page_idx, y_top) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect

        if q_idx + 1 < len(markers):
            next_page_idx, next_y = markers[q_idx + 1]
            y_bottom = next_y if next_page_idx == page_idx else page_rect.height
        else:
            y_bottom = page_rect.height

        x0 = 0.0
        y0 = max(0.0, y_top - 5)
        x1 = page_rect.width
        y1 = min(page_rect.height, y_bottom)

        if y1 - y0 < 1 or x1 - x0 < 1:
            continue

        clip = fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f'question_{q_idx + 1:03d}.png')
        pix.save(out_path)
        paths.append(out_path)

    doc.close()
    return paths

_OLLAMA_URL   = "http://localhost:11434/api/chat"
_VISION_MODEL = "qwen2.5vl:7b"

_VISION_PROMPT_TEMPLATE = """\
You are an expert exam question extractor.

STEP 1 — SCAN THE ENTIRE IMAGE FOR VISUAL ELEMENTS:
Before reading any text, look at the whole image and identify every figure, \
graph, diagram, or image — both inside the question stem and inside any answer options.

STEP 2 — EXTRACT THE FULL QUESTION TEXT from top to bottom.

IMAGE PLACEHOLDER RULES (follow exactly):
{figure_instruction}

EXTRACTION RULES:
1. Start from the actual question body. Do NOT include source/header lines \
   (e.g. "JEE Main 2024 Shift 1").
2. Extract text exactly as visible. Do not rephrase or summarise.
3. Include the question number and all answer choices (1) (2) (3) (4) if present.
4. Write math in plain Unicode: fractions as (a)/(b), square roots as √(x). \
   No LaTeX, no backslashes.
5. Ignore watermarks and footers (MathonGo, MARKS App, page numbers, etc.).

Output ONLY the extracted question text. No JSON, no explanation, no commentary.\
"""

_FIGURE_RULE_PRESENT = """\
- This question HAS embedded visual element(s).
- Where a figure/diagram/graph appears INSIDE the question stem, insert [IMAGE] \
  on its own line at exactly that position in the text.
- If an answer option IS a graph/diagram/image (not a text value), write that option as:
    (1) [IMAGE]
  Do this for every such option.
- Place each [IMAGE] where the visual physically sits — do NOT group them at the end.\
"""

_FIGURE_RULE_ABSENT = """\
- No figures were extracted from this question by the PDF parser.
- If you can still see a figure, graph, diagram, or image anywhere in the crop, \
  insert [IMAGE] at that exact position (same rules as above).
- If there are truly no visual elements, do not write any [IMAGE] token.\
"""


def _call_vision_model(image_path: str, has_figures: bool = False) -> str:
    """Send a question-crop image to Ollama and return the extracted text."""
    rule = _FIGURE_RULE_PRESENT if has_figures else _FIGURE_RULE_ABSENT
    prompt = _VISION_PROMPT_TEMPLATE.format(figure_instruction=rule)
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    payload = {
        "model": _VISION_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 1024},
    }
    resp = requests.post(_OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


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


def _build_validation_excel(results: list, output_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Validation"

    ws.append(["Q #", "PDF Question", "Excel Question", "PDF Answer", "Excel Answer", "Match", "Score %", "Status"])

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    status_styles = {
        "Correct":               (PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
                                  Font(color="006100", bold=True)),
        "Incorrect":             (PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
                                  Font(color="9C0006", bold=True)),
        "Manual Review":         (PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
                                  Font(color="9C6500", bold=True)),
        "Not Found":             (PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid"),
                                  Font(color="595959", bold=True)),
        "Missing in Submission": (PatternFill(start_color="F2CEEF", end_color="F2CEEF", fill_type="solid"),
                                  Font(color="7030A0", bold=True)),
    }

    for r in results:
        ws.append([
            r["q_num"],
            sanitize(r["pdf_question"]),
            sanitize(r["excel_question"]),
            sanitize(r["pdf_answer"]),
            sanitize(r["excel_answer"]),
            r["match_type"],
            r["match_score"],
            r["status"],
        ])
        row = ws.max_row
        ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row, 2).alignment = Alignment(horizontal="left",   vertical="top", wrap_text=True)
        ws.cell(row, 3).alignment = Alignment(horizontal="left",   vertical="top", wrap_text=True)
        ws.cell(row, 4).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row, 5).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row, 6).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row, 7).alignment = Alignment(horizontal="center", vertical="center")

        fill, font = status_styles.get(r["status"], status_styles["Manual Review"])
        status_cell = ws.cell(row, 8)
        status_cell.fill = fill
        status_cell.font = font
        status_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 55
    ws.column_dimensions['C'].width = 55
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 18
    ws.column_dimensions['F'].width = 12
    ws.column_dimensions['G'].width = 10
    ws.column_dimensions['H'].width = 22

    wb.save(output_path)


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



@app.route('/api/pdf-to-images', methods=['POST'])
def pdf_to_images():
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

        base_dir      = os.getcwd()
        pages_dir     = os.path.join(base_dir, 'pages')
        questions_dir = os.path.join(base_dir, 'questions')
        figures_dir   = os.path.join(base_dir, 'figures')
        os.makedirs(pages_dir, exist_ok=True)
        os.makedirs(questions_dir, exist_ok=True)
        os.makedirs(figures_dir, exist_ok=True)

        _pdf_pages_to_png(questions_path, pages_dir, prefix='questions')
        _pdf_pages_to_png(answers_path,   pages_dir, prefix='answers')
        q_crops  = _crop_questions_from_pdf(questions_path, questions_dir)
        fig_data = _extract_figures_from_pdf(questions_path, figures_dir)
        mapping  = _build_question_mapping(questions_path, answers_path, fig_data)

        # Both _crop_questions_from_pdf and _build_question_mapping detect the same
        # markers in the same order, so index i in q_crops == index i in mapping.
        crop_by_qnum = {
            entry["question_num"]: q_crops[i]
            for i, entry in enumerate(mapping)
            if i < len(q_crops)
        }

        result = []
        for entry in mapping:
            crop_path = crop_by_qnum.get(entry["question_num"])
            figs = entry.get("figure") or []
            if crop_path and os.path.exists(crop_path):
                try:
                    q_text = _call_vision_model(crop_path, has_figures=bool(figs))
                except Exception as vision_err:
                    q_text = f"[vision error: {vision_err}]"
            else:
                q_text = ""

            figures_str = ", ".join(os.path.basename(p) for p in figs)

            result.append({
                "question_num":  str(entry["question_num"]),
                "question_text": sanitize(latex_to_unicode(q_text)),
                "answers":       sanitize(latex_to_unicode(entry.get("answer", "N/A") or "N/A")),
                "figures":       figures_str,
            })

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

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'questions_output.xlsx')
        wb.save(output_excel)

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


@app.route('/api/validate', methods=['POST'])
def validate_qa():
    questions_path = None
    answers_path   = None
    excel_path     = None
    try:
        for field in ('questions_pdf', 'answers_pdf', 'submission_excel'):
            if field not in request.files:
                return jsonify({"error": f"Missing required file: '{field}'"}), 400

        questions_file = request.files['questions_pdf']
        answers_file   = request.files['answers_pdf']
        excel_file     = request.files['submission_excel']

        if not (allowed_file(questions_file.filename) and allowed_file(answers_file.filename)):
            return jsonify({"error": "Only PDF files are allowed for questions and answers"}), 400
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Only Excel files (.xlsx / .xls) are accepted for submission"}), 400

        questions_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(questions_file.filename))
        answers_path   = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(answers_file.filename))
        excel_path     = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(excel_file.filename))
        questions_file.save(questions_path)
        answers_file.save(answers_path)
        excel_file.save(excel_path)

        # ── Extract from PDFs ──────────────────────────────────────────────────
        processor     = PDFProcessor(questions_path, answers_path)
        pdf_questions = processor.parse_questions(processor.extract_text_from_pdf(questions_path))
        pdf_answers   = processor.parse_answers(processor.extract_text_from_pdf(answers_path))

        if not pdf_questions:
            return jsonify({"error": "No questions could be extracted from the questions PDF"}), 422

        pdf_lookup = {
            i + 1: {
                "question": pdf_questions[i],
                "answer":   pdf_answers[i] if i < len(pdf_answers) else "N/A",
            }
            for i in range(len(pdf_questions))
        }

        # ── Read submission Excel ──────────────────────────────────────────────
        ws_in = load_workbook(excel_path).active
        submission_rows = []
        for row in ws_in.iter_rows(min_row=2, values_only=True):
            if all(v is None for v in row):
                continue
            q_num  = row[0]
            q_text = str(row[1]) if row[1] is not None else ""
            # Answer is the last non-None value in the row
            answer = next((str(v) for v in reversed(row) if v is not None), "N/A")
            submission_rows.append({
                "q_num":    int(q_num) if isinstance(q_num, (int, float)) else None,
                "question": q_text,
                "answer":   answer,
            })

        if not submission_rows:
            return jsonify({"error": "No data rows found in the submission Excel"}), 422

        # ── Match and validate ─────────────────────────────────────────────────
        results          = []
        matched_pdf_nums = set()

        for sub in submission_rows:
            sub_qnum     = sub["q_num"]
            sub_question = sub["question"]
            sub_answer   = sub["answer"]

            if sub_qnum is not None and sub_qnum in pdf_lookup:
                pdf_entry   = pdf_lookup[sub_qnum]
                match_type  = "Exact"
                match_score = 100
                matched_pdf_nums.add(sub_qnum)
            else:
                best_score, best_qnum = 0.0, None
                for qnum, entry in pdf_lookup.items():
                    score = SequenceMatcher(None, sub_question.lower(), entry["question"].lower()).ratio() * 100
                    if score > best_score:
                        best_score, best_qnum = score, qnum

                if best_qnum is not None and best_score >= 60:
                    pdf_entry   = pdf_lookup[best_qnum]
                    match_type  = "Fuzzy"
                    match_score = round(best_score, 1)
                    sub_qnum    = best_qnum
                    matched_pdf_nums.add(best_qnum)
                else:
                    pdf_entry   = {"question": "N/A", "answer": "N/A"}
                    match_type  = "Not Found"
                    match_score = 0

            if match_type == "Not Found":
                status = "Not Found"
            else:
                status = check_correctness(sub_answer, pdf_entry["answer"])

            results.append({
                "q_num":        sub_qnum,
                "pdf_question": pdf_entry["question"],
                "excel_question": sub_question,
                "pdf_answer":   pdf_entry["answer"],
                "excel_answer": sub_answer,
                "match_type":   match_type,
                "match_score":  match_score,
                "status":       status,
            })

        # Flag PDF questions absent from the submission
        for qnum, entry in sorted(pdf_lookup.items()):
            if qnum not in matched_pdf_nums:
                results.append({
                    "q_num":         qnum,
                    "pdf_question":  entry["question"],
                    "excel_question": "N/A",
                    "pdf_answer":    entry["answer"],
                    "excel_answer":  "N/A",
                    "match_type":    "Missing",
                    "match_score":   0,
                    "status":        "Missing in Submission",
                })

        results.sort(key=lambda r: (r["q_num"] is None, r["q_num"] or 0))

        output_excel = os.path.join(app.config['UPLOAD_FOLDER'], 'validation_results.xlsx')
        _build_validation_excel(results, output_excel)

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


if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5000)

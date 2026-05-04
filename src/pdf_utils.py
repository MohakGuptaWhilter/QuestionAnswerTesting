import os
import re
import fitz  # PyMuPDF
from src.pdf_processor import PDFProcessor

_Q_PATTERN = re.compile(r'^\s*(?:Q\.?\s*)?(\d+)[.)]\s', re.IGNORECASE)
_DPI = 150
_MAT = fitz.Matrix(_DPI / 72, _DPI / 72)


def pdf_pages_to_png(pdf_path: str, output_dir: str, prefix: str) -> list:
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


def extract_figures_from_pdf(pdf_path: str, output_dir: str) -> list:
    """Extract every embedded image from the PDF and save to output_dir.

    Returns a list of (page_idx, y_top, saved_path) for position-based
    question assignment.
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


def build_question_mapping(questions_path: str, answers_path: str, fig_data: list) -> list:
    """Return [{"question_num": N, "figure": [...] | None, "answer": "..."}, ...].

    fig_data: list of (page_idx, y_top, path) from extract_figures_from_pdf.
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


def crop_questions_from_pdf(pdf_path: str, output_dir: str) -> list:
    """Detect question boundaries via sequential numbered patterns and crop each
    question region to its own PNG file.

    Key invariant: only a block whose number equals expected_next is accepted as a
    question marker. Falls back to one PNG per page when no markers are found.
    """
    doc = fitz.open(pdf_path)
    markers = []
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

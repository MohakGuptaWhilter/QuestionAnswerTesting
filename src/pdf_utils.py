import os
import re
import numpy as np
import fitz  # PyMuPDF
from src.pdf_processor import PDFProcessor

_Q_PATTERN = re.compile(
    r'^\s*(?:'
    # Alternative 1 — Q / Question prefix present: delimiter is optional (Q1, Q1., Q.1, Q 1.)
    r'Q(?:uestion)?\.?\s*\(?(\d{1,3})[\s.):,]?'
    r'|'
    # Alternative 2 — no prefix: dot/paren must be followed by whitespace OR end-of-string.
    # The end-of-string branch handles "1." alone on its own line (no trailing space).
    # The positive lookahead for a non-digit after [.)] prevents matching decimals like "45.4".
    r'\(?(\d{1,3})[.)](?=\s|$)'
    r')',
    re.IGNORECASE,
)


def _parse_q_num(m) -> int:
    """Return the question number from a _Q_PATTERN match (handles both alternatives)."""
    return int(m.group(1) if m.group(1) is not None else m.group(2))
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
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, block[1]))
                expected_num = num + 1
    doc.close()

    def _find_question(img_page: int, img_y: float):
        """Last marker whose start is at or before (img_page, img_y).
        Falls back to Q1 for figures that appear above the first question marker."""
        result = None
        for q_num, q_page, q_y in markers:
            if q_page < img_page or (q_page == img_page and q_y <= img_y):
                result = q_num
            else:
                break
        if result is None and markers:
            result = markers[0][0]
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


def extract_figures_per_question(pdf_path: str, output_base_dir: str) -> dict:
    """Extract embedded images for each question's region in the PDF.

    Saves each figure to output_base_dir/question_num_{q_num:03d}/figure_{n:03d}.ext
    Returns {q_num: [list of saved figure paths]}.
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
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, block[1]))
                expected_num = num + 1

    if not markers:
        doc.close()
        return {}

    q_ranges = {}
    for q_idx, (q_num, page_idx, y_top) in enumerate(markers):
        page_rect = doc[page_idx].rect
        if q_idx + 1 < len(markers):
            next_q_num, next_page_idx, next_y = markers[q_idx + 1]
            y_bottom = next_y if next_page_idx == page_idx else page_rect.height
        else:
            y_bottom = page_rect.height
        y0 = 0.0 if q_idx == 0 else max(0.0, y_top - 5)
        q_ranges[q_num] = (page_idx, y0, y_bottom)

    q_figures: dict = {q_num: [] for q_num in q_ranges}
    seen_xrefs = set()
    fig_idx = 1

    for page_idx, page in enumerate(doc):
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            img_y = rects[0].y0

            assigned_q = None
            for q_num, (q_page, y0, y_bottom) in q_ranges.items():
                if q_page == page_idx and y0 <= img_y < y_bottom:
                    assigned_q = q_num
                    break
            if assigned_q is None:
                continue

            base_image = doc.extract_image(xref)
            ext = base_image["ext"]
            q_dir = os.path.join(output_base_dir, f'question_num_{assigned_q:03d}')
            os.makedirs(q_dir, exist_ok=True)
            out_path = os.path.join(q_dir, f'figure_{fig_idx:03d}.{ext}')
            with open(out_path, 'wb') as f:
                f.write(base_image["image"])
            q_figures[assigned_q].append(out_path)
            fig_idx += 1

    doc.close()
    return q_figures


def _content_bottom(page, y_start: float, y_limit: float) -> float:
    """Return the y-bottom of the last content block (text or image) whose top
    falls in [y_start, y_limit).  Returns y_start when no blocks are found."""
    bottom = y_start
    for block in page.get_text("blocks"):
        if block[1] < y_start or block[1] >= y_limit:
            continue
        bottom = max(bottom, block[3])
    return bottom


def crop_questions_from_pdf(pdf_path: str, output_dir: str) -> dict:
    """Detect question boundaries via sequential numbered patterns and crop each
    question region to its own PNG file.

    Returns {q_num: path} so callers always look up by question number, not index.
    Falls back to {page_num: path} per page when no markers are found.
    """
    doc = fitz.open(pdf_path)
    markers = []   # [(q_num, page_idx, y_top), ...]
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
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, block[1]))
                expected_num = num + 1

    crops = {}

    if not markers:
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=_MAT)
            out_path = os.path.join(output_dir, f'question_{page_idx + 1:03d}.png')
            pix.save(out_path)
            crops[page_idx + 1] = out_path
        doc.close()
        return crops

    for q_idx, (q_num, page_idx, y_top) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect

        # y_limit: hard upper boundary — the start of the next question (or page bottom).
        # Used only to scope the content search; the actual crop bottom is tighter.
        if q_idx + 1 < len(markers):
            next_q_num, next_page_idx, next_y = markers[q_idx + 1]
            y_limit = next_y if next_page_idx == page_idx else page_rect.height
        else:
            y_limit = page_rect.height

        x0 = 0.0
        y0 = max(0.0, y_top - 5)
        x1 = page_rect.width

        # Tighten the bottom to the last content block (text or image) so the
        # crop contains only the question + options, not the gap before the next question.
        raw_bottom = _content_bottom(page, y_top, y_limit)
        y1 = min(page_rect.height, raw_bottom + 5)

        if y1 - y0 < 1 or x1 - x0 < 1:
            continue

        clip = fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f'question_{q_num:03d}.png')
        pix.save(out_path)
        crops[q_num] = out_path

    doc.close()
    return crops


def save_page_crops(pdf_path: str, page_index: int, layout_type: str,
                    page_type: str, base_dir: str = ".") -> list:
    """Render and save a page (or its left/right halves for multi-column) to disk.

    Files are written to <base_dir>/questions/ or <base_dir>/solutions/.
    Returns a list of saved absolute paths.
    """
    target_dir = os.path.join(base_dir, page_type)
    os.makedirs(target_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    page = doc[page_index]
    rect = page.rect
    page_num = page_index + 1
    saved = []

    if layout_type == "multi_column":
        mid_x = rect.width / 2
        halves = [
            ("left",  fitz.Rect(0,     0, mid_x,      rect.height)),
            ("right", fitz.Rect(mid_x, 0, rect.width, rect.height)),
        ]
        for side, clip in halves:
            pix = page.get_pixmap(matrix=_MAT, clip=clip)
            path = os.path.join(target_dir, f"page_{page_num:03d}_{side}.png")
            pix.save(path)
            saved.append(os.path.abspath(path))
    else:
        pix = page.get_pixmap(matrix=_MAT)
        path = os.path.join(target_dir, f"page_{page_num:03d}.png")
        pix.save(path)
        saved.append(os.path.abspath(path))

    doc.close()
    return saved


def extract_figures_from_pages(pdf_path: str, page_indices: list, output_dir: str) -> list:
    """Extract embedded images from a specific subset of pages.

    Same return format as extract_figures_from_pdf — list of (page_idx, y_top, saved_path) —
    but only processes the pages in page_indices (0-based).
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    results = []
    seen_xrefs = set()
    fig_idx = 1

    for page_idx in sorted(set(page_indices)):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            rects = page.get_image_rects(xref)
            y_top = rects[0].y0 if rects else 0.0
            base_image = doc.extract_image(xref)
            ext = base_image["ext"]
            out_path = os.path.join(output_dir, f"figure_{fig_idx:03d}.{ext}")
            with open(out_path, "wb") as f:
                f.write(base_image["image"])
            results.append((page_idx, y_top, out_path))
            fig_idx += 1

    doc.close()
    return results


def map_figures_to_questions_on_pages(pdf_path: str, page_indices: list, fig_data: list) -> dict:
    """Map figure paths (from extract_figures_from_pages) to question numbers.

    Scans only the specified pages for numbered question markers, then assigns
    each figure to the nearest preceding marker by (page, y) position.
    Returns {q_num: [list_of_figure_paths]}.  Empty dict if no markers found.
    """
    if not page_indices or not fig_data:
        return {}

    doc = fitz.open(pdf_path)
    markers = []
    expected_num = None

    for page_idx in sorted(set(page_indices)):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        for block in blocks:
            if block[6] != 0:
                continue
            first_line = block[4].strip().split('\n')[0]
            m = _Q_PATTERN.match(first_line)
            if not m:
                continue
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, block[1]))
                expected_num = num + 1

    doc.close()

    if not markers:
        return {}

    def _find_nearest(img_page: int, img_y: float):
        result = None
        for q_num, q_page, q_y in markers:
            if q_page < img_page or (q_page == img_page and q_y <= img_y):
                result = q_num
            else:
                break
        return result if result is not None else markers[0][0]

    q_figures: dict = {q_num: [] for q_num, _, _ in markers}
    for img_page, img_y, path in sorted(fig_data, key=lambda x: (x[0], x[1])):
        q_num = _find_nearest(img_page, img_y)
        if q_num in q_figures:
            q_figures[q_num].append(path)

    return q_figures


def _content_bottom_in_col(page, y_start: float, y_limit: float,
                            col_x0: float, col_x1: float) -> float:
    """Like _content_bottom but only considers blocks that overlap the column x-range."""
    bottom = y_start
    for block in page.get_text("blocks"):
        if block[1] < y_start or block[1] >= y_limit:
            continue
        if block[2] <= col_x0 or block[0] >= col_x1:   # no x overlap with column
            continue
        bottom = max(bottom, block[3])
    return bottom


def _detect_col_split(page) -> float:
    """Return the x-coordinate of the gutter between the two columns.

    Rounds block x0 values to 5 px bins, then finds the largest gap in the
    central 20 %–80 % zone of the page.  Falls back to page midpoint when the
    gap is too small to be meaningful (< 5 % of page width).
    """
    pw = page.rect.width
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and len(b[4].strip()) > 10]
    if not blocks:
        return pw / 2

    # Unique x0 positions, rounded to 5 px to merge near-identical column starts
    x0s = sorted(set(round(b[0] / 5) * 5 for b in blocks))
    central = [x for x in x0s if pw * 0.2 <= x <= pw * 0.8]
    if len(central) < 2:
        return pw / 2

    best_gap, split = 0.0, pw / 2
    for i in range(len(central) - 1):
        gap = central[i + 1] - central[i]
        if gap > best_gap:
            best_gap = gap
            split = (central[i] + central[i + 1]) / 2

    return split if best_gap > pw * 0.05 else pw / 2


def _col_split_visual(page) -> float:
    """Detect the column gutter x-coordinate by rendering the page to a grayscale
    image and applying a vertical projection profile.

    The fraction of near-white pixels in each pixel-column is smoothed, then the
    maximum inside the central 25 %–75 % zone is taken as the gutter.  Falls back
    to page midpoint when no clear whitespace strip is found.
    """
    pw = page.rect.width
    pix = page.get_pixmap(matrix=_MAT, colorspace=fitz.csGRAY)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(np.float32)

    # Skip header (top 15 %) and footer (bottom 5 %)
    h, w = gray.shape
    content = gray[int(h * 0.15): int(h * 0.95), :]

    # White-pixel fraction per vertical pixel-column (gutter = densest white strip)
    white_frac = (content > 245).mean(axis=0)

    # Smooth with a box filter ~3 % of image width to find a region, not a hairline
    kernel = max(3, w // 30)
    smoothed = np.convolve(white_frac, np.ones(kernel) / kernel, mode='same')

    lo, hi = int(w * 0.25), int(w * 0.75)
    peak_local = int(np.argmax(smoothed[lo:hi]))
    peak_x_px = lo + peak_local

    # Only trust the result when the peak is meaningfully white (≥ 60 % white)
    if smoothed[peak_x_px] < 0.60:
        return pw / 2

    return peak_x_px * pw / w


def _line_markers_from_page(page) -> list:
    """Return [(line_text, x0, y0), ...] for every text line on the page.

    Uses get_text('dict') so each line's bounding box is derived from its
    individual spans — more precise than block-level coordinates.
    """
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            x0 = spans[0]["bbox"][0]
            y0 = spans[0]["bbox"][1]
            lines.append((text, x0, y0))
    return lines


def crop_questions_visual(pdf_path: str, page_indices: list,
                           output_dir: str, prefix: str = "question",
                           layout_by_page: dict = None) -> dict:
    """Crop question/answer regions using visual column detection.

    Replaces the text-block heuristic in crop_questions_from_pages with two
    improvements:

    1. Column gutter detection via rendered-image vertical projection
       (_col_split_visual) — finds the actual whitespace strip between columns
       regardless of how PDF text blocks are structured or whether column widths
       are unequal.

    2. Q-marker positions from line-level span bounding boxes (_line_markers_from_page)
       — more precise y0 / x0 than the block's bounding box corner.

    Same return format as crop_questions_from_pages: {q_num: absolute_path}.
    """
    os.makedirs(output_dir, exist_ok=True)
    layout_by_page = layout_by_page or {}
    doc = fitz.open(pdf_path)
    page_set = set(page_indices)

    markers = []        # (q_num, page_idx, y_top, x0)
    expected_num = None
    col_split_cache = {}  # page_idx -> gutter x in PDF coordinates

    for page_idx in sorted(page_set):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        layout = layout_by_page.get(page_idx, "single_column")

        if layout == "multi_column":
            mid_x = _col_split_visual(page)
            col_split_cache[page_idx] = mid_x
        else:
            mid_x = page.rect.width  # treat entire page as one column

        # Get all text lines with per-span precision
        all_lines = _line_markers_from_page(page)

        # Sort left column first (by y), then right column (by y)
        if layout == "multi_column":
            left  = sorted([l for l in all_lines if l[1] <  mid_x], key=lambda l: (l[2], l[1]))
            right = sorted([l for l in all_lines if l[1] >= mid_x], key=lambda l: (l[2], l[1]))
            ordered = left + right
        else:
            ordered = sorted(all_lines, key=lambda l: (l[2], l[1]))

        for text, x0, y0 in ordered:
            m = _Q_PATTERN.match(text)
            if not m:
                continue
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, y0, x0))
                expected_num = num + 1

    crops = {}
    if not markers:
        doc.close()
        return crops

    for q_idx, (q_num, page_idx, y_top, block_x0) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect
        layout = layout_by_page.get(page_idx, "single_column")
        mid_x = col_split_cache.get(page_idx, page_rect.width / 2)

        if layout == "multi_column":
            if block_x0 >= mid_x:
                col_x0, col_x1 = mid_x, page_rect.width
            else:
                col_x0, col_x1 = 0.0, mid_x
        else:
            col_x0, col_x1 = 0.0, page_rect.width

        # y_limit: top of the next marker in the same column on the same page
        y_limit = page_rect.height
        if q_idx + 1 < len(markers):
            _, np_idx, ny_top, nbx0 = markers[q_idx + 1]
            if np_idx == page_idx:
                if layout == "multi_column":
                    if (nbx0 >= mid_x) == (block_x0 >= mid_x):
                        y_limit = ny_top
                else:
                    y_limit = ny_top

        y0_crop = max(0.0, y_top - 5)
        raw_bottom = _content_bottom_in_col(page, y_top, y_limit, col_x0, col_x1)
        y1_crop = min(page_rect.height, raw_bottom + 8)

        if y1_crop - y0_crop < 1 or col_x1 - col_x0 < 1:
            continue

        clip = fitz.Rect(col_x0, y0_crop, col_x1, y1_crop)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")
        pix.save(out_path)
        crops[q_num] = os.path.abspath(out_path)

    doc.close()
    return crops


def crop_questions_from_pages(pdf_path: str, page_indices: list,
                               output_dir: str, prefix: str = "question",
                               layout_by_page: dict = None) -> dict:
    """Crop individual question/answer regions from specific pages to PNG files.

    layout_by_page: {page_idx (0-based): "single_column" | "multi_column"}
      For multi_column pages blocks are scanned left-column-first so that the
      sequential expected_num check counts through the left column before moving
      to the right column.  The x-range of each crop is restricted to the column
      where its marker was found.

    Returns {q_num: absolute_path}.
    """
    os.makedirs(output_dir, exist_ok=True)
    layout_by_page = layout_by_page or {}
    doc = fitz.open(pdf_path)
    page_set = set(page_indices)

    # markers: (q_num, page_idx, y_top, block_x0)
    markers = []
    expected_num = None
    col_split_cache = {}  # page_idx -> detected gutter x

    for page_idx in sorted(page_set):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        layout = layout_by_page.get(page_idx, "single_column")

        # Use line-level positions from get_text("dict") so Q-numbers found on any
        # line of a block get the correct y coordinate, not just the block top.
        all_lines = _line_markers_from_page(page)

        if layout == "multi_column":
            mid_x = _detect_col_split(page)
            col_split_cache[page_idx] = mid_x
            left  = sorted([l for l in all_lines if l[1] <  mid_x], key=lambda l: (l[2], l[1]))
            right = sorted([l for l in all_lines if l[1] >= mid_x], key=lambda l: (l[2], l[1]))
            ordered_lines = left + right
        else:
            ordered_lines = sorted(all_lines, key=lambda l: (l[2], l[1]))

        for text, x0, y0 in ordered_lines:
            m = _Q_PATTERN.match(text)
            if not m:
                continue
            num = _parse_q_num(m)
            if expected_num is None or num == expected_num:
                markers.append((num, page_idx, y0, x0))
                expected_num = num + 1

    crops = {}
    if not markers:
        doc.close()
        return crops

    for q_idx, (q_num, page_idx, y_top, block_x0) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect
        layout = layout_by_page.get(page_idx, "single_column")
        mid_x = col_split_cache.get(page_idx, page_rect.width / 2)

        # Column x-range
        if layout == "multi_column":
            if block_x0 >= mid_x:
                col_x0, col_x1 = mid_x, page_rect.width   # right column
            else:
                col_x0, col_x1 = 0.0, mid_x               # left column
        else:
            col_x0, col_x1 = 0.0, page_rect.width

        # y_limit: next marker in the same column on the same page
        y_limit = page_rect.height
        if q_idx + 1 < len(markers):
            _, np_idx, ny_top, nbx0 = markers[q_idx + 1]
            if np_idx == page_idx:
                if layout == "multi_column":
                    if (nbx0 >= mid_x) == (block_x0 >= mid_x):   # same column
                        y_limit = ny_top
                else:
                    y_limit = ny_top

        y0 = max(0.0, y_top - 5)
        raw_bottom = _content_bottom_in_col(page, y_top, y_limit, col_x0, col_x1)
        y1 = min(page_rect.height, raw_bottom + 8)

        if y1 - y0 < 1 or col_x1 - col_x0 < 1:
            continue

        clip = fitz.Rect(col_x0, y0, col_x1, y1)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")
        pix.save(out_path)
        crops[q_num] = os.path.abspath(out_path)

    doc.close()
    return crops


def detect_layout_fitz(pdf_path: str, page_index: int) -> dict:
    """Detect single vs multi-column layout using PyMuPDF text block positions.

    Skips the top 25 % of the page so full-width titles/headers don't pollute
    the column signal.  Returns a dict with: layout, columns, confidence, reason.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    page_width = page.rect.width
    page_height = page.rect.height

    # blocks: (x0, y0, x1, y1, text, block_no, block_type)  block_type 0 = text
    blocks = page.get_text("blocks")
    doc.close()

    # Keep only text blocks in the content body (below the top-25 % header band)
    content_blocks = [
        b for b in blocks
        if b[6] == 0
        and b[1] > page_height * 0.25
        and len(b[4].strip()) > 10
    ]

    if len(content_blocks) < 4:
        return {
            "layout": "single_column",
            "columns": 1,
            "confidence": 0.5,
            "reason": "Too few content blocks to determine layout",
        }

    # A right-column block starts past 35 % of the page width
    col_threshold = page_width * 0.35
    left_blocks  = [b for b in content_blocks if b[0] <= col_threshold]
    right_blocks = [b for b in content_blocks if b[0] >  col_threshold]

    if len(right_blocks) >= 3 and len(left_blocks) >= 3:
        return {
            "layout": "multi_column",
            "columns": 2,
            "confidence": 0.92,
            "reason": (
                f"{len(left_blocks)} blocks in left column, "
                f"{len(right_blocks)} blocks in right column"
            ),
        }

    return {
        "layout": "single_column",
        "columns": 1,
        "confidence": 0.92,
        "reason": f"All {len(content_blocks)} content blocks start in the left region",
    }

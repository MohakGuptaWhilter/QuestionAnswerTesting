import os
import re
import numpy as np
import fitz  # PyMuPDF
from src.pdf_processor import PDFProcessor
from src.crop_questions_hybrid import _visual_col_split

_Q_PATTERN = re.compile(
    r'^\s*(?:'
    # Alternative 1 — Q / Question prefix present: delimiter is optional (Q1, Q1., Q.1, Q 1.)
    r'Q(?:uestion)?\.?\s*\(?(\d{1,3})[\s.):,]?'
    r'|'
    # Alternative 2 — Example / Ex. prefix (e.g. "Example 3", "Ex. 2:", "Ex.4.")
    r'Ex(?:ample)?\.?\s*\(?(\d{1,3})[\s.):,]?'
    r'|'
    # Alternative 3 — no prefix: dot/paren must be followed by whitespace OR end-of-string.
    # The end-of-string branch handles "1." alone on its own line (no trailing space).
    # The positive lookahead for a non-digit after [.)] prevents matching decimals like "45.4".
    r'\(?(\d{1,3})[.)](?=\s|$)'
    r')',
    re.IGNORECASE,
)

# Exercise-only pattern: drops the Ex/Example alternative to avoid false matches on
# question/solution pages where "Example N" appears only as a cross-reference, not a marker.
_Q_PATTERN_EXERCISE = re.compile(
    r'^\s*(?:'
    r'Q(?:uestion)?\.?\s*\(?(\d{1,3})[\s.):,]?'
    r'|'
    r'\(?(\d{1,3})[.)](?=[\s(]|$)'
    r')',
    re.IGNORECASE,
)

# Used to detect answer-key rows: a compact grid like "1. (a)  2. (c)  3. (c)..."
# always contains a SECOND num. entry after the first match.  Single-entry solution
# lines like "9. (a) 28.7 pm × ..." never do.
_Q_INLINE_RE = re.compile(r'(?<!\d)\d{1,3}[.)](?=\s)')


def _parse_q_num(m) -> int:
    """Return the question number from a _Q_PATTERN match (handles all alternatives)."""
    return int(next(g for g in (m.group(1), m.group(2), m.group(3)) if g is not None))


def _parse_q_num_exercise(m) -> int:
    """Return question number from a _Q_PATTERN_EXERCISE match (two groups only)."""
    return int(next(g for g in (m.group(1), m.group(2)) if g is not None))

# Matches lines that start a solution/answer block within an Example.
# Handles: "Sol.", "Sol. (b)", "Solution:", "Ans.", "Ans. (a)", "Answer:"
_SOL_PATTERN = re.compile(
    r'^\s*(?:Sol(?:ution)?|Ans(?:wer)?)[\s.:()\[]',
    re.IGNORECASE,
)

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
        mid_x = _visual_col_split(page)
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


def _merge_rects(rects: list, gap: float = 5.0) -> list:
    """Merge overlapping or nearby fitz.Rect objects into larger bounding boxes."""
    if not rects:
        return []
    merged = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        result = []
        used = [False] * len(merged)
        for i, r in enumerate(merged):
            if used[i]:
                continue
            combined = fitz.Rect(r)
            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue
                expanded = fitz.Rect(
                    combined.x0 - gap, combined.y0 - gap,
                    combined.x1 + gap, combined.y1 + gap,
                )
                if not (expanded & merged[j]).is_empty:
                    combined |= merged[j]
                    used[j] = True
                    changed = True
            result.append(combined)
        merged = result
    return merged


def _find_vector_figure_rects(page, min_area: float = 800.0) -> list:
    """Return bounding rects of significant vector-drawn figures on the page.

    Skips regions that are mostly covered by text blocks (e.g. table borders,
    section dividers) to avoid false positives.
    """
    drawings = page.get_drawings()
    if not drawings:
        return []

    draw_rects = [
        d["rect"] for d in drawings
        if not d["rect"].is_empty and d["rect"].get_area() > 0
    ]
    if not draw_rects:
        return []

    merged = _merge_rects(draw_rects, gap=5.0)

    text_rects = [fitz.Rect(b[:4]) for b in page.get_text("blocks") if b[6] == 0]

    results = []
    for rect in merged:
        if rect.get_area() < min_area:
            continue
        text_area = sum(
            (rect & tr).get_area() for tr in text_rects if not (rect & tr).is_empty
        )
        if text_rects and text_area / rect.get_area() > 0.5:
            continue
        results.append(rect)

    return results


def extract_figures_from_pages(pdf_path: str, page_indices: list, output_dir: str) -> list:
    """Extract figures from a specific subset of pages.

    First tries embedded raster images via get_images(). For pages where no
    embedded images are found, falls back to detecting vector-drawn figures via
    get_drawings() so that typeset diagrams are also captured.

    Same return format as extract_figures_from_pdf — list of (page_idx, y_top, saved_path).
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
        page_fig_count = 0

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            base_image = doc.extract_image(xref)
            if base_image["width"] < 40 or base_image["height"] < 40:
                continue
            rects = page.get_image_rects(xref)
            y_top = rects[0].y0 if rects else 0.0
            ext = base_image["ext"]
            out_path = os.path.join(output_dir, f"figure_{fig_idx:03d}.{ext}")
            with open(out_path, "wb") as f:
                f.write(base_image["image"])
            results.append((page_idx, y_top, out_path))
            fig_idx += 1
            page_fig_count += 1

        # Fallback: detect vector-drawn figures when no embedded images found
        if page_fig_count == 0:
            for fig_rect in _find_vector_figure_rects(page):
                pix = page.get_pixmap(matrix=_MAT, clip=fig_rect)
                out_path = os.path.join(output_dir, f"figure_{fig_idx:03d}.png")
                pix.save(out_path)
                results.append((page_idx, fig_rect.y0, out_path))
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
    section_offset = 0

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
                markers.append((num + section_offset, page_idx, block[1]))
                expected_num = num + 1
            elif num < expected_num and num <= 5 and (expected_num - num) > 5:
                section_offset += expected_num - 1
                markers.append((num + section_offset, page_idx, block[1]))
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
    """Like _content_bottom but only considers blocks that overlap the column x-range.

    A block qualifies when its y-range overlaps [y_start, y_limit) — the block may
    start slightly before y_start because span y-coords (used for markers) are more
    precise than block y-coords.
    """
    bottom = y_start
    for block in page.get_text("blocks"):
        if block[3] <= y_start or block[1] >= y_limit:  # no y overlap
            continue
        if block[2] <= col_x0 or block[0] >= col_x1:    # no x overlap with column
            continue
        # Cap at y_limit: a single block can span multiple questions in dense
        # typesetting — never let one block extend the crop past the next marker.
        bottom = max(bottom, min(block[3], y_limit))
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


def _refine_col_split(page, rough_split: float,
                      min_y: float = 0.0) -> float:
    """Refine a rough column-split estimate to the true gutter midpoint.

    Uses block bounding boxes (restricted to y >= min_y to skip answer-key /
    header rows that can span both columns) to find the maximum right-edge of
    left-column content and the minimum left-edge of right-column content.
    Blocks whose x0 falls within 40 px of rough_split (centered headers,
    gutter labels) are also excluded.
    Falls back to rough_split if the gutter cannot be determined.
    """
    pw = page.rect.width
    margin = 40.0
    blocks = [b for b in page.get_text("blocks")
              if b[6] == 0 and len(b[4].strip()) > 3 and b[1] >= min_y]
    if not blocks:
        return rough_split

    left_x1 = 0.0
    right_x0 = pw
    for b in blocks:
        bx0, bx1 = b[0], b[2]
        # Skip very wide blocks (full-page headers / footers)
        if bx1 - bx0 > pw * 0.7:
            continue
        # Skip blocks whose x0 is close to the rough boundary (gutter noise)
        if abs(bx0 - rough_split) < margin:
            continue
        if bx0 < rough_split:
            left_x1 = max(left_x1, bx1)
        else:
            right_x0 = min(right_x0, bx0)

    if right_x0 > left_x1 and left_x1 > 0 and right_x0 < pw:
        return (left_x1 + right_x0) / 2
    return rough_split


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
    section_offset = 0
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
            m = _Q_PATTERN_EXERCISE.match(text)
            if not m:
                continue
            # Skip answer-key rows: "1. (a)  2. (c)  3. (c)..." has a second entry
            # after the first match; genuine solution lines like "9. (a) 28.7 pm..." do not.
            if _Q_INLINE_RE.search(text[m.end():]):
                continue
            num = _parse_q_num_exercise(m)
            if expected_num is None or num == expected_num:
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1
            elif num < expected_num and num <= 5 and (expected_num - num) > 5:
                # Section numbering restart (e.g. Round II resets to 1 after Round I ends at 76)
                section_offset += expected_num - 1
                markers.append((num + section_offset, page_idx, y0, x0))
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

        if y1_crop - y0_crop < 20 or col_x1 - col_x0 < 1:
            continue

        clip = fitz.Rect(col_x0, y0_crop, col_x1, y1_crop)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")
        pix.save(out_path)
        crops[q_num] = os.path.abspath(out_path)

    doc.close()
    return crops


def _stitch_images_vertically(paths: list, out_path: str) -> None:
    """Stack PNG images top-to-bottom into a single file using Pillow."""
    from PIL import Image
    imgs = [Image.open(p) for p in paths]
    max_w = max(img.width for img in imgs)
    total_h = sum(img.height for img in imgs)
    canvas = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y_off = 0
    for img in imgs:
        canvas.paste(img, (0, y_off))
        y_off += img.height
        img.close()
    canvas.save(out_path)


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
    section_offset = 0
    col_split_cache = {}  # page_idx -> detected gutter x

    for page_idx in sorted(page_set):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        layout = layout_by_page.get(page_idx, "single_column")

        # Use line-level positions from get_text("dict") so Q-numbers found on any
        # line of a block get the correct y coordinate, not just the block top.
        all_lines = _line_markers_from_page(page)
        print(f"[crop_solutions] page {page_idx} layout={layout} lines={len(all_lines)}")

        if layout == "multi_column":
            mid_x = _col_split_visual(page)
            col_split_cache[page_idx] = mid_x
            left  = sorted([l for l in all_lines if l[1] <  mid_x], key=lambda l: (l[2], l[1]))
            right = sorted([l for l in all_lines if l[1] >= mid_x], key=lambda l: (l[2], l[1]))
            ordered_lines = left + right
        else:
            ordered_lines = sorted(all_lines, key=lambda l: (l[2], l[1]))

        for text, x0, y0 in ordered_lines:
            m = _Q_PATTERN_EXERCISE.match(text)
            if not m:
                continue
            if _Q_INLINE_RE.search(text[m.end():]):
                continue  # answer-key row: "1. (a)  2. (c)..." has a second entry
            num = _parse_q_num_exercise(m)
            if expected_num is None or num >= expected_num:
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1
            elif num < expected_num and num <= 5 and (expected_num - num) > 5:
                # Section numbering restart (e.g. Round II resets to 1 after Round I ends at 76)
                section_offset += expected_num - 1
                markers.append((num + section_offset, page_idx, y0, x0))
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
        # cross_page_info: set when the next marker is on a different page
        y_limit = page_rect.height
        cross_page_info = None  # (next_page_idx, next_y_top) when continuation exists
        if q_idx + 1 < len(markers):
            _, np_idx, ny_top, nbx0 = markers[q_idx + 1]
            if np_idx == page_idx:
                if layout == "multi_column":
                    if (nbx0 >= mid_x) == (block_x0 >= mid_x):   # same column
                        y_limit = ny_top
                else:
                    y_limit = ny_top
            else:
                # Next marker is on a different page — content may continue there
                cross_page_info = (np_idx, ny_top)

        y0 = max(0.0, y_top - 5)
        raw_bottom = _content_bottom_in_col(page, y_top, y_limit, col_x0, col_x1)
        y1 = min(page_rect.height, raw_bottom + 8)

        # Skip degenerate single-line crops (answer-key grid entries, stray markers).
        # At 150 DPI a normal body line is ~20 pt → ~42 px; require at least 30 pt.
        if y1 - y0 < 30 or col_x1 - col_x0 < 1:
            continue

        clip = fitz.Rect(col_x0, y0, col_x1, y1)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")

        if cross_page_info is None:
            pix.save(out_path)
        else:
            # This entry's content may spill onto subsequent pages.
            # Build a list of image parts, then stitch them vertically.
            np_idx, ny_top = cross_page_info
            part0 = os.path.join(output_dir, f"{prefix}_{q_num:03d}_part0.png")
            pix.save(part0)
            parts = [part0]

            # Any full pages classified as solution/question pages that fall
            # between the current page and the next-marker page
            for inter_idx in sorted(page_set):
                if inter_idx <= page_idx or inter_idx >= np_idx:
                    continue
                inter_pix = doc[inter_idx].get_pixmap(matrix=_MAT)
                inter_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}_part{inter_idx}.png")
                inter_pix.save(inter_path)
                parts.append(inter_path)

            # Content on the next-marker page before the next entry starts
            if ny_top > 5:
                np_page = doc[np_idx]
                cont_clip = fitz.Rect(0.0, 0.0, np_page.rect.width, ny_top - 5)
                cont_pix = np_page.get_pixmap(matrix=_MAT, clip=cont_clip)
                cont_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}_cont.png")
                cont_pix.save(cont_path)
                parts.append(cont_path)

            if len(parts) == 1:
                os.rename(parts[0], out_path)
            else:
                _stitch_images_vertically(parts, out_path)
                for p in parts:
                    try: os.remove(p)
                    except OSError: pass

        crops[q_num] = os.path.abspath(out_path)

    doc.close()
    return crops

def _detect_answer_key_region(lines):
    """
    Detect dense answer-key grids like:
    1.(a) 2.(b) 3.(c)...   (MCQ)
    18.(14.00) 19.(2130) 20.(26.92)...  (Numeric Value)

    A row qualifies only when it has ≥3 compact entries AND the average
    characters per entry is low (< 20).  The density check prevents long
    solution lines that incidentally contain three numbers from being
    misclassified as answer-key rows.

    Returns:
        (y0, y1) region to ignore
        OR None
    """
    # Matches genuine answer-key entries where the answer is in parentheses:
    #   MCQ:  "1.(a)"  "17.(c)"  "1. (d)"
    #   NVQ:  "18.(14.00)"  "19.(2130)"  "20.(26.92)"
    # The parentheses are REQUIRED so plain chemistry decimals like "69.9",
    # "55.85", "1.25" (which appear in solution tables) never match.
    ANSWER_PAT = re.compile(
        r'(?<!\d)\d{1,3}\s*[.)]\s*\(\s*(?:[a-dA-D]|\d+(?:[.,]\d+)?)\s*\)'
    )
    # Wider bucket so spans on the same visual row that vary by a few pts
    # (common with superscript/subscript rendering) are merged correctly.
    Y_TOLERANCE = 6  # pt

    rows: dict[int, list] = {}
    for text, x0, y0 in lines:
        bucket = round(y0 / Y_TOLERANCE)
        rows.setdefault(bucket, []).append((text, y0))

    candidate_rows = []
    for bucket, items in rows.items():
        combined = " ".join(re.sub(r"\s+", " ", t.strip()) for t, _ in items)
        matches = ANSWER_PAT.findall(combined)
        # Density guard: answer-key entries are compact; solution lines are verbose.
        # "1.(a)" ≈ 5 chars/entry; a solution line with 3 numbers ≈ 60+ chars/entry.
        if len(matches) >= 3 and len(combined) / len(matches) < 20:
            row_y = items[0][1]
            candidate_rows.append(row_y)

    if not candidate_rows:
        return None

    return (
        min(candidate_rows) - 5,
        max(candidate_rows) + 20
    )


def crop_solutions_from_pages(
    pdf_path: str, page_indices: list,
    output_dir: str, prefix: str = "solution",
    layout_by_page: dict = None,
) -> dict:
    """Crop individual solution entries from solution/answer pages to PNG files.

    Key differences from crop_questions_from_pages:
    - Does NOT skip rows where multiple numbered entries appear on one line
      (e.g. answer-key grids "1.(a) 2.(c)...") — those are valid solution starts.
    - Uses a lower minimum crop height (10 pt vs 30 pt) since single-line
      answers like "1. (a)" are common on solution pages.
    - Cross-page stitching works the same way as the question counterpart.

    Returns {q_num: absolute_path}.
    """
    os.makedirs(output_dir, exist_ok=True)
    layout_by_page = layout_by_page or {}
    effective_layout = dict(layout_by_page)  # local copy — augmented with auto-detected layouts
    doc = fitz.open(pdf_path)
    page_set = set(page_indices)

    markers = []
    expected_num = None
    section_offset = 0
    col_split_cache = {}

    for page_idx in sorted(page_set):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        layout = effective_layout.get(page_idx, "single_column")
        all_lines = _line_markers_from_page(page)
        print(f"[crop_solutions] page {page_idx} layout={layout} lines={len(all_lines)}")

        # -----------------------------------
        # Remove entire answer-key region
        # BEFORE column splitting
        # -----------------------------------

        ignore_region = _detect_answer_key_region(all_lines)
        print(f"[crop_solutions] page {page_idx} ignore_region={ignore_region}")

        if ignore_region is not None:
            ignore_y0, ignore_y1 = ignore_region
            solution_lines = [
                l for l in all_lines
                if not (ignore_y0 <= l[2] <= ignore_y1)
            ]
            # If nearly all content was filtered (pure answer-key page misclassified
            # as solutions), skip this page so its entries don't corrupt expected_num.
            filtered_ratio = 1 - len(solution_lines) / max(len(all_lines), 1)
            if filtered_ratio > 0.85:
                print(f"[crop_solutions] page {page_idx}: skipped — {filtered_ratio:.0%} answer-key content")
                continue
        else:
            solution_lines = all_lines

        # Auto-detect two-column layout when not explicitly specified.
        # _detect_col_split finds the largest gap between block x-starts; if it
        # falls significantly off-centre the page is almost certainly two-column.
        # _refine_col_split then adjusts to the actual gutter midpoint using
        # block right-edges, so the crop boundary falls between the columns.
        if layout == "single_column":
            auto_mid = _detect_col_split(page)
            pw = page.rect.width
            if abs(auto_mid - pw / 2) > pw * 0.04:
                # Restrict block analysis to the solution area (below answer key)
                # so that wide answer-key rows don't corrupt the gutter estimate.
                sol_min_y = ignore_region[1] if ignore_region is not None else 0.0
                auto_mid = _refine_col_split(page, auto_mid, min_y=sol_min_y)
                layout = "multi_column"
                effective_layout[page_idx] = "multi_column"
                col_split_cache[page_idx] = auto_mid
                print(f"[crop_solutions] page {page_idx}: auto-detected multi_column split at x={auto_mid:.1f}")

        if layout == "multi_column":
            mid_x = col_split_cache.get(page_idx) or _col_split_visual(page)
            col_split_cache[page_idx] = mid_x
            left  = sorted([l for l in solution_lines if l[1] <  mid_x], key=lambda l: (l[2], l[1]))
            right = sorted([l for l in solution_lines if l[1] >= mid_x], key=lambda l: (l[2], l[1]))
            ordered_lines = left + right
        else:
            ordered_lines = sorted(solution_lines, key=lambda l: (l[2], l[1]))

        # Print first 30 lines so we can see what text the PDF actually produces
        print(f"[crop_solutions] page {page_idx} first lines:")
        for _t, _x, _y in ordered_lines[:30]:
            print(f"  y={_y:.1f} x={_x:.1f} | {_t[:80]!r}")

        page_markers_before = len(markers)
        for text, x0, y0 in ordered_lines:
            m = _Q_PATTERN_EXERCISE.match(text)
            if not m:
                continue
            # Reject plain "N." matches (no Q-prefix) where the remainder starts with
            # a lowercase letter — these are chemistry lines like "22. g of CaO",
            # not question markers.  "(a)" or capital-letter starts are still accepted.
            if m.group(1) is None:
                remainder = text[m.end():].lstrip()
                if remainder and remainder[0].islower():
                    print(f"  [SKIP-CHEM] num={_parse_q_num_exercise(m)} text={text[:40]!r}")
                    continue
            else:
                remainder = ""
            num = _parse_q_num_exercise(m)
            if expected_num is None or num >= expected_num:
                # Reject suspiciously large forward jumps (false positives like
                # "112." appearing as a step/formula number inside a solution body).
                if expected_num is not None and num > expected_num + 30:
                    print(f"  [SKIP-JUMP] num={num} expected_num={expected_num} text={text[:40]!r}")
                    continue
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1
                print(f"  [marker] Q{num+section_offset} at y={y0:.1f} x={x0:.1f}")
            elif num < expected_num and num <= 5 and (expected_num - num) > 5:
                # Require some content after the number for section-reset detection.
                # Standalone "3." or "4." inside a solution body must not be treated
                # as the start of a new section.  Genuine Round-II starters like
                # "1. (c)" or "1. To find..." always carry content.
                if not remainder and num != 1:
                    print(f"  [SKIP] num={num} expected_num={expected_num} text={text[:40]!r}")
                    continue
                section_offset += expected_num - 1
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1
                print(f"  [marker] Q{num+section_offset} at y={y0:.1f} x={x0:.1f} (section reset)")
            else:
                print(f"  [SKIP] num={num} expected_num={expected_num} text={text[:40]!r}")
        print(f"[crop_solutions] page {page_idx}: {len(markers)-page_markers_before} markers added")

    crops = {}
    if not markers:
        doc.close()
        return crops

    for q_idx, (q_num, page_idx, y_top, block_x0) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect
        layout = effective_layout.get(page_idx, "single_column")
        mid_x = col_split_cache.get(page_idx, page_rect.width / 2)

        if layout == "multi_column":
            col_x0, col_x1 = (mid_x, page_rect.width) if block_x0 >= mid_x else (0.0, mid_x)
        else:
            col_x0, col_x1 = 0.0, page_rect.width

        y_limit = page_rect.height
        cross_page_info = None
        if q_idx + 1 < len(markers):
            _, np_idx, ny_top, nbx0 = markers[q_idx + 1]
            if np_idx == page_idx:
                if layout == "multi_column":
                    if (nbx0 >= mid_x) == (block_x0 >= mid_x):
                        y_limit = ny_top
                else:
                    y_limit = ny_top
            else:
                cross_page_info = (np_idx, ny_top)

        y0_crop = max(0.0, y_top - 5)
        if cross_page_info is not None:
            # Solution continues onto the next page — take the full remaining page.
            y1_crop = page_rect.height
        else:
            raw_bottom = _content_bottom_in_col(page, y_top, y_limit, col_x0, col_x1)
            y1_crop = min(page_rect.height, raw_bottom + 8)

        # Lower minimum height than questions (10 pt vs 30 pt) —
        # many solution entries are a single line like "1. (a)".
        if y1_crop - y0_crop < 10 or col_x1 - col_x0 < 1:
            continue

        clip = fitz.Rect(col_x0, y0_crop, col_x1, y1_crop)
        pix = page.get_pixmap(matrix=_MAT, clip=clip)
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")

        if cross_page_info is None:
            pix.save(out_path)
        else:
            np_idx, ny_top = cross_page_info
            part0 = os.path.join(output_dir, f"{prefix}_{q_num:03d}_part0.png")
            pix.save(part0)
            parts = [part0]

            for inter_idx in sorted(page_set):
                if inter_idx <= page_idx or inter_idx >= np_idx:
                    continue
                inter_pix = doc[inter_idx].get_pixmap(matrix=_MAT)
                inter_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}_part{inter_idx}.png")
                inter_pix.save(inter_path)
                parts.append(inter_path)

            if ny_top > 5:
                np_page = doc[np_idx]
                cont_clip = fitz.Rect(0.0, 0.0, np_page.rect.width, ny_top - 5)
                cont_pix = np_page.get_pixmap(matrix=_MAT, clip=cont_clip)
                cont_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}_cont.png")
                cont_pix.save(cont_path)
                parts.append(cont_path)

            if len(parts) == 1:
                os.rename(parts[0], out_path)
            else:
                _stitch_images_vertically(parts, out_path)
                for p in parts:
                    try: os.remove(p)
                    except OSError: pass

        crops[q_num] = os.path.abspath(out_path)

    doc.close()
    return crops


def _find_solution_split(page, y_top: float, y_limit: float,
                          col_x0: float, col_x1: float):
    """Scan text lines in [y_top, y_limit) × [col_x0, col_x1) for a Sol./Ans. marker.

    Returns the y-coordinate of the first matching line, or None if not found.
    """
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            y0_line = spans[0]["bbox"][1]
            x0_line = spans[0]["bbox"][0]
            if y0_line < y_top or y0_line >= y_limit:
                continue
            if x0_line < col_x0 or x0_line >= col_x1:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if _SOL_PATTERN.match(text):
                return y0_line
    return None


def crop_questions_and_answers_from_pages(
    pdf_path: str, page_indices: list,
    questions_dir: str, answers_dir: str,
    layout_by_page: dict = None,
) -> tuple:
    """Crop each Example/Question block and split at the Sol./Ans. boundary.

    For each detected marker region:
    - If a Sol./Ans. line is found inside the block:
        top part  → questions_dir/question_NNN.png
        bottom part → answers_dir/answer_NNN.png
    - Otherwise the full block → questions_dir/question_NNN.png only.

    Returns (q_crops, a_crops) where each is {q_num: absolute_path}.
    """
    os.makedirs(questions_dir, exist_ok=True)
    os.makedirs(answers_dir, exist_ok=True)
    layout_by_page = layout_by_page or {}
    doc = fitz.open(pdf_path)
    page_set = set(page_indices)

    # ── Marker detection (same logic as crop_questions_from_pages) ─────────────
    markers = []
    expected_num = None
    section_offset = 0
    col_split_cache = {}

    for page_idx in sorted(page_set):
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        layout = layout_by_page.get(page_idx, "single_column")
        all_lines = _line_markers_from_page(page)

        if layout == "multi_column":
            mid_x = _col_split_visual(page)
            col_split_cache[page_idx] = mid_x
            left  = sorted([l for l in all_lines if l[1] <  mid_x], key=lambda l: (l[2], l[1]))
            right = sorted([l for l in all_lines if l[1] >= mid_x], key=lambda l: (l[2], l[1]))
            ordered_lines = left + right
        else:
            ordered_lines = sorted(all_lines, key=lambda l: (l[2], l[1]))

        for text, x0, y0 in ordered_lines:
            m = _Q_PATTERN_EXERCISE.match(text)
            if not m:
                continue
            if _Q_INLINE_RE.search(text[m.end():]):
                continue  # answer-key row: "1. (a)  2. (c)..." has a second entry
            num = _parse_q_num_exercise(m)
            if expected_num is None or num == expected_num:
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1
            elif num < expected_num and num <= 5 and (expected_num - num) > 5:
                section_offset += expected_num - 1
                markers.append((num + section_offset, page_idx, y0, x0))
                expected_num = num + 1

    q_crops: dict = {}
    a_crops: dict = {}

    if not markers:
        doc.close()
        return q_crops, a_crops

    # ── Crop each marker region with optional Sol./Ans. split ──────────────────
    for q_idx, (q_num, page_idx, y_top, block_x0) in enumerate(markers):
        page = doc[page_idx]
        page_rect = page.rect
        layout = layout_by_page.get(page_idx, "single_column")
        mid_x = col_split_cache.get(page_idx, page_rect.width / 2)

        if layout == "multi_column":
            col_x0, col_x1 = (mid_x, page_rect.width) if block_x0 >= mid_x else (0.0, mid_x)
        else:
            col_x0, col_x1 = 0.0, page_rect.width

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

        if y1_crop - y0_crop < 20 or col_x1 - col_x0 < 1:
            continue

        sol_y = _find_solution_split(page, y_top, y_limit, col_x0, col_x1)

        if sol_y is not None and sol_y > y_top:
            # Question part
            q_clip = fitz.Rect(col_x0, y0_crop, col_x1, sol_y)
            q_pix = page.get_pixmap(matrix=_MAT, clip=q_clip)
            q_path = os.path.join(questions_dir, f"question_{q_num:03d}.png")
            q_pix.save(q_path)
            q_crops[q_num] = os.path.abspath(q_path)

            # Answer part
            a_clip = fitz.Rect(col_x0, sol_y, col_x1, y1_crop)
            a_pix = page.get_pixmap(matrix=_MAT, clip=a_clip)
            a_path = os.path.join(answers_dir, f"answer_{q_num:03d}.png")
            a_pix.save(a_path)
            a_crops[q_num] = os.path.abspath(a_path)
        else:
            # No solution marker — full block is the question
            q_clip = fitz.Rect(col_x0, y0_crop, col_x1, y1_crop)
            q_pix = page.get_pixmap(matrix=_MAT, clip=q_clip)
            q_path = os.path.join(questions_dir, f"question_{q_num:03d}.png")
            q_pix.save(q_path)
            q_crops[q_num] = os.path.abspath(q_path)

    doc.close()
    return q_crops, a_crops


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

    # Keep only substantive content blocks:
    #   - below the top-10 % header band
    #   - above the bottom-10 % footer/page-number band
    #   - wide enough to be real content (not narrow page-number or watermark glyphs)
    #   - at least 20 chars so single-word watermarks ("SAMPLE", "NW.EXAMS") are excluded
    content_blocks = [
        b for b in blocks
        if b[6] == 0
        and b[1] > page_height * 0.10
        and b[3] < page_height * 0.90
        and (b[2] - b[0]) > page_width * 0.08
        and len(b[4].strip()) > 20
    ]

    if len(content_blocks) < 4:
        return {
            "layout": "single_column",
            "columns": 1,
            "confidence": 0.5,
            "reason": "Too few content blocks to determine layout",
        }

    # A genuine right column starts in the middle zone of the page (30 %–75 %).
    # Blocks that start past 75 % are page numbers, running headers, or binding
    # margins — not a real second column.
    left_threshold  = page_width * 0.30
    right_zone_max  = page_width * 0.75

    left_blocks  = [b for b in content_blocks if b[0] <= left_threshold]
    right_blocks = [b for b in content_blocks if left_threshold < b[0] <= right_zone_max]

    if len(right_blocks) >= 3 and len(left_blocks) >= 3:
        result = {
            "layout": "multi_column",
            "columns": 2,
            "confidence": 0.92,
            "reason": (
                f"{len(left_blocks)} blocks in left column, "
                f"{len(right_blocks)} blocks in right column"
            ),
        }
    else:
        result = {
            "layout": "single_column",
            "columns": 1,
            "confidence": 0.92,
            "reason": f"All {len(content_blocks)} content blocks start in the left region",
        }

    print(
        f"[detect_layout] page {page_index}: {result['layout']}"
        f"  left={len(left_blocks)} right={len(right_blocks)}"
        f"  total_content={len(content_blocks)}"
    )
    return result

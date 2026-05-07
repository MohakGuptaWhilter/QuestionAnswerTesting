"""Hybrid question cropper: PDF text detection + image-based cropping.

Approach
--------
The old PDF-only method (`crop_questions_from_pages`) had two bugs:

1. `_content_bottom_in_col` missed text blocks that *started* above the question
   marker but *extended* into its region, producing near-zero-height crops.

2. `_detect_col_split` (text-based) was unreliable — it picked random gaps between
   right-column block x0 positions instead of the actual gutter.

This module fixes both by combining:

- **PDF text layer** for sequential question-number detection (regex + expected_num
  check) — reliable, handles bold/italic/formatted numbers.

- **Column images** rendered from PDF for the actual crop — avoids all the
  block-overlap and column-range bugs, produces pixel-perfect tight crops
  via horizontal ink-density projection.

- **Visual gutter detection** (_visual_col_split) — finds the real whitespace
  strip between columns by rendering the page to grayscale and scanning
  vertical pixel columns.

Usage
-----
    from crop_questions_hybrid import crop_questions_from_page_images

    crops = crop_questions_from_page_images(
        pdf_path="exam.pdf",
        page_indices=[16, 17],          # 0-based page indices
        output_dir="./cropped",
        layout_by_page={16: "multi_column", 17: "multi_column"},
    )
    # crops = {1: "/abs/path/question_001.png", 2: ..., ...}
"""

import os
import re
import numpy as np
import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Question-number regex (same as existing codebase)
# ---------------------------------------------------------------------------
_Q_PATTERN = re.compile(
    r'^\s*(?:'
    r'Q(?:uestion)?\.?\s*\(?(\d{1,3})[\s.):,]?'
    r'|'
    r'\(?(\d{1,3})[.)](?=\s|$)'
    r')',
    re.IGNORECASE,
)

_DPI = 150
_MAT = fitz.Matrix(_DPI / 72, _DPI / 72)


def _parse_q_num(m) -> int:
    return int(m.group(1) if m.group(1) is not None else m.group(2))


# ---------------------------------------------------------------------------
# Visual column-gutter detection (rendered image approach)
# ---------------------------------------------------------------------------
def _visual_col_split(page) -> float:
    """Return the x-coordinate (in PDF points) of the gutter between two columns.

    Renders the page to grayscale and finds the vertical strip with the highest
    fraction of white pixels in the central 25–75 % zone.  Falls back to page
    midpoint when no clear gutter is found.
    """
    pw = page.rect.width
    pix = page.get_pixmap(matrix=_MAT, colorspace=fitz.csGRAY)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width
    ).astype(np.float32)
    h, w = gray.shape

    # Skip header/footer bands
    content = gray[int(h * 0.15): int(h * 0.95), :]
    white_frac = (content > 245).mean(axis=0)

    kernel = max(3, w // 30)
    smoothed = np.convolve(white_frac, np.ones(kernel) / kernel, mode='same')

    lo, hi = int(w * 0.25), int(w * 0.75)
    peak_local = int(np.argmax(smoothed[lo:hi]))
    peak_x_px = lo + peak_local

    if smoothed[peak_x_px] < 0.60:
        return pw / 2

    return peak_x_px * pw / w


# ---------------------------------------------------------------------------
# PDF text-layer question detection (per-column)
# ---------------------------------------------------------------------------
def _find_q_markers_in_column(page, col_x0: float, col_x1: float,
                               expected_start: int = None) -> list:
    """Find sequentially-numbered question markers within a column x-range.

    Uses line-level span bounding boxes from ``get_text("dict")`` for precise
    y-coordinates.  The ``expected_num`` check enforces sequential numbering
    so stray numbers (inside options, equations, etc.) are skipped.

    Returns [(q_num, y_top_pdf), ...] in reading order.
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
            if col_x0 <= x0 < col_x1:
                lines.append((text, x0, y0))

    lines.sort(key=lambda l: (l[2], l[1]))

    markers = []
    expected = expected_start
    for text, x0, y0 in lines:
        m = _Q_PATTERN.match(text)
        if not m:
            continue
        num = _parse_q_num(m)
        if expected is None or num == expected:
            markers.append((num, y0))
            expected = num + 1

    return markers


# ---------------------------------------------------------------------------
# Image-based cropping between known marker positions
# ---------------------------------------------------------------------------
def _crop_from_image_at_markers(col_img_path: str, markers_px: list,
                                 output_dir: str, prefix: str = "question",
                                 padding: int = 5) -> dict:
    """Crop question regions from a column image at known y-positions.

    Uses horizontal ink-density projection to find the actual content bottom
    for each question (tight crop — no wasted whitespace bleeding into the
    next question's area).

    Parameters
    ----------
    col_img_path : str
        Path to the single-column PNG image.
    markers_px : list of (q_num, y_px)
        Question start positions in pixel coordinates.
    output_dir : str
        Directory to save cropped PNGs.
    prefix : str
        Filename prefix.
    padding : int
        Pixels of padding above and below the crop.

    Returns
    -------
    dict : {q_num: absolute_path}
    """
    from PIL import Image

    img = Image.open(col_img_path)
    gray = np.array(img.convert('L'), dtype=np.float32)
    h, w = gray.shape

    # Row-wise ink density (dark pixels)
    ink = (gray < 200).mean(axis=1)
    smoothed = np.convolve(ink, np.ones(3) / 3, mode='same')
    is_empty = smoothed < 0.003

    crops = {}
    for i, (q_num, y_px) in enumerate(markers_px):
        y_limit = markers_px[i + 1][1] if i + 1 < len(markers_px) else h

        # Content bottom: last non-empty row before y_limit
        content_bottom = y_px
        for y in range(y_px, y_limit):
            if not is_empty[y]:
                content_bottom = y

        y0 = max(0, y_px - padding)
        y1 = min(h, content_bottom + padding + 1)

        if y1 - y0 < 10:
            continue

        crop_img = img.crop((0, y0, w, y1))
        out_path = os.path.join(output_dir, f"{prefix}_{q_num:03d}.png")
        crop_img.save(out_path)
        crops[q_num] = os.path.abspath(out_path)

    return crops


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------
def crop_questions_from_page_images(pdf_path: str, page_indices: list,
                                      output_dir: str, prefix: str = "question",
                                      layout_by_page: dict = None) -> dict:
    """Crop individual questions from PDF pages using the hybrid approach.

    For each page:

    1. Detect column layout via visual gutter detection.
    2. Render each column as a separate PNG image.
    3. Find question markers from the PDF text layer (reliable regex +
       sequential-number check).
    4. Convert marker PDF-coordinate positions to pixel coordinates.
    5. Crop from the column image using horizontal projection for tight bounds.

    Parameters
    ----------
    pdf_path : str
        Path to the PDF file.
    page_indices : list of int
        0-based page indices to process.
    output_dir : str
        Directory to save cropped question PNGs.
    prefix : str
        Filename prefix for output files (default: "question").
    layout_by_page : dict, optional
        {page_idx: "single_column" | "multi_column" | "auto"}.
        Defaults to "auto" for all pages.

    Returns
    -------
    dict : {q_num: absolute_path}
    """
    os.makedirs(output_dir, exist_ok=True)
    layout_by_page = layout_by_page or {}
    doc = fitz.open(pdf_path)

    all_crops = {}
    expected_num = None

    for page_idx in sorted(page_indices):
        page = doc[page_idx]
        rect = page.rect
        layout = layout_by_page.get(page_idx, "auto")

        # --- Determine column layout ---
        if layout == "auto":
            mid_x = _visual_col_split(page)
            if abs(mid_x - rect.width / 2) < rect.width * 0.15:
                layout = "multi_column"
            else:
                layout = "single_column"
                mid_x = rect.width
        elif layout == "multi_column":
            mid_x = _visual_col_split(page)
        else:
            mid_x = rect.width

        # --- Define columns ---
        if layout == "multi_column":
            columns = [
                ("left",  0.0,   mid_x),
                ("right", mid_x, rect.width),
            ]
        else:
            columns = [("full", 0.0, rect.width)]

        for col_name, col_x0, col_x1 in columns:
            # Render column image
            clip = fitz.Rect(col_x0, 0, col_x1, rect.height)
            pix = page.get_pixmap(matrix=_MAT, clip=clip)
            col_img_path = os.path.join(
                output_dir, f"_tmp_col_p{page_idx}_{col_name}.png"
            )
            pix.save(col_img_path)

            # Detect question markers from PDF text
            markers = _find_q_markers_in_column(
                page, col_x0, col_x1, expected_num
            )
            if markers:
                expected_num = markers[-1][0] + 1

            # Convert PDF y → pixel y
            scale = _DPI / 72
            markers_px = [(q_num, int(y_pdf * scale)) for q_num, y_pdf in markers]

            # Crop from column image
            crops = _crop_from_image_at_markers(
                col_img_path, markers_px, output_dir, prefix
            )
            all_crops.update(crops)

            # Clean up temporary column image
            os.remove(col_img_path)

    doc.close()
    return all_crops

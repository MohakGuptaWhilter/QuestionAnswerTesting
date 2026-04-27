"""
GPT-4o-mini vision-based Q&A extractor for educational PDFs.

Strategy:
1. Cheap text pass → detect section/chapter boundaries (headers are text even
   when equations are images, so this is reliable).
2. Render each section's pages as high-resolution PNG images.
3. GPT-4o-mini reads the images — captures equations (returned as LaTeX) and
   geometric diagrams (described in [brackets]) that plain text extraction misses.
4. Orphan matching (questions without answers and vice-versa) is scoped to each
   section, so topics that reuse numbering 1, 2, 3... never cross-contaminate.
"""

import os
import re
import io
import json
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

try:
    from PIL import Image, ImageDraw
    _PIL = True
except ImportError:
    _PIL = False

from dotenv import load_dotenv
from src.figure_mapper import FigureMapper

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"), override=False)
load_dotenv(os.path.join(_ROOT, "src", ".env"), override=False)

try:
    import fitz
    _PYMUPDF = True
except ImportError:
    _PYMUPDF = False

try:
    import pdfplumber
    _PDFPLUMBER = True
except ImportError:
    _PDFPLUMBER = False

_MAX_CHUNK = 5       # max pages per GPT vision call
_RENDER_ZOOM = 2.0   # 144 DPI — clear enough for equations without bloating image size

_VISION_PROMPT = """\
You are an expert educational content extractor with strong mathematical OCR capability.

Analyze the provided PDF page images and extract ONLY questions and their answers/solutions.

━━ WHAT TO EXTRACT ━━
• Numbered practice problems: 1.  2.  (i)  (ii)  Q1.  Q2.  etc.
• Worked examples explicitly posed as problems: "Example 1: Find ...", "Ex. 2: Prove that ..."
• Multiple-choice questions (include all option labels and text)
• Fill-in-the-blank or short-answer questions

━━ WHAT TO SKIP — do NOT extract ━━
• Theory text, definitions, theorems, axioms, or proofs presented as expository content
• Explanatory paragraphs, remarks, notes, motivating discussions, or introductions
• Derivations or demonstrations that are NOT framed as an exercise or worked example with
  an explicit question for the reader to answer
• Section headings, chapter titles, or any instructional/descriptive prose

━━ FORMATTING RULES (follow exactly) ━━
• All mathematical expressions → LaTeX notation
    Inline:  $x^2 + 3x - 4 = 0$
    Display: $$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$
• Greek letters / special symbols → LaTeX: $\\alpha$, $\\theta$, $\\sqrt{2}$, $\\frac{a}{b}$
• Tables → reproduce as plain text with | separators

━━ FIGURE MARKERS ━━
• Every figure region on these pages has been pre-detected and labelled: a red bounding box
  is drawn around it and a "FIGURE N" tag appears at the top-left corner of that box.
• When a labelled figure belongs to a question, insert [[FIGURE_N]] — using the EXACT number
  printed in the red label — at the position in the "question" string where the figure sits.
• Do NOT assign your own numbering. Only reference numbers that are visible as red labels.
• If a figure appears between the question stem and the options, place [[FIGURE_N]] there.
• If a figure appears AFTER all the options (below the MCQ choices), append [[FIGURE_N]] at
  the END of the "question" string.
• If a figure appears below the question text but before any options, place [[FIGURE_N]] after
  the question stem text.
• ALWAYS include [[FIGURE_N]] somewhere in the "question" string whenever a labelled figure
  belongs to that question — never silently omit a figure placeholder.
• If a labelled figure belongs to theory text or explanatory prose (not a question), omit it.

━━ MULTIPLE-CHOICE OPTIONS ━━
• Place ALL option labels and their full text in the "options" array — do NOT embed them in
  the "question" string.
• Preserve the exact label format shown: "(A)", "(1)", "a)", etc.
• Include LaTeX for any math inside options.
  Example: ["(A) $2x$", "(B) $x^2$", "(C) $-x$", "(D) 0"]

Answers may appear:
• Immediately after the question (inline), OR
• In a "Solutions" / "Answer Key" section later on these same pages

Return JSON {"items": [...]} — each item:
  "number"   : exact question identifier as shown (e.g. "1", "Q2", "Example 3")
  "question" : question stem with LaTeX and [[FIGURE_N]] placeholders; null if answer-only entry
  "options"  : list of MCQ option strings; empty list [] if the question is not multiple-choice
  "answer"   : complete solution/answer with LaTeX for all math; null if not on these pages

Rules:
- If a question's answer is not on these pages, set "answer" to null.
- If an answer entry has no corresponding question on these pages, set "question" to null.
- Transcribe all equations exactly as shown — precision is critical.
- Do NOT summarise, paraphrase, or omit steps from solutions.
- Do NOT include theory or expository text even if it contains equations.
"""


# ── Text extraction (cheap, used only for boundary detection) ─────────────────

def _extract_text_pages(pdf_path: str) -> List[str]:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if _PYMUPDF:
        doc = fitz.open(pdf_path)
        pages = [page.get_text("text") for page in doc]
        doc.close()
        if any(p.strip() for p in pages):
            return pages
    if _PDFPLUMBER:
        with pdfplumber.open(pdf_path) as pdf:
            return [p.extract_text() or "" for p in pdf.pages]
    raise RuntimeError("No PDF extraction library available. Install pymupdf or pdfplumber.")


# ── Section boundary detection ────────────────────────────────────────────────

_SECTION_HEADER = re.compile(
    r'^\s*(?:chapter|section|topic|unit|part|module|exercise|lecture)\s+\d+',
    re.IGNORECASE | re.MULTILINE,
)


def _find_section_boundaries(pages_text: List[str]) -> List[int]:
    """
    Return page indices where new sections begin.
    Headers are typically real text even in equation-heavy PDFs, so text
    extraction is reliable enough for this purpose.
    Falls back to [0, len] (treat whole PDF as one section) if nothing found.
    """
    boundaries = [0]
    for i, text in enumerate(pages_text[1:], start=1):
        if _SECTION_HEADER.search(text):
            boundaries.append(i)
    boundaries.append(len(pages_text))
    return boundaries


# ── Image rendering ───────────────────────────────────────────────────────────

def _render_page_b64(doc, page_idx: int) -> str:
    """Render a single PDF page to a base64-encoded PNG."""
    page = doc[page_idx]
    mat = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return base64.b64encode(pix.tobytes("png")).decode()


def _annotate_page_b64(b64_png: str, numbered_regions: List[Tuple[int, object]]) -> str:
    """
    Draw a red bounding box and "FIGURE N" label onto a base64-encoded page PNG
    for each (figure_number, fitz.Rect) pair.  Rect coords are in PDF pt units
    and are scaled by _RENDER_ZOOM to match pixel dimensions.

    Returns the annotated PNG as base64.  Falls back to the original if PIL is
    unavailable or any error occurs.
    """
    if not _PIL or not numbered_regions:
        return b64_png
    try:
        img  = Image.open(io.BytesIO(base64.b64decode(b64_png))).convert('RGB')
        draw = ImageDraw.Draw(img)
        zoom = _RENDER_ZOOM
        for fig_n, rect in numbered_regions:
            x0, y0 = int(rect.x0 * zoom), int(rect.y0 * zoom)
            x1, y1 = int(rect.x1 * zoom), int(rect.y1 * zoom)
            # Red border (2 px thick)
            for off in range(2):
                draw.rectangle([x0 - off, y0 - off, x1 + off, y1 + off],
                               outline=(220, 20, 20))
            # Label badge above the box
            label  = f'FIGURE {fig_n}'
            lx, ly = x0 + 4, max(0, y0 - 16)
            draw.rectangle([lx - 2, ly - 1, lx + 7 * len(label) + 2, ly + 13],
                           fill=(220, 20, 20))
            draw.text((lx, ly), label, fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return b64_png


_FIGURE_MARKER_RE = re.compile(r'\[\[FIGURE_(\d+)\]\]')


def _replace_figure_markers(text: str, figure_map: Dict[int, str]) -> str:
    """Replace [[FIGURE_N]] with [[FIGURE_URL:<s3_url>]] using the pre-built map."""
    if not text or not figure_map:
        return text

    def _sub(m: re.Match) -> str:
        url = figure_map.get(int(m.group(1)))
        return f'[[FIGURE_URL:{url}]]' if url else m.group(0)

    return _FIGURE_MARKER_RE.sub(_sub, text)


# ── GPT vision call ───────────────────────────────────────────────────────────

def _call_gpt_vision(client, images_b64: List[str], model: str) -> List[Dict]:
    content = []
    for img in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img}", "detail": "high"},
        })
    content.append({"type": "text", "text": _VISION_PROMPT})

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    parsed = json.loads(resp.choices[0].message.content)
    if isinstance(parsed, list):
        return parsed
    for key in ("items", "questions", "data", "results"):
        if isinstance(parsed.get(key), list):
            return parsed[key]
    for v in parsed.values():
        if isinstance(v, list):
            return v
    return []


# ── Number normalisation & sorting ────────────────────────────────────────────

def _normalise_key(raw: str) -> str:
    """'1.', 'Q 1', 'Q.1', 'Example 1', 'Ex.1.2' → stable match key."""
    s = raw.strip().lower()
    m = re.match(r'^(?:example|ex\.?)\s*([\d.]+)', s)
    if m:
        return f"ex:{m.group(1)}"
    m = re.match(r'^q\.?\s*(\d+)', s)
    if m:
        return f"q:{m.group(1)}"
    m = re.match(r'^(\d+)', s)
    if m:
        return f"q:{m.group(1)}"
    return s


def _sort_key(key: str) -> Tuple:
    if key.startswith("ex:"):
        return (0,) + tuple(int(d) for d in re.findall(r'\d+', key))
    if key.startswith("q:"):
        return (1,) + tuple(int(d) for d in re.findall(r'\d+', key))
    return (2, 0)


# ── Within-section orphan matching ────────────────────────────────────────────

def _match_section_items(items: List[Dict]) -> List[Dict]:
    """
    Given raw items from one section (question/answer may be null), pair each
    question with its answer by normalised number key.

    Scoping this to a single section prevents cross-section number collisions
    (e.g. Topic 1 Q1 ≠ Topic 2 Q1 even though both are numbered "1").
    """
    complete: List[Dict] = []
    orphan_q: Dict[str, str] = {}
    orphan_a: Dict[str, str] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        raw_num = str(item.get("number") or "").strip()
        q = (item.get("question") or "").strip()
        opts = [str(o) for o in (item.get("options") or []) if o]
        if opts and q:
            q = q + "\n" + "\n".join(opts)
        a = (item.get("answer") or "").strip()
        nkey = _normalise_key(raw_num) if raw_num else ""

        if q and a:
            complete.append({"_key": nkey, "question": q, "answer": a})
        elif q:
            prev = orphan_q.get(nkey)
            orphan_q[nkey] = (prev + "\n" + q) if prev else q
        elif a and nkey:
            prev = orphan_a.get(nkey)
            orphan_a[nkey] = (prev + "\n" + a) if prev else a

    for nkey, q in orphan_q.items():
        complete.append({
            "_key": nkey,
            "question": q,
            "answer": orphan_a.get(nkey, "N/A"),
        })

    return complete


# ── Public API ────────────────────────────────────────────────────────────────

def extract_qa_with_gpt(
    pdf_path: str,
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Extract Q&A pairs from a PDF using GPT-4o-mini vision.

    Equations are returned as LaTeX ($...$  or $$...$$).
    Geometric diagrams are described in [square brackets].
    Complex PDFs with only image-based equations are handled correctly because
    GPT reads the rendered page images rather than extracted text.
    """
    if not _PYMUPDF:
        raise RuntimeError(
            "pymupdf is required for vision mode. Install with: pip install pymupdf"
        )

    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not resolved_key:
        raise ValueError("OPENAI_API_KEY is not set")

    from openai import OpenAI
    client = OpenAI(api_key=resolved_key)

    # Cheap text pass for section boundary detection only
    pages_text = _extract_text_pages(pdf_path)
    boundaries = _find_section_boundaries(pages_text)

    doc = fitz.open(pdf_path)
    all_pairs: List[Dict] = []

    try:
        # Pre-render all chunks sequentially (fitz doc is not thread-safe).
        # Each entry: (section_index, annotated_page_images, figure_map)
        #
        # For each chunk:
        #   1. Detect all figure regions (raster + vector) per page.
        #   2. Number them sequentially (fig_counter restarts at 1 per chunk).
        #   3. Crop + upload each region to S3 → figure_map {N: url}.
        #   4. Render each page PNG and draw red bounding boxes + "FIGURE N"
        #      labels onto it so GPT reads the number from the image directly.
        chunks: List[Tuple] = []
        for bi in range(len(boundaries) - 1):
            sec_start, sec_end = boundaries[bi], boundaries[bi + 1]
            for chunk_s in range(sec_start, sec_end, _MAX_CHUNK):
                chunk_e     = min(chunk_s + _MAX_CHUNK, sec_end)
                page_indices = list(range(chunk_s, chunk_e))

                mapper = FigureMapper(doc, page_indices).build()
                images = [
                    _annotate_page_b64(_render_page_b64(doc, pi),
                                       mapper.page_regions.get(pi, []))
                    for pi in page_indices
                ]
                chunks.append((bi, images, mapper.figure_map, mapper))
    finally:
        doc.close()

    # Fire all GPT vision calls in parallel — same token spend, less wall time.
    # Cap workers at 10 to avoid OpenAI rate-limit errors on large PDFs.
    section_items_map: Dict[int, List[Dict]] = {}
    max_workers = min(len(chunks), 10)

    def _call_chunk(bi, images, fmap, mapper):
        return bi, _call_gpt_vision(client, images, model), fmap, mapper

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_call_chunk, bi, imgs, fmap, mapper): bi
            for bi, imgs, fmap, mapper in chunks
        }
        for future in as_completed(futures):
            try:
                bi, items, figure_map, mapper = future.result()
                for item in items:
                    if item.get("question"):
                        item["question"] = _replace_figure_markers(item["question"], figure_map)
                    if item.get("answer"):
                        item["answer"] = _replace_figure_markers(item["answer"], figure_map)
                mapper.inject(items)  # positional fallback for any figure GPT missed
                section_items_map.setdefault(bi, []).extend(items)
            except Exception:
                continue

    # Reassemble sections in order, then match orphans within each section.
    for bi in range(len(boundaries) - 1):
        all_pairs.extend(_match_section_items(section_items_map.get(bi, [])))

    all_pairs.sort(key=lambda p: _sort_key(p.get("_key", "")))
    for p in all_pairs:
        p.pop("_key", None)

    return all_pairs

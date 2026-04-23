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
import json
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

from dotenv import load_dotenv

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
• Geometric figures / diagrams → concise description in [square brackets]
    Example: [Circle with centre O, radius 5 cm; chord AB perpendicular to diameter CD]
• Multiple-choice options → include all labels and text, e.g. (A) $2x$ (B) $x^2$ (C) $-x$ (D) $0$
• Tables → reproduce as plain text with | separators

Answers may appear:
• Immediately after the question (inline), OR
• In a "Solutions" / "Answer Key" section later on these same pages

Return JSON {"items": [...]} — each item:
  "number"   : exact question identifier as shown (e.g. "1", "Q2", "Example 3")
  "question" : complete question text with LaTeX for all math; null if this is an answer-only entry
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
        # Each entry: (section_index, list_of_base64_images)
        chunks: List[Tuple[int, List[str]]] = []
        for bi in range(len(boundaries) - 1):
            sec_start, sec_end = boundaries[bi], boundaries[bi + 1]
            for chunk_s in range(sec_start, sec_end, _MAX_CHUNK):
                chunk_e = min(chunk_s + _MAX_CHUNK, sec_end)
                images = [_render_page_b64(doc, i) for i in range(chunk_s, chunk_e)]
                chunks.append((bi, images))
    finally:
        doc.close()

    # Fire all GPT vision calls in parallel — same token spend, less wall time.
    # Cap workers at 10 to avoid OpenAI rate-limit errors on large PDFs.
    section_items_map: Dict[int, List[Dict]] = {}
    max_workers = min(len(chunks), 10)

    def _call_chunk(bi: int, images: List[str]) -> Tuple[int, List[Dict]]:
        return bi, _call_gpt_vision(client, images, model)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_call_chunk, bi, imgs): bi for bi, imgs in chunks}
        for future in as_completed(futures):
            try:
                bi, items = future.result()
                section_items_map.setdefault(bi, []).extend(items)
            except Exception:
                continue  # skip bad chunk, don't abort whole PDF

    # Reassemble sections in order, then match orphans within each section.
    for bi in range(len(boundaries) - 1):
        all_pairs.extend(_match_section_items(section_items_map.get(bi, [])))

    all_pairs.sort(key=lambda p: _sort_key(p.get("_key", "")))
    for p in all_pairs:
        p.pop("_key", None)

    return all_pairs

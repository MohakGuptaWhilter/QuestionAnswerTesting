import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

_CLASSIFICATION_PROMPT = (
    "You are a document-page classifier for academic PDFs.\n\n"
    "Classify this page into exactly one of the following categories:\n"
    "- questions: A page that contains PRACTICE or EXERCISE problems for the reader "
    "to solve independently, with NO solution or answer provided on the same page "
    "alongside the problem. This includes: numbered exam/practice problems, "
    "exercise sets, MCQ-style problems where only the question and options appear "
    "(no worked solution inline), and standalone word problems.\n"
    "- solutions: A page that ONLY presents answers or solutions to previously posed "
    "questions and contains NO unsolved practice problems. This includes: standalone "
    "answer keys (e.g. '1.(a) 2.(c) ...'), dedicated 'Solutions' / 'Answers' / "
    "'Hints & Solutions' / 'Answer Key' pages, and pages of compact answer entries.\n"
    "- theory: Explanatory content — definitions, theorems, concepts, formulas, "
    "lecture notes, AND worked examples (blocks headed 'Example N' or 'Ex. N' that "
    "include their own solution or worked steps on the same page). A page that mixes "
    "explanatory text with worked examples (Example + Sol.) is 'theory', not 'questions'.\n"
    "- misc: Cover pages, table of contents, instructions, blank pages, index, bibliography.\n\n"
    "KEY DISTINCTIONS:\n"
    "  • 'Example 3: A ball is thrown… Sol. v = √(2gh) = 14 m/s' → theory "
    "(worked example with solution inline)\n"
    "  • '3. A ball is thrown… Find the velocity.' (no solution given) → questions "
    "(unsolved practice problem)\n"
    "  • '1.(a)  2.(c)  3.(b)  4.(d)…' (only letter answers) → solutions (answer key)\n\n"
    "DECISION ORDER (apply top-to-bottom, stop at first match):\n"
    "1. If the page contains only unsolved practice/exercise problems (no inline solutions) → 'questions'\n"
    "2. If the page is only answer entries or solutions with no unsolved problems → 'solutions'\n"
    "3. If the page contains worked examples (Example N + Sol.) or pure explanatory text → 'theory'\n"
    "4. Otherwise → 'misc'\n\n"
    "Return ONLY a JSON object with no surrounding text:\n"
    '{"page_type": "<theory|questions|solutions|misc>", "confidence": <0.0-1.0>, "reason": "<one short sentence>"}'
)


def classify_page_with_gpt(image_path: str, model: str = "gpt-4o-mini") -> dict:
    """Classify a single PDF page image using GPT-4o-mini.

    Returns a dict with keys: page_type, confidence, reason.
    """
    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        max_tokens=128,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
                {"type": "text", "text": _CLASSIFICATION_PROMPT},
            ],
        }],
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)


_LAYOUT_PROMPT = (
    "You are a document layout analyser for academic PDFs.\n\n"
    "Look at the page and determine how the main content is arranged horizontally.\n\n"
    "Rules:\n"
    "- single_column: All text/content runs in one continuous column that spans most of the page width.\n"
    "- multi_column: Content is split into two or more side-by-side vertical columns "
    "(e.g. two-column exam paper, newspaper-style layout, answer grid).\n\n"
    "Count only the primary content columns, not headers/footers or page-number lines.\n\n"
    "Return ONLY a JSON object with no surrounding text:\n"
    '{"layout": "<single_column|multi_column>", "columns": <integer number of columns>, '
    '"confidence": <0.0-1.0>, "reason": "<one short sentence>"}'
)


def detect_layout_with_gpt(image_path: str, model: str = "gpt-4o-mini") -> dict:
    """Detect whether a page is single-column or multi-column using GPT-4o-mini.

    Returns a dict with keys: layout, columns, confidence, reason.
    Only meaningful for questions/solutions pages.
    """
    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        max_tokens=128,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
                {"type": "text", "text": _LAYOUT_PROMPT},
            ],
        }],
    )

    raw = response.choices[0].message.content.strip()
    return json.loads(raw)

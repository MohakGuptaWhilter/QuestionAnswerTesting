import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

_CLASSIFICATION_PROMPT = (
    "You are a document-page classifier for academic PDFs.\n\n"
    "Classify this page into exactly one of the following categories:\n"
    "- questions: A page that POSES at least one problem, question, or example for the reader "
    "to solve — regardless of whether theory or worked solutions also appear on the same page. "
    "This includes: numbered exam/practice problems, MCQ options (A/B/C/D), word problems, "
    "numbered examples headed 'Example N' (even with solutions shown below them), "
    "and any page that asks the reader to find, calculate, prove, or determine something. "
    "PRIORITY RULE: If even ONE question or example problem appears anywhere on the page, "
    "classify the entire page as 'questions'.\n"
    "- solutions: A page that ONLY presents answers or solutions to previously posed questions "
    "and contains NO new questions being posed. This means: standalone answer keys "
    "(e.g. '1.(a) 2.(c) ...'), a dedicated 'Solutions' / 'Answers' / 'Hints & Solutions' / "
    "'Answer Key' section page with nothing but answer entries. "
    "Do NOT classify as solutions if the page also contains any problem statement, "
    "example problem, or MCQ options.\n"
    "- theory: Pure explanatory content with NO problems posed — definitions, concepts, "
    "theorems, formulas, or lecture notes where nothing is asked of the reader.\n"
    "- misc: Cover pages, table of contents, instructions, blank pages, index, bibliography.\n\n"
    "DECISION ORDER (apply top-to-bottom, stop at first match):\n"
    "1. If the page poses ANY question, problem, or numbered example → 'questions'\n"
    "2. If the page is ONLY answer entries with no questions → 'solutions'\n"
    "3. If the page is pure explanatory text → 'theory'\n"
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

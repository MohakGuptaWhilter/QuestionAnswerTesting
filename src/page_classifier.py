import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

_CLASSIFICATION_PROMPT = """
You are a high-accuracy document page classifier for Indian academic and JEE/NEET exam-preparation PDFs (e.g. Arihant, DC Pandey, HC Verma).

Classify the given page into EXACTLY ONE of five categories: theory, examples, questions, solutions, misc.

=====================================================
STEP 1 — ELIMINATE misc FIRST
=====================================================

Classify as "misc" if the page is clearly administrative or non-educational:
  - Cover page, title page, copyright page
  - Table of contents, index, bibliography
  - Preface, foreword, acknowledgements
  - Blank or near-blank page
  - Publisher advertisements
  - Syllabus / chapter overview list (even if it contains chemistry content in bullet form)
  - Answer key grid ONLY (e.g. "1-a  2-c  3-b  4-d") with no solution working

If the page is misc, STOP and return "misc". Otherwise continue.

=====================================================
STEP 2 — IDENTIFY THE DOMINANT CONTENT
=====================================================

Ask yourself TWO questions in order:

Q1: Is this page part of an EXERCISE SECTION?
  Signs of an exercise section:
    - Section/chapter header: "Exercise", "Practice", "Level 1/2/3", "Objective Questions",
      "Previous Year Questions", "Assertion-Reason", "Integer Type", "Fill in the Blanks"
    - Numbered problems using plain "1.", "2.", "3." numbering (not "Example 1.")
    - MCQ answer option lines "(A) ...(B) ...(C) ...(D)..."
    - Dense list of problems with little prose between them

  If YES — this is an exercise page. Go to Q2 to decide questions vs. solutions.
  If NO  — this is in the chapter body. Go to Q3.

Q2 (exercise pages only): Does each problem have a solution/explanation ON THIS PAGE?
  YES → "solutions" (solutions/answers to exercise problems)
  NO  → "questions" (unsolved exercise problems for the reader to attempt)

  NOTE: MCQ options (A)(B)(C)(D) listed after a question are NOT solutions.
  A solution is "Sol.", "Ans.", "Solution:", option-elimination reasoning, or worked steps.

Q3 (chapter body pages): What is the dominant content?
  Conceptual prose (definitions, derivations, laws, formulas, no exercise Qs) → "theory"
  Labeled worked examples with "Example N." headers and step-by-step solutions → "examples"
  Exercise questions answered with full solutions (in chapter body context) → "solutions"

=====================================================
CATEGORY DEFINITIONS
=====================================================

──────────────────────────────────────────
1. theory
──────────────────────────────────────────
Pure teaching content: concepts, definitions, derivations, laws, formulas.

Strong signals:
  ✔ Long explanatory paragraphs, derivations, proofs
  ✔ Named laws, theorems, principles
  ✔ Formula boxes, key-point boxes, note boxes
  ✔ NO numbered exercise problems on the page

──────────────────────────────────────────
2. examples
──────────────────────────────────────────
Pedagogical worked examples embedded IN THE CHAPTER BODY (NOT in an exercise section).

Strong signals (need BOTH):
  ✔ Problems are labeled with "Example N." or "Solved Example N." or "Illustration N."
    as the HEADING of each problem (not just a reference in text)
  ✔ Each labeled problem is followed immediately by a step-by-step solution
  ✔ The page is clearly in the chapter narrative, NOT inside an "Exercise" / "Practice" section

CRITICAL: Do NOT classify as "examples" if:
  ✗ The page has an "Exercise" or "Practice" section header (→ questions or solutions instead)
  ✗ The "Example" word appears only as a reference ("see Example 5") without being a problem header
  ✗ The problems are plain-numbered (1., 2., 3.) without "Example" prefix

──────────────────────────────────────────
3. solutions
──────────────────────────────────────────
Answers/solutions to exercise or practice problems.

Strong signals:
  ✔ Repeated pattern: numbered problem → "Sol." / "Ans." / "Solution:" → working → answer
  ✔ "Correct option is (X)" or option-elimination reasoning
  ✔ Many problems solved compactly (typically 5+ per page)
  ✔ Compact dense layout, little white space

Key distinction from "examples":
  - "examples": pedagogical, in chapter body, few per page, teaching tone
  - "solutions": exercise-set answers, many per page, repetitive Q→Sol. pattern

──────────────────────────────────────────
4. questions
──────────────────────────────────────────
Unsolved exercise or practice problems.

Strong signals:
  ✔ Numbered problems with NO solution text following them on this page
  ✔ MCQ options (A)(B)(C)(D) listed with NO worked answer after them
  ✔ Section headers: "Exercise", "Practice Set", "Level 1", "Objective Questions",
    "Previous Year Questions", "Assertion-Reason", "Integer Type"
  ✔ Sparse layout, minimal explanatory prose between problems

Do NOT classify as "questions" if solutions/explanations follow each problem.

──────────────────────────────────────────
5. misc
──────────────────────────────────────────
(Handled in Step 1 above.)

=====================================================
DECISION ORDER (apply in this order, stop at first match)
=====================================================

1. misc       — administrative, non-educational
2. questions  — exercise section, problems WITHOUT solutions on this page
3. solutions  — exercise section, problems WITH solutions on this page
4. examples   — chapter body, "Example N." labeled problems with step-by-step solutions
5. theory     — chapter body, conceptual prose, no exercise problems

=====================================================
OUTPUT FORMAT
=====================================================

Return ONLY valid JSON, no surrounding text:

{
  "page_type": "<examples|solutions|theory|questions|misc>",
  "confidence": <0.0–1.0>,
  "reason": "<one concise sentence citing the key signals you observed>"
}
"""


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

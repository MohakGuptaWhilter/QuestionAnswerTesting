import base64
import requests

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


def call_vision_model(image_path: str, has_figures: bool = False) -> str:
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

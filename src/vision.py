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
- This question has {n} embedded visual element(s).
- As you read top-to-bottom, each time a figure, diagram, graph, or image appears \
  insert the next numbered placeholder on its own line: [Figure 1] for the first, \
  [Figure 2] for the second, and so on up to [Figure {n}].
- If an answer option IS a visual (not a text value), write it as "(1) [Figure N]" \
  using the next available number.
- Place each [Figure N] exactly where the visual sits — do NOT group them at the end.\
"""

_FIGURE_RULE_ABSENT = """\
- No figures were extracted from this question by the PDF parser.
- If you can still see a figure, graph, diagram, or image anywhere in the crop, \
  insert [Figure 1] at that exact position (and [Figure 2], [Figure 3], etc. for \
  additional visuals in reading order).
- If there are truly no visual elements, do not write any [Figure N] token.\
"""


def call_vision_model(image_path: str, figure_count: int = 0) -> str:
    """Send a question-crop image to Ollama and return the extracted text."""
    if figure_count > 0:
        rule = _FIGURE_RULE_PRESENT.format(n=figure_count)
    else:
        rule = _FIGURE_RULE_ABSENT
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

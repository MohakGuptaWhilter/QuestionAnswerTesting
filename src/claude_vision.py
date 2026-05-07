import base64
import time
import random
import anthropic

from src.vision import _VISION_PROMPT_TEMPLATE, _FIGURE_RULE_PRESENT, _FIGURE_RULE_ABSENT

_MAX_RETRIES = 6
_BASE_DELAY  = 5.0   # seconds before first retry


def call_vision_model_claude(image_path: str, figure_count: int = 0,
                             model: str = "claude-haiku-4-5-20251001") -> str:
    """Send a question-crop image to Anthropic Claude and return the extracted text.

    Reads ANTHROPIC_API_KEY from the environment.
    Supported models: claude-haiku-4-5-20251001, claude-sonnet-4-6
    Retries up to _MAX_RETRIES times on rate-limit (429) errors with
    exponential backoff + jitter.
    """
    rule = _FIGURE_RULE_PRESENT.format(n=figure_count) if figure_count > 0 else _FIGURE_RULE_ABSENT
    prompt = _VISION_PROMPT_TEMPLATE.format(figure_instruction=rule)

    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()
    messages_payload = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            },
            {"type": "text", "text": prompt},
        ],
    }]

    for attempt in range(_MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                temperature=0,
                messages=messages_payload,
            )
            return message.content[0].text.strip()
        except anthropic.RateLimitError:
            if attempt == _MAX_RETRIES:
                raise
            delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 2)
            time.sleep(delay)

import base64
import anthropic

from src.vision import _VISION_PROMPT_TEMPLATE, _FIGURE_RULE_PRESENT, _FIGURE_RULE_ABSENT


def call_vision_model_claude(image_path: str, figure_count: int = 0,
                             model: str = "claude-haiku-4-5-20251001") -> str:
    """Send a question-crop image to Anthropic Claude and return the extracted text.

    Reads ANTHROPIC_API_KEY from the environment.
    Supported models: claude-haiku-4-5-20251001, claude-sonnet-4-6
    """
    rule = _FIGURE_RULE_PRESENT.format(n=figure_count) if figure_count > 0 else _FIGURE_RULE_ABSENT
    prompt = _VISION_PROMPT_TEMPLATE.format(figure_instruction=rule)

    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return message.content[0].text.strip()

import base64
from openai import OpenAI

from src.vision import _VISION_PROMPT_TEMPLATE, _FIGURE_RULE_PRESENT, _FIGURE_RULE_ABSENT


def call_vision_model_gpt(image_path: str, figure_count: int = 0,
                          model: str = "gpt-4o") -> str:
    """Send a question-crop image to OpenAI and return the extracted text.

    Reads OPENAI_API_KEY from the environment.
    Supported models: gpt-4o, gpt-4o-mini
    """
    rule = _FIGURE_RULE_PRESENT.format(n=figure_count) if figure_count > 0 else _FIGURE_RULE_ABSENT
    prompt = _VISION_PROMPT_TEMPLATE.format(figure_instruction=rule)

    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return response.choices[0].message.content.strip()

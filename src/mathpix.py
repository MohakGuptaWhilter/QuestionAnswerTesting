import base64
import os
import requests

_MATHPIX_URL = "https://api.mathpix.com/v3/text"

# Map the frontend "model" selector to Mathpix output formats.
_FORMAT_MAP = {
    "text":   ["text"],
    "latex":  ["latex_simplified"],
    "full":   ["text", "latex_simplified"],
}


def call_mathpix(image_path: str, model: str = "text") -> str:
    """Extract text from a question-crop image using the Mathpix OCR API."""
    app_id  = os.environ.get("MATHPIX_APP_ID", "")
    app_key = os.environ.get("MATHPIX_APP_KEY", "")
    if not app_id or not app_key:
        raise RuntimeError(
            "MATHPIX_APP_ID and MATHPIX_APP_KEY environment variables must be set."
        )

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    formats = _FORMAT_MAP.get(model, ["text"])
    payload = {
        "src": f"data:image/png;base64,{image_b64}",
        "formats": formats,
        "options_json": '{"rm_spaces": true}',
    }
    headers = {
        "app_id":       app_id,
        "app_key":      app_key,
        "Content-type": "application/json",
    }
    resp = requests.post(_MATHPIX_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if model == "latex" and "latex_simplified" in data:
        return data["latex_simplified"]
    return data.get("text", "")

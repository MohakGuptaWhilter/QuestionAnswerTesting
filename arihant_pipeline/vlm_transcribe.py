from dataclasses import dataclass
from typing import List
import uuid
import numpy as np
from PIL import Image
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class Transcription:
    """
    Represents OCR/VLM transcription output.
    """

    transcription_id: str

    crop_id: str

    region_type: str

    qid: str

    raw_text: str

    normalized_text: str

    confidence: float

    metadata: dict


# =========================================================
# VLM TRANSCRIBER
# =========================================================

class VLMTranscriber:
    """
    Converts semantic crops into machine-readable text.

    Responsibilities:
    - run OCR/VLM inference
    - preserve equations
    - preserve MCQ structure
    - normalize OCR text
    - estimate transcription quality

    IMPORTANT:
    This stage only transcribes.
    It does NOT:
    - parse questions
    - solve questions
    - classify semantics
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.model = getattr(
            config,
            "vlm_model",
            "qwen2.5vl:7b"
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def transcribe(
        self,
        crops,
        max_workers: int = 8,
    ) -> List[Transcription]:

        def _transcribe_one(crop):
            raw_text = self._run_vlm(crop.image)
            normalized = self._normalize_text(raw_text)
            confidence = self._estimate_confidence(normalized)
            return Transcription(
                transcription_id=str(uuid.uuid4()),
                crop_id=crop.crop_id,
                region_type=crop.region_type,
                qid=crop.qid,
                raw_text=raw_text,
                normalized_text=normalized,
                confidence=confidence,
                metadata={
                    "page_number": crop.page_number,
                    "model": self.model,
                    "region_type": crop.region_type,
                },
            )

        results: dict = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_transcribe_one, crop): i
                for i, crop in enumerate(crops)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    print(
                        f"[VLMTranscriber] Failed "
                        f"{crops[idx].crop_id}: {str(e)}"
                    )

        return [results[i] for i in sorted(results)]

    # =====================================================
    # IMAGE CONVERSION
    # =====================================================

    def _image_to_bytes(
        self,
        image: np.ndarray
    ) -> bytes:
        """
        Convert numpy image to PNG bytes.
        """

        pil_image = Image.fromarray(image)

        buffer = io.BytesIO()

        pil_image.save(
            buffer,
            format="PNG"
        )

        return buffer.getvalue()

    # =====================================================
    # VLM CALL
    # =====================================================

    def _run_vlm(
        self,
        image: np.ndarray
    ) -> str:
        """
        Main OCR/VLM inference function.
        Routes to Claude, OpenAI, or Ollama based on self.model.
        """

        image_bytes = self._image_to_bytes(image)

        prompt = (
            "Transcribe the image EXACTLY as written.\n\n"
            "Rules:\n"
            "- Preserve equations.\n"
            "- Preserve symbols.\n"
            "- Preserve MCQ options.\n"
            "- Preserve line breaks.\n"
            "- Preserve chemistry notation.\n"
            "- Preserve mathematical notation.\n"
            "- Do NOT summarize.\n"
            "- Do NOT solve the question.\n"
            "- Do NOT explain anything.\n"
            "Return only the transcription."
        )

        import base64 as _b64

        _ALIASES = {
            "haiku":         "claude-haiku-4-5-20251001",
            "claude-haiku":  "claude-haiku-4-5-20251001",
            "sonnet":        "claude-sonnet-4-6",
            "claude-sonnet": "claude-sonnet-4-6",
            "gpt-4o":        "gpt-4o",
            "gpt-4o-mini":   "gpt-4o-mini",
        }

        resolved = _ALIASES.get(self.model, self.model)
        image_b64 = _b64.b64encode(image_bytes).decode()

        if resolved.startswith("claude"):
            import time
            import random
            import anthropic
            client = anthropic.Anthropic()
            for attempt in range(7):
                try:
                    msg = client.messages.create(
                        model=resolved,
                        max_tokens=2048,
                        temperature=0,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                }},
                                {"type": "text", "text": prompt},
                            ],
                        }],
                    )
                    return msg.content[0].text.strip()
                except anthropic.RateLimitError:
                    if attempt == 6:
                        raise
                    time.sleep(5.0 * (2 ** attempt) + random.uniform(0, 2))

        if resolved.startswith("gpt") or resolved.startswith("o1") or resolved.startswith("o3"):
            from openai import OpenAI
            client = OpenAI()
            response = client.chat.completions.create(
                model=resolved,
                max_tokens=2048,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return response.choices[0].message.content.strip()

        # Ollama default
        import requests as _req
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 2048},
        }
        resp = _req.post("http://localhost:11434/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    # =====================================================
    # TEXT NORMALIZATION
    # =====================================================

    def _normalize_text(
        self,
        text: str
    ) -> str:
        """
        Normalize OCR/VLM output.
        """

        if not text:
            return ""

        # ---------------------------------------------
        # Unicode normalization
        # ---------------------------------------------
        replacements = {

            "−": "-",

            "–": "-",

            "—": "-",

            "ﬁ": "fi",

            "ﬂ": "fl",

            "×": "x",

            "÷": "/",

            "“": '"',

            "”": '"',

            "‘": "'",

            "’": "'",
        }

        for src, dst in replacements.items():

            text = text.replace(src, dst)

        # ---------------------------------------------
        # Remove excessive spaces
        # ---------------------------------------------
        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        # ---------------------------------------------
        # Normalize line endings
        # ---------------------------------------------
        lines = []

        for line in text.splitlines():

            cleaned = line.rstrip()

            if cleaned:
                lines.append(cleaned)

        text = "\n".join(lines)

        return text.strip()

    # =====================================================
    # CONFIDENCE ESTIMATION
    # =====================================================

    def _estimate_confidence(
        self,
        text: str
    ) -> float:
        """
        Lightweight OCR confidence estimation.
        """

        if not text:
            return 0.0

        # ---------------------------------------------
        # Extremely short outputs
        # ---------------------------------------------
        if len(text.strip()) < 5:
            return 0.20

        # ---------------------------------------------
        # Garbage symbol ratio
        # ---------------------------------------------
        weird_chars = len(
            re.findall(
                r"[�□◊]",
                text
            )
        )

        ratio = weird_chars / max(
            len(text),
            1
        )

        if ratio > 0.10:
            return 0.40

        # ---------------------------------------------
        # Healthy extraction
        # ---------------------------------------------
        return 0.90

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_transcription_summary(
        self,
        transcriptions
    ):

        print(
            "\n========== TRANSCRIPTIONS ==========\n"
        )

        for transcription in transcriptions:

            print(
                f"[{transcription.region_type.upper()}] "
                f"QID={transcription.qid} | "
                f"Confidence={transcription.confidence:.2f}"
            )

            print(
                transcription.normalized_text[:500]
            )

            print("-" * 80)
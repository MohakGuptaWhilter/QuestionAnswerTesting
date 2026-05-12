from dataclasses import dataclass
from typing import List
import uuid
import numpy as np
from PIL import Image
import io
import re


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
        crops
    ) -> List[Transcription]:

        transcriptions = []

        for crop in crops:

            try:

                # -------------------------------------
                # Run OCR/VLM
                # -------------------------------------
                raw_text = self._run_vlm(
                    crop.image
                )

                # -------------------------------------
                # Normalize text
                # -------------------------------------
                normalized = self._normalize_text(
                    raw_text
                )

                # -------------------------------------
                # Estimate confidence
                # -------------------------------------
                confidence = self._estimate_confidence(
                    normalized
                )

                # -------------------------------------
                # Build transcription object
                # -------------------------------------
                transcription = Transcription(

                    transcription_id=str(uuid.uuid4()),

                    crop_id=crop.crop_id,

                    region_type=crop.region_type,

                    qid=crop.qid,

                    raw_text=raw_text,

                    normalized_text=normalized,

                    confidence=confidence,

                    metadata={

                        "page_number":
                            crop.page_number,

                        "model":
                            self.model,

                        "region_type":
                            crop.region_type
                    }
                )

                transcriptions.append(
                    transcription
                )

            except Exception as e:

                print(
                    f"[VLMTranscriber] Failed "
                    f"{crop.crop_id}: {str(e)}"
                )

        return transcriptions

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

        Replace this implementation
        with your actual model call.
        """

        image_bytes = self._image_to_bytes(
            image
        )

        # ---------------------------------------------
        # OCR/VLM prompt
        # ---------------------------------------------
        prompt = """
Transcribe the image EXACTLY as written.

Rules:
- Preserve equations.
- Preserve symbols.
- Preserve MCQ options.
- Preserve line breaks.
- Preserve chemistry notation.
- Preserve mathematical notation.
- Do NOT summarize.
- Do NOT solve the question.
- Do NOT explain anything.
Return only the transcription.
"""

        # =================================================
        # PLACEHOLDER MODEL CALL
        # =================================================
        #
        # Replace with:
        # - Ollama
        # - Claude
        # - OpenAI
        # - Qwen
        # - MathPix
        #
        # Example:
        #
        # response = your_vlm_api(
        #     model=self.model,
        #     image=image_bytes,
        #     prompt=prompt
        # )
        #
        # return response
        #
        # =================================================

        simulated_response = (
            "[PLACEHOLDER OCR OUTPUT]"
        )

        return simulated_response

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
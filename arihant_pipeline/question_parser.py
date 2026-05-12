from dataclasses import dataclass
from typing import List, Dict, Optional
import re


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class ParsedQuestion:
    """
    Final structured academic question object.
    """

    qid: Optional[str]

    question_text: str

    options: Dict[str, str]

    answer: Optional[str]

    solution_text: Optional[str]

    question_type: str

    confidence: float

    metadata: dict


# =========================================================
# QUESTION PARSER
# =========================================================

class QuestionParser:
    """
    Converts OCR/VLM transcriptions into structured
    academic question objects.

    Responsibilities:
    - detect question types
    - extract MCQ options
    - separate solutions
    - normalize text structure
    - preserve equations/symbols

    IMPORTANT:
    This stage parses STRUCTURE.
    It does NOT:
    - OCR
    - classify layouts
    - detect regions
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

    # =====================================================
    # PUBLIC API
    # =====================================================

    def parse(
        self,
        transcriptions
    ) -> List[ParsedQuestion]:

        parsed_questions = []

        for transcription in transcriptions:

            try:

                parsed = self._parse_transcription(
                    transcription
                )

                parsed_questions.append(parsed)

            except Exception as e:

                print(
                    f"[QuestionParser] Failed "
                    f"{transcription.crop_id}: {str(e)}"
                )

        return parsed_questions

    # =====================================================
    # MAIN PARSER
    # =====================================================

    def _parse_transcription(
        self,
        transcription
    ) -> ParsedQuestion:

        text = transcription.normalized_text

        # ---------------------------------------------
        # Detect question type
        # ---------------------------------------------
        question_type = self._detect_question_type(
            text
        )

        # ---------------------------------------------
        # Extract solution
        # ---------------------------------------------
        question_text, solution_text = (
            self._split_solution(text)
        )

        # ---------------------------------------------
        # Extract options
        # ---------------------------------------------
        options = {}

        if question_type == "mcq":

            question_text, options = (
                self._extract_options(
                    question_text
                )
            )

        # ---------------------------------------------
        # Clean question text
        # ---------------------------------------------
        question_text = self._clean_question_text(
            question_text
        )

        # ---------------------------------------------
        # Estimate parser confidence
        # ---------------------------------------------
        confidence = self._estimate_confidence(
            question_text,
            options,
            question_type
        )

        # ---------------------------------------------
        # Build structured object
        # ---------------------------------------------
        return ParsedQuestion(

            qid=transcription.qid,

            question_text=question_text,

            options=options,

            answer=None,

            solution_text=solution_text,

            question_type=question_type,

            confidence=confidence,

            metadata={

                "crop_id":
                    transcription.crop_id,

                "region_type":
                    transcription.region_type,

                "ocr_confidence":
                    transcription.confidence
            }
        )

    # =====================================================
    # QUESTION TYPE DETECTION
    # =====================================================

    def _detect_question_type(
        self,
        text: str
    ) -> str:

        lower = text.lower()

        # ---------------------------------------------
        # Assertion-Reason
        # ---------------------------------------------
        if (
            "assertion" in lower
            and "reason" in lower
        ):
            return "assertion_reason"

        # ---------------------------------------------
        # Match the column
        # ---------------------------------------------
        if (
            "column i" in lower
            or "column ii" in lower
        ):
            return "match_the_column"

        # ---------------------------------------------
        # MCQ
        # ---------------------------------------------
        option_hits = sum(
            option in text
            for option in [
                "(A)",
                "(B)",
                "(C)",
                "(D)"
            ]
        )

        if option_hits >= 2:
            return "mcq"

        # ---------------------------------------------
        # Numerical
        # ---------------------------------------------
        return "numerical"

    # =====================================================
    # SOLUTION SPLITTING
    # =====================================================

    def _split_solution(
        self,
        text: str
    ):

        patterns = [
            r"\bsol\.?\b",
            r"\bsolution\b",
            r"\bans\.?\b",
            r"\banswer\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:

                idx = match.start()

                question = text[:idx].strip()

                solution = text[idx:].strip()

                return question, solution

        return text.strip(), None

    # =====================================================
    # OPTION EXTRACTION
    # =====================================================

    def _extract_options(
        self,
        text: str
    ):

        options = {}

        # ---------------------------------------------
        # Robust MCQ regex
        # ---------------------------------------------
        pattern = re.compile(

            r"\(?([A-D])\)?[\.\)]?\s*(.*?)"
            r"(?=\(?[A-D]\)?[\.\)]?\s*|$)",

            re.S
        )

        matches = pattern.findall(text)

        # ---------------------------------------------
        # Build option dictionary
        # ---------------------------------------------
        for label, value in matches:

            cleaned = value.strip()

            if cleaned:

                options[label] = cleaned

        # ---------------------------------------------
        # Remove options from question body
        # ---------------------------------------------
        if matches:

            first_match = pattern.search(text)

            question_text = text[
                :first_match.start()
            ].strip()

        else:

            question_text = text

        return question_text, options

    # =====================================================
    # QUESTION CLEANING
    # =====================================================

    def _clean_question_text(
        self,
        text: str
    ) -> str:

        # ---------------------------------------------
        # Remove question numbering
        # ---------------------------------------------
        patterns = [

            r"^Q\.?\s*\d+\s*[\.\)]?\s*",

            r"^\d+\.\s*",

            r"^\(\d+\)\s*",
        ]

        for pattern in patterns:

            text = re.sub(
                pattern,
                "",
                text,
                flags=re.I
            )

        # ---------------------------------------------
        # Normalize spaces
        # ---------------------------------------------
        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    # =====================================================
    # CONFIDENCE ESTIMATION
    # =====================================================

    def _estimate_confidence(
        self,
        question_text,
        options,
        question_type
    ) -> float:

        score = 1.0

        # ---------------------------------------------
        # Tiny question
        # ---------------------------------------------
        if len(question_text.split()) < 3:
            score -= 0.4

        # ---------------------------------------------
        # MCQ integrity
        # ---------------------------------------------
        if question_type == "mcq":

            if len(options) < 4:
                score -= 0.3

        # ---------------------------------------------
        # Empty extraction
        # ---------------------------------------------
        if not question_text:
            score = 0.0

        return max(score, 0.0)

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_question_summary(
        self,
        parsed_questions
    ):

        print(
            "\n========== PARSED QUESTIONS ==========\n"
        )

        for q in parsed_questions:

            print(
                f"[{q.question_type.upper()}] "
                f"QID={q.qid} | "
                f"Confidence={q.confidence:.2f}"
            )

            print("\nQUESTION:")
            print(q.question_text)

            if q.options:

                print("\nOPTIONS:")

                for k, v in q.options.items():

                    print(f"{k}: {v}")

            if q.solution_text:

                print("\nSOLUTION:")
                print(q.solution_text[:300])

            print("-" * 80)
from dataclasses import dataclass
from typing import List
import re
import numpy as np


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class ClassifiedBlock:
    """
    Semantic classification result for a layout block.
    """

    reading_index: int

    semantic_type: str

    confidence: float

    ordered_block: object


# =========================================================
# BLOCK CLASSIFIER
# =========================================================

class BlockClassifier:
    """
    Converts layout blocks into semantic document units.

    Responsibilities:
    - identify questions
    - identify solutions
    - identify answer keys
    - identify examples
    - identify theory
    - identify headings

    This stage transforms:
        visual layout -> semantic meaning
    """

    # -----------------------------------------------------
    # REGEX PATTERNS
    # -----------------------------------------------------

    QUESTION_PATTERNS = [
        r"^\d+\.",
        r"^Q\.?\s*\d+",
        r"^\(\d+\)",
    ]

    OPTION_PATTERNS = [
        r"\(A\)",
        r"\(B\)",
        r"\(C\)",
        r"\(D\)",
    ]

    SOLUTION_KEYWORDS = [
        "sol.",
        "solution",
        "ans.",
        "answer",
        "therefore",
        "hence",
    ]

    EXAMPLE_KEYWORDS = [
        "example",
        "illustration",
        "solved example",
    ]

    THEORY_KEYWORDS = [
        "definition",
        "concept",
        "theory",
        "introduction",
    ]

    # -----------------------------------------------------
    # INIT
    # -----------------------------------------------------

    def __init__(self, config):

        self.config = config

        self.heading_font_threshold = getattr(
            config,
            "heading_font_threshold",
            16
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def classify(
        self,
        ordered_blocks
    ) -> List[ClassifiedBlock]:

        classified = []

        for ordered in ordered_blocks:

            block = ordered.layout_block

            semantic_type, confidence = (
                self._classify_block(block)
            )

            classified.append(
                ClassifiedBlock(
                    reading_index=ordered.reading_index,
                    semantic_type=semantic_type,
                    confidence=confidence,
                    ordered_block=ordered
                )
            )

        return classified

    # =====================================================
    # MAIN CLASSIFICATION LOGIC
    # =====================================================

    def _classify_block(self, block):

        text = block.text.strip()

        text_lower = text.lower()

        # -------------------------------------------------
        # Empty / noise
        # -------------------------------------------------
        if not text:
            return "misc", 0.10

        # -------------------------------------------------
        # Heading
        # -------------------------------------------------
        if self._is_heading(block):
            return "heading", 0.98

        # -------------------------------------------------
        # Answer key
        # -------------------------------------------------
        if self._is_answer_key(text):
            return "answer_key", 0.99

        # -------------------------------------------------
        # Solution
        # -------------------------------------------------
        if self._is_solution(text_lower):
            return "solution", 0.95

        # -------------------------------------------------
        # Example
        # -------------------------------------------------
        if self._is_example(text_lower):
            return "example", 0.96

        # -------------------------------------------------
        # Question
        # -------------------------------------------------
        if self._is_question(text):
            return "question", 0.93

        # -------------------------------------------------
        # Theory
        # -------------------------------------------------
        if self._is_theory(text_lower):
            return "theory", 0.90

        # -------------------------------------------------
        # Formula-heavy
        # -------------------------------------------------
        if self._is_formula(text):
            return "formula", 0.85

        # -------------------------------------------------
        # Table-like
        # -------------------------------------------------
        if self._is_table(text):
            return "table", 0.80

        return "misc", 0.50

    # =====================================================
    # HEADING DETECTION
    # =====================================================

    def _is_heading(self, block):

        avg_font = self._average_font_size(block)

        text = block.text.strip()

        if avg_font >= self.heading_font_threshold:
            return True

        if len(text.split()) <= 8 and text.isupper():
            return True

        return False

    # =====================================================
    # QUESTION DETECTION
    # =====================================================

    def _is_question(self, text):

        text = text.strip()

        # ---------------------------------------------
        # Regex anchors
        # ---------------------------------------------
        for pattern in self.QUESTION_PATTERNS:

            if re.search(pattern, text):
                return True

        # ---------------------------------------------
        # MCQ option density
        # ---------------------------------------------
        option_hits = sum(
            bool(re.search(p, text))
            for p in self.OPTION_PATTERNS
        )

        if option_hits >= 2:
            return True

        # ---------------------------------------------
        # Imperative verbs
        # ---------------------------------------------
        imperative_words = [
            "find",
            "calculate",
            "determine",
            "prove",
            "evaluate",
        ]

        lower = text.lower()

        imperative_hits = sum(
            word in lower
            for word in imperative_words
        )

        if imperative_hits >= 1 and len(text.split()) < 120:
            return True

        return False

    # =====================================================
    # SOLUTION DETECTION
    # =====================================================

    def _is_solution(self, text):

        for keyword in self.SOLUTION_KEYWORDS:

            if keyword in text:
                return True

        return False

    # =====================================================
    # EXAMPLE DETECTION
    # =====================================================

    def _is_example(self, text):

        for keyword in self.EXAMPLE_KEYWORDS:

            if keyword in text:
                return True

        return False

    # =====================================================
    # THEORY DETECTION
    # =====================================================

    def _is_theory(self, text):

        word_count = len(text.split())

        keyword_hits = sum(
            keyword in text
            for keyword in self.THEORY_KEYWORDS
        )

        # Dense prose block
        if word_count > 80:
            return True

        # Theory-like keywords
        if keyword_hits >= 1:
            return True

        return False

    # =====================================================
    # ANSWER KEY DETECTION
    # =====================================================

    def _is_answer_key(self, text):

        patterns = [
            r"\d+\.\([A-D]\)",
            r"\d+\s*\([A-D]\)",
            r"\d+\.\s*[A-D]",
        ]

        total_hits = 0

        for pattern in patterns:

            total_hits += len(
                re.findall(pattern, text)
            )

        return total_hits >= 5

    # =====================================================
    # FORMULA DETECTION
    # =====================================================

    def _is_formula(self, text):

        symbols = [
            "=",
            "∑",
            "√",
            "∫",
            "^",
            "→",
            "±",
        ]

        symbol_hits = sum(
            s in text
            for s in symbols
        )

        return symbol_hits >= 2

    # =====================================================
    # TABLE DETECTION
    # =====================================================

    def _is_table(self, text):

        lines = text.split("\n")

        if len(lines) < 3:
            return False

        consistent_spacing = 0

        for line in lines:

            if len(re.findall(r"\s{3,}", line)) >= 2:
                consistent_spacing += 1

        return consistent_spacing >= 3

    # =====================================================
    # FONT STATISTICS
    # =====================================================

    def _average_font_size(self, block):

        font_sizes = []

        try:

            for line in block.lines:

                for span in line.spans:

                    if hasattr(span, "size"):
                        font_sizes.append(span.size)

        except Exception:
            return 10

        if not font_sizes:
            return 10

        return float(np.mean(font_sizes))

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_classification_summary(
        self,
        classified_blocks
    ):

        for block in classified_blocks:

            layout = block.ordered_block.layout_block

            print(
                f"[{block.reading_index}] "
                f"{block.semantic_type.upper()} "
                f"({block.confidence:.2f}) | "
                f"{layout.text[:100]}"
            )
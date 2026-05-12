from dataclasses import dataclass
from typing import List, Optional
import re
import uuid


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class Anchor:
    """
    Represents a semantic region starting point.

    Examples:
    - Question start
    - Solution start
    - Example start
    - Answer key start
    """

    anchor_id: str

    anchor_type: str

    qid: Optional[str]

    page_number: int

    bbox: tuple

    reading_index: int

    text: str

    confidence: float

    source_block: object


# =========================================================
# QUESTION ANCHOR DETECTOR
# =========================================================

class QuestionAnchorDetector:
    """
    Detects semantic anchors in classified document blocks.

    Responsibilities:
    - detect question starts
    - detect solution starts
    - detect example starts
    - detect answer-key starts
    - extract semantic IDs

    IMPORTANT:
    Anchors are NOT full semantic regions.

    They are:
        semantic entry points
    """

    # -----------------------------------------------------
    # QUESTION PATTERNS
    # -----------------------------------------------------

    QUESTION_PATTERNS = [
        r"^Q\.?\s*(\d+)",
        r"^(\d+)\.",
        r"^\((\d+)\)",
    ]

    # -----------------------------------------------------
    # SOLUTION PATTERNS
    # -----------------------------------------------------

    SOLUTION_PATTERNS = [
        r"sol\.?\s*(\d+)",
        r"solution\s*(\d+)",
        r"ans\.?\s*(\d+)",
        r"answer\s*(\d+)",
    ]

    # -----------------------------------------------------
    # EXAMPLE PATTERNS
    # -----------------------------------------------------

    EXAMPLE_PATTERNS = [
        r"example\s*(\d+)",
        r"illustration\s*(\d+)",
        r"solved\s+example\s*(\d+)",
    ]

    # -----------------------------------------------------
    # ANSWER KEY PATTERNS
    # -----------------------------------------------------

    ANSWER_KEY_PATTERNS = [
        r"\d+\.\([A-D]\)",
        r"\d+\s*\([A-D]\)",
        r"\d+\.\s*[A-D]",
    ]

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

    # =====================================================
    # PUBLIC API
    # =====================================================

    def detect(
        self,
        classified_blocks
    ) -> List[Anchor]:

        anchors = []

        for classified in classified_blocks:

            semantic_type = classified.semantic_type

            layout_block = (
                classified
                .ordered_block
                .layout_block
            )

            text = layout_block.text.strip()

            # ---------------------------------------------
            # QUESTION ANCHORS
            # ---------------------------------------------
            if semantic_type == "question":

                qid = self._extract_question_id(
                    text
                )

                anchors.append(
                    self._build_anchor(
                        classified_block=classified,
                        anchor_type="question",
                        qid=qid,
                        confidence=0.95
                    )
                )

            # ---------------------------------------------
            # SOLUTION ANCHORS
            # ---------------------------------------------
            elif semantic_type == "solution":

                qid = self._extract_solution_id(
                    text
                )

                anchors.append(
                    self._build_anchor(
                        classified_block=classified,
                        anchor_type="solution",
                        qid=qid,
                        confidence=0.93
                    )
                )

            # ---------------------------------------------
            # EXAMPLE ANCHORS
            # ---------------------------------------------
            elif semantic_type == "example":

                qid = self._extract_example_id(
                    text
                )

                anchors.append(
                    self._build_anchor(
                        classified_block=classified,
                        anchor_type="example",
                        qid=qid,
                        confidence=0.94
                    )
                )

            # ---------------------------------------------
            # ANSWER KEY ANCHORS
            # ---------------------------------------------
            elif semantic_type == "answer_key":

                anchors.append(
                    self._build_anchor(
                        classified_block=classified,
                        anchor_type="answer_key",
                        qid=None,
                        confidence=0.99
                    )
                )

        return anchors

    # =====================================================
    # BUILD ANCHOR
    # =====================================================

    def _build_anchor(
        self,
        classified_block,
        anchor_type: str,
        qid: Optional[str],
        confidence: float
    ) -> Anchor:

        ordered = classified_block.ordered_block

        layout = ordered.layout_block

        return Anchor(
            anchor_id=str(uuid.uuid4()),

            anchor_type=anchor_type,

            qid=qid,

            page_number=layout.page_number,

            bbox=layout.bbox,

            reading_index=classified_block.reading_index,

            text=layout.text[:300],

            confidence=confidence,

            source_block=classified_block
        )

    # =====================================================
    # QUESTION ID EXTRACTION
    # =====================================================

    def _extract_question_id(
        self,
        text: str
    ) -> Optional[str]:

        text = text.strip()

        for pattern in self.QUESTION_PATTERNS:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:
                return match.group(1)

        return None

    # =====================================================
    # SOLUTION ID EXTRACTION
    # =====================================================

    def _extract_solution_id(
        self,
        text: str
    ) -> Optional[str]:

        text = text.strip().lower()

        for pattern in self.SOLUTION_PATTERNS:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:
                return match.group(1)

        # Fallback:
        # solution may contain "12."
        fallback = re.search(
            r"^(\d+)\.",
            text
        )

        if fallback:
            return fallback.group(1)

        return None

    # =====================================================
    # EXAMPLE ID EXTRACTION
    # =====================================================

    def _extract_example_id(
        self,
        text: str
    ) -> Optional[str]:

        text = text.strip()

        for pattern in self.EXAMPLE_PATTERNS:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:
                return match.group(1)

        return None

    # =====================================================
    # ANSWER KEY DETECTION
    # =====================================================

    def _looks_like_answer_key(
        self,
        text: str
    ) -> bool:

        total_hits = 0

        for pattern in self.ANSWER_KEY_PATTERNS:

            total_hits += len(
                re.findall(
                    pattern,
                    text
                )
            )

        return total_hits >= 5

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_anchor_summary(
        self,
        anchors: List[Anchor]
    ):

        print("\n========== ANCHORS ==========\n")

        for anchor in anchors:

            print(
                f"[{anchor.anchor_type.upper()}] "
                f"QID={anchor.qid} | "
                f"Page={anchor.page_number} | "
                f"Idx={anchor.reading_index} | "
                f"{anchor.text[:120]}"
            )
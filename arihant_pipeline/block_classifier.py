from dataclasses import dataclass
from typing import Dict, List, Tuple
import re
import numpy as np


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class ClassifiedBlock:
    """Semantic classification result for a layout block."""

    reading_index: int
    semantic_type: str
    confidence: float
    ordered_block: object


# =========================================================
# BLOCK CLASSIFIER
# =========================================================

class BlockClassifier:
    """
    Two-pass classifier.

    Pass 1 — Page classification (page-level rules, deterministic):
        • "example"  — page contains at least one "Example <N>." anywhere
        • "question" — page has numbered items (1. …) AND ≥2 MCQ option markers
        • "theory"   — everything else

    Pass 2 — Block classification (constrained by page type):
        • theory pages  → all blocks tagged "theory" (except headings)
        • example pages → look for example / formula / heading / misc
        • question pages → look for question / answer_key / formula / heading / misc
    """

    # ── MCQ option markers ────────────────────────────────────────────────────
    OPTION_PATTERNS = [r"\(A\)", r"\(B\)", r"\(C\)", r"\(D\)"]

    # ── Solution start ────────────────────────────────────────────────────────
    SOLUTION_START_RE = re.compile(r"^(sol\.|ans\.)\s*", re.IGNORECASE)

    # ── Answer-key entry (compact grid: "1.(A)  2.(C)  3.(B)") ───────────────
    ANSWER_KEY_PATTERNS = [
        r"\d+\.\([A-D]\)",
        r"\d+\s*\([A-D]\)",
        r"\d+\.\s*[A-D]",
    ]

    # ── Heading font threshold ────────────────────────────────────────────────
    DEFAULT_HEADING_FONT = 16

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self, config):
        self.config = config
        self.heading_font_threshold = getattr(
            config, "heading_font_threshold", self.DEFAULT_HEADING_FONT
        )

    # =========================================================
    # PUBLIC API
    # =========================================================

    def classify(self, ordered_blocks) -> List[ClassifiedBlock]:
        page_types = self._classify_pages(ordered_blocks)

        classified = []
        for ordered in ordered_blocks:
            block = ordered.layout_block
            page_type = page_types.get(block.page_number, "theory")
            semantic_type, confidence = self._classify_block(block, page_type)
            classified.append(
                ClassifiedBlock(
                    reading_index=ordered.reading_index,
                    semantic_type=semantic_type,
                    confidence=confidence,
                    ordered_block=ordered,
                )
            )

        self._log_page_summary(page_types)
        return classified

    # =========================================================
    # PASS 1 — PAGE CLASSIFICATION
    # =========================================================

    def _classify_pages(self, ordered_blocks) -> Dict[int, str]:
        """
        Determine the type of every page that appears in ordered_blocks.

        Rules (applied in priority order):
          1. example  — ≥1 "Example <N>."  anywhere on the page
          2. question — ≥1 numbered item (^\d+\.) AND ≥2 MCQ option markers
          3. theory   — everything else
        """
        # Collect all text per page
        page_texts: Dict[int, List[str]] = {}
        for ordered in ordered_blocks:
            pn = ordered.layout_block.page_number
            page_texts.setdefault(pn, []).append(ordered.layout_block.text)

        page_types: Dict[int, str] = {}
        for page_num, texts in page_texts.items():
            full_text = "\n".join(texts)
            if self._page_is_example(full_text):
                page_types[page_num] = "example"
            elif self._page_is_question(full_text):
                page_types[page_num] = "question"
            else:
                page_types[page_num] = "theory"

        return page_types

    def _page_is_example(self, text: str) -> bool:
        """True if 'Example <number>.' appears ANYWHERE on the page."""
        return bool(re.search(r"example\s+\d+\.", text, re.IGNORECASE))

    def _page_is_question(self, text: str) -> bool:
        """
        True if the page looks like a questions page:
          - at least one numbered item starting a line  (1. …)
          - at least two distinct MCQ option markers    (A) (B) (C) (D)
        """
        has_numbered = bool(re.search(r"^\d+\.\s", text, re.MULTILINE))
        option_hits = sum(
            bool(re.search(p, text)) for p in self.OPTION_PATTERNS
        )
        return has_numbered and option_hits >= 2

    # =========================================================
    # PASS 2 — BLOCK CLASSIFICATION (page-type constrained)
    # =========================================================

    def _classify_block(self, block, page_type: str) -> Tuple[str, float]:
        """Classify one block given the page it belongs to."""
        text = block.text.strip()

        if not text:
            return "misc", 0.10

        # Headings are always headings regardless of page type
        if self._is_heading(block):
            return "heading", 0.98

        if page_type == "theory":
            return "theory", 0.92

        if page_type == "example":
            return self._classify_example_page_block(text)

        # page_type == "question"
        return self._classify_question_page_block(text)

    def _classify_example_page_block(self, text: str) -> Tuple[str, float]:
        if re.search(r"example\s+\d+\.", text, re.IGNORECASE):
            return "example", 0.97
        if self._is_solution(text):
            return "solution", 0.93
        if self._is_formula(text):
            return "formula", 0.85
        return "misc", 0.55

    def _classify_question_page_block(self, text: str) -> Tuple[str, float]:
        if self._is_answer_key(text):
            return "answer_key", 0.99
        if self._is_solution(text):
            return "solution", 0.93
        if self._is_question(text):
            return "question", 0.94
        if self._is_formula(text):
            return "formula", 0.85
        return "misc", 0.55

    # =========================================================
    # BLOCK-LEVEL DETECTORS
    # =========================================================

    def _is_heading(self, block) -> bool:
        text = block.text.strip()
        if self._average_font_size(block) >= self.heading_font_threshold:
            return True
        if len(text.split()) <= 8 and text.isupper():
            return True
        return False

    def _is_question(self, text: str) -> bool:
        if re.search(r"^\d+\.\s", text):
            return True
        if re.search(r"^Q\.?\s*\d+", text):
            return True
        if re.search(r"^\(\d+\)", text):
            return True
        option_hits = sum(bool(re.search(p, text)) for p in self.OPTION_PATTERNS)
        return option_hits >= 2

    def _is_solution(self, text: str) -> bool:
        if "....." in text or "…" in text:
            return False
        return bool(self.SOLUTION_START_RE.match(text))

    def _is_answer_key(self, text: str) -> bool:
        total = sum(
            len(re.findall(p, text)) for p in self.ANSWER_KEY_PATTERNS
        )
        return total >= 5

    def _is_formula(self, text: str) -> bool:
        symbols = ["=", "∑", "√", "∫", "^", "→", "±"]
        return sum(s in text for s in symbols) >= 2

    # =========================================================
    # FONT STATISTICS
    # =========================================================

    def _average_font_size(self, block) -> float:
        sizes = []
        try:
            for line in block.lines:
                for span in line.spans:
                    if hasattr(span, "size"):
                        sizes.append(span.size)
        except Exception:
            return 10.0
        return float(np.mean(sizes)) if sizes else 10.0

    # =========================================================
    # DEBUG
    # =========================================================

    def _log_page_summary(self, page_types: Dict[int, str]) -> None:
        counts: Dict[str, int] = {}
        for pt in page_types.values():
            counts[pt] = counts.get(pt, 0) + 1
        parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        print(f"[BlockClassifier] Pages: {parts}")

    def print_classification_summary(self, classified_blocks) -> None:
        for block in classified_blocks:
            layout = block.ordered_block.layout_block
            print(
                f"[{block.reading_index}] "
                f"{block.semantic_type.upper()} "
                f"({block.confidence:.2f}) | "
                f"{layout.text[:100]}"
            )

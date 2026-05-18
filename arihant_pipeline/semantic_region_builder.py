from dataclasses import dataclass
from typing import List, Optional
import uuid
import re


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class SemanticRegion:
    """
    Represents a semantically complete region.

    IMPORTANT:
    Region is fundamentally represented by BLOCKS,
    not only by bbox.
    """

    region_id: str

    region_type: str

    qid: Optional[str]

    page_start: int

    page_end: int

    blocks: list

    bbox: tuple

    text: str

    confidence: float


# =========================================================
# IMPROVED SEMANTIC REGION BUILDER
# =========================================================

class SemanticRegionBuilder:
    """
    Production-grade semantic region builder.

    Major improvements:
    - semantic continuation scoring
    - proper solution termination
    - topic drift detection
    - hard stop patterns
    - cleaner bbox generation
    - no aggressive misc absorption

    THIS STAGE DETERMINES:
    - crop correctness
    - OCR correctness
    - solution extraction quality
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        # ---------------------------------------------
        # Spatial controls
        # ---------------------------------------------
        self.max_vertical_gap = getattr(
            config,
            "max_vertical_gap",
            60
        )

        # ---------------------------------------------
        # Continuation threshold
        # ---------------------------------------------
        self.continuation_threshold = getattr(
            config,
            "continuation_threshold",
            0.45
        )

        # ---------------------------------------------
        # Safety limits
        # ---------------------------------------------
        self.max_region_blocks = getattr(
            config,
            "max_region_blocks",
            30
        )

        # ---------------------------------------------
        # Compatible semantic types
        # ---------------------------------------------
        # IMPORTANT:
        # Removed dangerous "misc"
        # ---------------------------------------------
        self.region_compatibility = {

            "question": {
                "question",
                "formula",
                "table",
            },

            "solution": {
                "solution",
                "formula",
                "table",
            },

            "example": {
                "example",
                "formula",
                "table",
            },

            "answer_key": {
                "answer_key",
            },
        }

    # =====================================================
    # PUBLIC API
    # =====================================================

    def build(
        self,
        anchors,
        classified_blocks
    ) -> List[SemanticRegion]:

        semantic_regions = []

        # ---------------------------------------------
        # Reading-order lookup
        # ---------------------------------------------
        block_map = self._build_block_map(
            classified_blocks
        )

        # ---------------------------------------------
        # Sort anchors
        # ---------------------------------------------
        anchors = sorted(
            anchors,
            key=lambda a: a.reading_index
        )

        # ---------------------------------------------
        # Grow region per anchor
        # ---------------------------------------------
        for idx, anchor in enumerate(anchors):

            next_anchor = None

            if idx < len(anchors) - 1:
                next_anchor = anchors[idx + 1]

            region = self._grow_region(

                anchor=anchor,

                next_anchor=next_anchor,

                block_map=block_map
            )

            semantic_regions.append(region)

        return semantic_regions

    # =====================================================
    # BUILD BLOCK MAP
    # =====================================================

    def _build_block_map(
        self,
        classified_blocks
    ):

        block_map = {}

        for block in classified_blocks:

            block_map[
                block.reading_index
            ] = block

        return block_map

    # =====================================================
    # REGION GROWTH
    # =====================================================

    def _grow_region(
        self,
        anchor,
        next_anchor,
        block_map
    ) -> SemanticRegion:

        region_blocks = []

        anchor_type = anchor.anchor_type

        current_idx = anchor.reading_index

        end_limit = (
            next_anchor.reading_index
            if next_anchor
            else max(block_map.keys()) + 1
        )

        # ---------------------------------------------
        # Grow semantically
        # ---------------------------------------------
        while current_idx < end_limit:

            if current_idx not in block_map:

                current_idx += 1
                continue

            candidate = block_map[current_idx]

            layout_block = (
                candidate
                .ordered_block
                .layout_block
            )

            # -----------------------------------------
            # HARD TERMINATION
            # -----------------------------------------
            if self._is_hard_stop(
                candidate,
                anchor_type
            ):
                break

            # -----------------------------------------
            # Safety limit
            # -----------------------------------------
            if len(region_blocks) >= self.max_region_blocks:
                break

            # -----------------------------------------
            # First block always accepted
            # -----------------------------------------
            if not region_blocks:

                region_blocks.append(candidate)

                current_idx += 1
                continue

            # -----------------------------------------
            # Continuation score
            # -----------------------------------------
            score = self._continuation_score(

                region_blocks=region_blocks,

                candidate_block=candidate,

                anchor_type=anchor_type
            )

            # -----------------------------------------
            # Stop if semantic continuity weak
            # -----------------------------------------
            if score < self.continuation_threshold:
                break

            region_blocks.append(candidate)

            current_idx += 1

        return self._build_region(
            anchor,
            region_blocks
        )

    # =====================================================
    # HARD TERMINATION
    # =====================================================

    def _is_hard_stop(
        self,
        candidate,
        anchor_type
    ) -> bool:

        text = (
            candidate
            .ordered_block
            .layout_block
            .text
            .strip()
        )

        # ---------------------------------------------
        # New question pattern
        # ---------------------------------------------
        if re.match(
            r"^(Q\.?\s*\d+|\d+\.)",
            text,
            re.I
        ):
            return True

        # ---------------------------------------------
        # New solution pattern
        # ---------------------------------------------
        if (
            anchor_type != "solution"
            and re.match(
                r"^(Sol\.?|Solution)",
                text,
                re.I
            )
        ):
            return True

        # ---------------------------------------------
        # MCQ restart
        # ---------------------------------------------
        if re.search(
            r"\(A\).+\(B\)",
            text,
            re.S
        ):
            return True

        return False

    # =====================================================
    # CONTINUATION SCORING
    # =====================================================

    def _continuation_score(
        self,
        region_blocks,
        candidate_block,
        anchor_type
    ) -> float:

        score = 0.0

        candidate_layout = (
            candidate_block
            .ordered_block
            .layout_block
        )

        candidate_type = (
            candidate_block.semantic_type
        )

        # =================================================
        # 1. Semantic compatibility
        # =================================================

        compatible = (
            candidate_type
            in self.region_compatibility.get(
                anchor_type,
                set()
            )
        )

        if compatible:
            score += 0.30

        # =================================================
        # 2. Spatial continuity
        # =================================================

        prev_layout = (
            region_blocks[-1]
            .ordered_block
            .layout_block
        )

        spatial_score = self._spatial_score(
            prev_layout,
            candidate_layout
        )

        score += spatial_score * 0.25

        # =================================================
        # 3. Semantic similarity
        # =================================================

        semantic_score = self._semantic_similarity(
            region_blocks,
            candidate_layout.text
        )

        score += semantic_score * 0.30

        # =================================================
        # 4. Solution continuity signals
        # =================================================

        if anchor_type == "solution":

            continuation_words = [

                "therefore",

                "hence",

                "thus",

                "given",

                "substituting",

                "we get",

                "from equation",

                "solving",
            ]

            lower = candidate_layout.text.lower()

            hits = sum(
                word in lower
                for word in continuation_words
            )

            if hits > 0:
                score += 0.15

        return min(score, 1.0)

    # =====================================================
    # SPATIAL SCORE
    # =====================================================

    def _spatial_score(
        self,
        prev_block,
        current_block
    ) -> float:

        # ---------------------------------------------
        # Cross-page continuation
        # ---------------------------------------------
        if (
            current_block.page_number
            == prev_block.page_number + 1
        ):
            return 0.8

        # ---------------------------------------------
        # Large page jump
        # ---------------------------------------------
        if (
            current_block.page_number
            != prev_block.page_number
        ):
            return 0.0

        # ---------------------------------------------
        # Vertical gap
        # ---------------------------------------------
        gap = (
            current_block.bbox[1]
            - prev_block.bbox[3]
        )

        if gap < 0:
            return 0.0

        if gap <= self.max_vertical_gap:
            return 1.0

        if gap <= self.max_vertical_gap * 2:
            return 0.5

        return 0.0

    # =====================================================
    # SEMANTIC SIMILARITY
    # =====================================================

    def _semantic_similarity(
        self,
        region_blocks,
        candidate_text
    ) -> float:

        existing_text = " ".join(

            b.ordered_block.layout_block.text

            for b in region_blocks[-5:]
        )

        words1 = set(
            re.findall(
                r"\w+",
                existing_text.lower()
            )
        )

        words2 = set(
            re.findall(
                r"\w+",
                candidate_text.lower()
            )
        )

        if not words1 or not words2:
            return 0.0

        overlap = len(
            words1.intersection(words2)
        )

        union = len(
            words1.union(words2)
        )

        return overlap / union

    # =====================================================
    # BUILD REGION
    # =====================================================

    def _build_region(
        self,
        anchor,
        classified_blocks
    ) -> SemanticRegion:

        if not classified_blocks:

            return SemanticRegion(

                region_id=str(uuid.uuid4()),

                region_type=anchor.anchor_type,

                qid=anchor.qid,

                page_start=anchor.page_number,

                page_end=anchor.page_number,

                blocks=[],

                bbox=(0, 0, 0, 0),

                text="",

                confidence=0.0
            )

        # ---------------------------------------------
        # Layout blocks
        # ---------------------------------------------
        layout_blocks = [

            cb.ordered_block.layout_block

            for cb in classified_blocks
        ]

        # ---------------------------------------------
        # IMPORTANT:
        # Merge ONLY same-page blocks for bbox
        # ---------------------------------------------
        first_page = min(
            b.page_number
            for b in layout_blocks
        )

        first_page_blocks = [

            b for b in layout_blocks

            if b.page_number == first_page
        ]

        bbox = self._merge_bboxes(

            [b.bbox for b in first_page_blocks]
        )

        # ---------------------------------------------
        # Combined text
        # ---------------------------------------------
        text = "\n".join(

            b.text

            for b in layout_blocks
        )

        # ---------------------------------------------
        # Confidence
        # ---------------------------------------------
        confidence = sum(

            cb.confidence

            for cb in classified_blocks

        ) / len(classified_blocks)

        return SemanticRegion(

            region_id=str(uuid.uuid4()),

            region_type=anchor.anchor_type,

            qid=anchor.qid,

            page_start=min(
                b.page_number
                for b in layout_blocks
            ),

            page_end=max(
                b.page_number
                for b in layout_blocks
            ),

            blocks=classified_blocks,

            bbox=bbox,

            text=text,

            confidence=confidence
        )

    # =====================================================
    # MERGE BBOXES
    # =====================================================

    def _merge_bboxes(
        self,
        bboxes
    ):

        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)

        return (
            x0,
            y0,
            x1,
            y1
        )

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_region_summary(
        self,
        semantic_regions
    ):

        print(
            "\n========== SEMANTIC REGIONS ==========\n"
        )

        for region in semantic_regions:

            print(
                f"[{region.region_type.upper()}] "
                f"QID={region.qid} | "
                f"Pages={region.page_start}-{region.page_end} | "
                f"Blocks={len(region.blocks)} | "
                f"Confidence={region.confidence:.2f}"
            )

            print(region.text[:500])

            print("-" * 80)
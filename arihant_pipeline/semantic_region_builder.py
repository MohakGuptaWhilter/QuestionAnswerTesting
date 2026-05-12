from dataclasses import dataclass
from typing import List, Optional
import uuid


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class SemanticRegion:
    """
    Represents a complete semantic object.

    Examples:
    - Full question
    - Full solution
    - Full solved example
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
# SEMANTIC REGION BUILDER
# =========================================================

class SemanticRegionBuilder:
    """
    Builds complete semantic regions from anchors.

    Responsibilities:
    - grow question regions
    - grow solution regions
    - attach equations/options
    - attach continuation blocks
    - stop at semantic boundaries

    THIS IS THE MOST IMPORTANT STAGE
    for correct cropping.
    """

    # -----------------------------------------------------
    # Semantic compatibility map
    # -----------------------------------------------------

    REGION_COMPATIBILITY = {
        "question": {
            "question",
            "formula",
            "table",
            "misc",
        },

        "solution": {
            "solution",
            "formula",
            "table",
            "misc",
        },

        "example": {
            "example",
            "formula",
            "table",
            "misc",
        },

        "answer_key": {
            "answer_key",
        },
    }

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.max_vertical_gap = getattr(
            config,
            "max_vertical_gap",
            120
        )

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
        # Create fast lookup by reading index
        # ---------------------------------------------
        block_map = self._build_block_map(
            classified_blocks
        )

        # ---------------------------------------------
        # Sort anchors by reading order
        # ---------------------------------------------
        anchors = sorted(
            anchors,
            key=lambda a: a.reading_index
        )

        # ---------------------------------------------
        # Build semantic region per anchor
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
    # BLOCK MAP
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

        start_idx = anchor.reading_index

        end_limit = (
            next_anchor.reading_index
            if next_anchor
            else max(block_map.keys()) + 1
        )

        current_idx = start_idx

        # ---------------------------------------------
        # Grow forward
        # ---------------------------------------------
        while current_idx < end_limit:

            if current_idx not in block_map:
                current_idx += 1
                continue

            classified = block_map[current_idx]

            semantic_type = classified.semantic_type

            layout_block = (
                classified
                .ordered_block
                .layout_block
            )

            # -----------------------------------------
            # Stop if incompatible semantic type
            # -----------------------------------------
            if not self._is_compatible(
                anchor_type,
                semantic_type
            ):
                break

            # -----------------------------------------
            # Stop if spatial continuity broken
            # -----------------------------------------
            if region_blocks:

                prev_block = (
                    region_blocks[-1]
                    .ordered_block
                    .layout_block
                )

                if not self._has_spatial_continuity(
                    prev_block,
                    layout_block
                ):
                    break

            region_blocks.append(classified)

            current_idx += 1

        # ---------------------------------------------
        # Build final semantic region
        # ---------------------------------------------
        return self._build_region(
            anchor,
            region_blocks
        )

    # =====================================================
    # COMPATIBILITY CHECK
    # =====================================================

    def _is_compatible(
        self,
        region_type,
        semantic_type
    ) -> bool:

        allowed = self.REGION_COMPATIBILITY.get(
            region_type,
            set()
        )

        return semantic_type in allowed

    # =====================================================
    # SPATIAL CONTINUITY
    # =====================================================

    def _has_spatial_continuity(
        self,
        block1,
        block2
    ) -> bool:

        # ---------------------------------------------
        # Same page
        # ---------------------------------------------
        if block1.page_number == block2.page_number:

            vertical_gap = (
                block2.bbox[1]
                - block1.bbox[3]
            )

            return vertical_gap < self.max_vertical_gap

        # ---------------------------------------------
        # Cross-page continuation
        # ---------------------------------------------
        if block2.page_number == block1.page_number + 1:

            # Allow continuation
            return True

        return False

    # =====================================================
    # BUILD REGION OBJECT
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
                confidence=0.0,
            )

        # ---------------------------------------------
        # Aggregate blocks
        # ---------------------------------------------
        layout_blocks = [
            cb.ordered_block.layout_block
            for cb in classified_blocks
        ]

        # ---------------------------------------------
        # Bounding box
        # ---------------------------------------------
        bbox = self._merge_bboxes(
            [b.bbox for b in layout_blocks]
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

        print("\n========== SEMANTIC REGIONS ==========\n")

        for region in semantic_regions:

            print(
                f"[{region.region_type.upper()}] "
                f"QID={region.qid} | "
                f"Pages={region.page_start}-{region.page_end} | "
                f"Blocks={len(region.blocks)} | "
                f"Confidence={region.confidence:.2f}"
            )

            print(region.text[:300])

            print("-" * 80)
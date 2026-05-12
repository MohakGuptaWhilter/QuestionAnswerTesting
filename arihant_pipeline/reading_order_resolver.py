from dataclasses import dataclass
from typing import List, Dict
import numpy as np


@dataclass
class OrderedLayoutBlock:
    """
    Represents a layout block with resolved reading order.
    """

    reading_index: int

    layout_block: object

    previous_block_id: str = None

    next_block_id: str = None


class ReadingOrderResolver:
    """
    Resolves human-readable reading order for layout blocks.

    Responsibilities:
    - group blocks page-wise
    - detect columns
    - sort blocks correctly
    - preserve reading sequence
    - attach adjacency relationships

    This stage is CRITICAL because PDFs do not guarantee
    correct extraction order.
    """

    def __init__(self, config):

        self.config = config

        # Maximum allowed x-distance for blocks
        # to belong to same column.
        self.column_threshold = getattr(
            config,
            "column_threshold",
            120
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def resolve(
        self,
        layout_blocks: List[object]
    ) -> List[OrderedLayoutBlock]:

        ordered_result = []

        reading_counter = 0

        # -----------------------------------------
        # Group page-wise
        # -----------------------------------------
        pages = self._group_by_page(
            layout_blocks
        )

        # -----------------------------------------
        # Resolve reading order page-by-page
        # -----------------------------------------
        for page_number in sorted(pages.keys()):

            page_blocks = pages[page_number]

            if not page_blocks:
                continue

            # -------------------------------------
            # Detect columns
            # -------------------------------------
            columns = self._detect_columns(
                page_blocks
            )

            # -------------------------------------
            # Resolve reading order
            # -------------------------------------
            ordered_page_blocks = self._resolve_page_order(
                columns
            )

            # -------------------------------------
            # Convert into ordered objects
            # -------------------------------------
            for block in ordered_page_blocks:

                ordered_result.append(
                    OrderedLayoutBlock(
                        reading_index=reading_counter,
                        layout_block=block
                    )
                )

                reading_counter += 1

        # -----------------------------------------
        # Build adjacency relationships
        # -----------------------------------------
        self._attach_neighbors(
            ordered_result
        )

        return ordered_result

    # =====================================================
    # PAGE GROUPING
    # =====================================================

    def _group_by_page(
        self,
        blocks: List[object]
    ) -> Dict[int, List[object]]:

        pages = {}

        for block in blocks:

            page_number = block.page_number

            if page_number not in pages:
                pages[page_number] = []

            pages[page_number].append(block)

        return pages

    # =====================================================
    # COLUMN DETECTION
    # =====================================================

    def _detect_columns(
        self,
        blocks: List[object]
    ) -> List[List[object]]:
        """
        Cluster blocks into visual columns.

        Uses x-coordinate grouping.
        """

        if not blocks:
            return []

        # -----------------------------------------
        # Sort left-to-right
        # -----------------------------------------
        blocks = sorted(
            blocks,
            key=lambda b: b.bbox[0]
        )

        columns = []

        for block in blocks:

            placed = False

            block_x = block.bbox[0]

            # -------------------------------------
            # Try inserting into existing column
            # -------------------------------------
            for column in columns:

                avg_x = np.mean([
                    b.bbox[0]
                    for b in column
                ])

                if abs(block_x - avg_x) < self.column_threshold:

                    column.append(block)

                    placed = True

                    break

            # -------------------------------------
            # Create new column
            # -------------------------------------
            if not placed:
                columns.append([block])

        return columns

    # =====================================================
    # PAGE ORDER RESOLUTION
    # =====================================================

    def _resolve_page_order(
        self,
        columns: List[List[object]]
    ) -> List[object]:
        """
        Resolve final human reading order.

        Reading order:
        left column -> right column
        top -> bottom inside each column
        """

        ordered = []

        # -----------------------------------------
        # Sort columns left -> right
        # -----------------------------------------
        columns.sort(
            key=lambda c: min(
                b.bbox[0]
                for b in c
            )
        )

        # -----------------------------------------
        # Sort blocks inside columns
        # -----------------------------------------
        for column in columns:

            column.sort(
                key=lambda b: b.bbox[1]
            )

            ordered.extend(column)

        return ordered

    # =====================================================
    # ADJACENCY ATTACHMENT
    # =====================================================

    def _attach_neighbors(
        self,
        ordered_blocks: List[OrderedLayoutBlock]
    ):
        """
        Attach previous and next block references.

        Extremely useful later for:
        - semantic region growth
        - question continuation
        - figure linking
        """

        for idx, ordered in enumerate(ordered_blocks):

            # Previous block
            if idx > 0:
                ordered.previous_block_id = (
                    ordered_blocks[idx - 1]
                    .layout_block
                    .block_id
                )

            # Next block
            if idx < len(ordered_blocks) - 1:
                ordered.next_block_id = (
                    ordered_blocks[idx + 1]
                    .layout_block
                    .block_id
                )

    # =====================================================
    # DEBUG HELPERS
    # =====================================================

    def print_reading_order(
        self,
        ordered_blocks: List[OrderedLayoutBlock]
    ):
        """
        Debug utility.
        """

        for ordered in ordered_blocks:

            block = ordered.layout_block

            print(
                f"[{ordered.reading_index}] "
                f"Page {block.page_number} | "
                f"{block.block_type} | "
                f"{block.text[:80]}"
            )
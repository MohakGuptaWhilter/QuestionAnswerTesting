from dataclasses import dataclass
from typing import List, Optional
import uuid


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class FigureBlock:
    """
    Represents a detected visual figure region.

    Examples:
    - diagram
    - graph
    - table
    - image
    """

    figure_id: str

    page_number: int

    bbox: tuple

    figure_type: str

    caption: str

    source_block: object


# =========================================================
# FIGURE LINKER
# =========================================================

class FigureLinker:
    """
    Links figures/diagrams/tables to semantic regions.

    Responsibilities:
    - detect figures
    - associate figures with questions
    - associate figures with solutions
    - preserve figure metadata

    IMPORTANT:
    This stage only LINKS figures.
    It does NOT OCR or crop them.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.max_vertical_distance = getattr(
            config,
            "max_figure_distance",
            400
        )

        self.min_link_score = getattr(
            config,
            "min_figure_link_score",
            0.60
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def link(
        self,
        semantic_regions,
        classified_blocks
    ):

        # ---------------------------------------------
        # Extract figure candidates
        # ---------------------------------------------
        figure_blocks = self._extract_figures(
            classified_blocks
        )

        # ---------------------------------------------
        # Attach figures to semantic regions
        # ---------------------------------------------
        for region in semantic_regions:

            linked_figures = []

            for figure in figure_blocks:

                score = self._score_figure(
                    region,
                    figure
                )

                if score >= self.min_link_score:

                    linked_figures.append(figure)

            # Attach linked figures
            region.figure_blocks = linked_figures

        return semantic_regions

    # =====================================================
    # FIGURE EXTRACTION
    # =====================================================

    def _extract_figures(
        self,
        classified_blocks
    ) -> List[FigureBlock]:

        figures = []

        for classified in classified_blocks:

            semantic_type = classified.semantic_type

            layout = (
                classified
                .ordered_block
                .layout_block
            )

            # -----------------------------------------
            # Detect figure-like semantic blocks
            # -----------------------------------------
            if semantic_type in [
                "figure",
                "table",
                "image",
            ]:

                figures.append(
                    FigureBlock(
                        figure_id=str(uuid.uuid4()),

                        page_number=layout.page_number,

                        bbox=layout.bbox,

                        figure_type=semantic_type,

                        caption=layout.text[:200],

                        source_block=classified
                    )
                )

            # -----------------------------------------
            # Detect figure references in misc blocks
            # -----------------------------------------
            elif self._looks_like_figure(
                layout.text
            ):

                figures.append(
                    FigureBlock(
                        figure_id=str(uuid.uuid4()),

                        page_number=layout.page_number,

                        bbox=layout.bbox,

                        figure_type="figure",

                        caption=layout.text[:200],

                        source_block=classified
                    )
                )

        return figures

    # =====================================================
    # FIGURE SCORING
    # =====================================================

    def _score_figure(
        self,
        region,
        figure
    ) -> float:

        # ---------------------------------------------
        # SIGNAL 1: PAGE MATCH
        # ---------------------------------------------
        if (
            region.page_start
            <= figure.page_number
            <= region.page_end
        ):
            page_score = 1.0
        else:
            page_score = 0.0

        # ---------------------------------------------
        # SIGNAL 2: VERTICAL DISTANCE
        # ---------------------------------------------
        distance = self._vertical_distance(
            region.bbox,
            figure.bbox
        )

        distance_score = max(
            0,
            1 - (
                distance
                / self.max_vertical_distance
            )
        )

        # ---------------------------------------------
        # SIGNAL 3: TEXT REFERENCE
        # ---------------------------------------------
        text = region.text.lower()

        reference_words = [
            "figure",
            "fig.",
            "diagram",
            "shown below",
            "shown in figure",
            "graph below",
        ]

        reference_score = 1.0 if any(
            word in text
            for word in reference_words
        ) else 0.0

        # ---------------------------------------------
        # SIGNAL 4: HORIZONTAL OVERLAP
        # ---------------------------------------------
        overlap_score = self._horizontal_overlap_score(
            region.bbox,
            figure.bbox
        )

        # ---------------------------------------------
        # FINAL SCORE
        # ---------------------------------------------
        score = (
            0.40 * page_score +
            0.25 * distance_score +
            0.20 * reference_score +
            0.15 * overlap_score
        )

        return score

    # =====================================================
    # FIGURE DETECTION HEURISTICS
    # =====================================================

    def _looks_like_figure(
        self,
        text: str
    ) -> bool:

        if not text:
            return False

        text = text.lower()

        figure_keywords = [
            "fig.",
            "figure",
            "diagram",
            "graph",
            "circuit",
            "shown below",
        ]

        return any(
            keyword in text
            for keyword in figure_keywords
        )

    # =====================================================
    # DISTANCE COMPUTATION
    # =====================================================

    def _vertical_distance(
        self,
        bbox1,
        bbox2
    ) -> float:

        y1 = bbox1[3]

        y2 = bbox2[1]

        return abs(y2 - y1)

    # =====================================================
    # HORIZONTAL OVERLAP
    # =====================================================

    def _horizontal_overlap_score(
        self,
        bbox1,
        bbox2
    ) -> float:

        x0_1, _, x1_1, _ = bbox1
        x0_2, _, x1_2, _ = bbox2

        overlap = max(
            0,
            min(x1_1, x1_2)
            - max(x0_1, x0_2)
        )

        width1 = x1_1 - x0_1

        width2 = x1_2 - x0_2

        min_width = min(width1, width2)

        if min_width <= 0:
            return 0.0

        return overlap / min_width

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_figure_summary(
        self,
        semantic_regions
    ):

        print("\n========== FIGURE LINKS ==========\n")

        for region in semantic_regions:

            figures = getattr(
                region,
                "figure_blocks",
                []
            )

            print(
                f"[{region.region_type.upper()}] "
                f"QID={region.qid} | "
                f"Figures={len(figures)}"
            )

            for fig in figures:

                print(
                    f"   ↳ FIGURE "
                    f"(Page {fig.page_number}) "
                    f"{fig.caption[:100]}"
                )

            print("-" * 80)
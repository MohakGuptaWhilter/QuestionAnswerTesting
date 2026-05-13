from dataclasses import dataclass
from typing import List, Tuple
import re
import uuid

from arihant_pipeline.pdf_loader import TextBlock


@dataclass
class LayoutBlock:

    block_id: str

    page_number: int

    bbox: Tuple[float, float, float, float]

    block_type: str

    text: str

    lines: list

    confidence: float

    metadata: dict


class LayoutAnalyzer:

    """
    Responsible for converting raw PDF blocks
    into coherent visual layout regions.
    """

    # Patterns that must start a new block — never merge INTO these
    BLOCK_START_PATTERN = re.compile(
        r"^(example\s+\d+\.|sol\.|ans\.|\d+\.\s)",
        re.IGNORECASE
    )

    def __init__(self, config):

        self.config = config

    def _average_font_size(self, block):

        sizes = []

        for line in block.lines:
            for span in line.spans:
                if span.text.strip():
                    sizes.append(span.size)

        if not sizes:
            return 0.0

        return sum(sizes) / len(sizes)

    def _merge_blocks(self, blocks):

        if not blocks:
            return []

        # Sort top-to-bottom, left-to-right so gap calculations are valid
        sorted_blocks = sorted(
            blocks,
            key=lambda b: (b.bbox[1], b.bbox[0])
        )

        merged = []

        # Accumulate merge state without touching original TextBlock objects
        cur_bbox = sorted_blocks[0].bbox
        cur_text = sorted_blocks[0].text
        cur_lines = list(sorted_blocks[0].lines)

        for nxt in sorted_blocks[1:]:

            if self._should_merge_bboxes(cur_bbox, nxt.bbox) and not self.BLOCK_START_PATTERN.match(nxt.text.strip()):

                cur_text += "\n" + nxt.text
                cur_lines = cur_lines + list(nxt.lines)
                cur_bbox = (
                    min(cur_bbox[0], nxt.bbox[0]),
                    min(cur_bbox[1], nxt.bbox[1]),
                    max(cur_bbox[2], nxt.bbox[2]),
                    max(cur_bbox[3], nxt.bbox[3]),
                )

            else:

                merged.append(
                    TextBlock(
                        bbox=cur_bbox,
                        lines=cur_lines,
                        text=cur_text
                    )
                )

                cur_bbox = nxt.bbox
                cur_text = nxt.text
                cur_lines = list(nxt.lines)

        merged.append(
            TextBlock(
                bbox=cur_bbox,
                lines=cur_lines,
                text=cur_text
            )
        )

        return merged

    def _detect_block_type(self, block):

        avg_font = self._average_font_size(block)

        text = block.text.strip()

        if avg_font > 16:
            return "heading"

        # Separator: trivially short and non-alphanumeric (rules, dividers)
        if len(text) < 5 and not any(c.isalnum() for c in text):
            return "separator"

        return "text"

    def _should_merge_bboxes(self, bbox1, bbox2):

        vertical_gap = bbox2[1] - bbox1[3]

        same_alignment = abs(bbox1[0] - bbox2[0]) < 15

        return vertical_gap < 20 and same_alignment

    def _should_merge(self, b1, b2):

        if self.BLOCK_START_PATTERN.match(b2.text.strip()):
            return False

        return self._should_merge_bboxes(b1.bbox, b2.bbox)

    def _is_header_or_footer(self, block_bbox, page_height, margin=40):

        y0 = block_bbox[1]
        y1 = block_bbox[3]

        return y0 < margin or y1 > page_height - margin

    def analyze(
        self,
        document,
        _rendered_pages
    ) -> List[LayoutBlock]:

        layout_blocks = []

        for page in document.pages:

            # -----------------------------------
            # Step 1: Merge fragmented blocks
            # -----------------------------------
            merged_blocks = self._merge_blocks(
                page.text_blocks
            )

            # -----------------------------------
            # Step 2: Detect layout types and
            #         strip headers / footers
            # -----------------------------------
            for block in merged_blocks:

                if self._is_header_or_footer(
                    block.bbox,
                    page.height
                ):
                    continue

                block_type = self._detect_block_type(block)

                layout_block = LayoutBlock(
                    block_id=str(uuid.uuid4()),
                    page_number=page.page_number,
                    bbox=block.bbox,
                    block_type=block_type,
                    text=block.text,
                    lines=block.lines,
                    confidence=0.95,
                    metadata={}
                )

                layout_blocks.append(layout_block)

        return layout_blocks

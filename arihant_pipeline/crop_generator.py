from dataclasses import dataclass
from typing import List, Dict
import numpy as np
import uuid


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class CropObject:
    """
    Represents a generated OCR/VLM-ready crop.
    """

    crop_id: str

    region_id: str

    region_type: str

    qid: str

    image: np.ndarray

    bbox: tuple

    page_number: int

    metadata: dict


# =========================================================
# CROP GENERATOR
# =========================================================

class CropGenerator:
    """
    Generates OCR-ready image crops from semantic regions.

    Responsibilities:
    - merge figure regions
    - apply intelligent padding
    - convert PDF coords -> image coords
    - generate high-quality crops
    - trim excessive whitespace

    IMPORTANT:
    Crop quality directly impacts OCR/VLM quality.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.padding = getattr(
            config,
            "crop_padding",
            15
        )

        self.whitespace_margin = getattr(
            config,
            "whitespace_margin",
            10
        )

        self.enable_trim = getattr(
            config,
            "enable_trim",
            True
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def generate(
        self,
        validated_regions,
        rendered_pages
    ) -> List[CropObject]:

        crops = []

        # ---------------------------------------------
        # Rendered page lookup
        # ---------------------------------------------
        page_map = {
            page.page_number: page
            for page in rendered_pages
        }

        # ---------------------------------------------
        # Generate crop per region
        # ---------------------------------------------
        for region in validated_regions:

            # Skip invalid regions
            if not getattr(region, "is_valid", True):
                continue

            try:

                crop = self._generate_region_crop(
                    region,
                    page_map
                )

                crops.append(crop)

            except Exception as e:

                print(
                    f"[CropGenerator] Failed region "
                    f"{region.region_id}: {str(e)}"
                )

        return crops

    # =====================================================
    # REGION CROP
    # =====================================================

    def _generate_region_crop(
        self,
        region,
        page_map: Dict
    ) -> CropObject:

        # ---------------------------------------------
        # Base semantic bbox
        # ---------------------------------------------
        bbox = region.bbox

        # ---------------------------------------------
        # Merge figure bboxes
        # ---------------------------------------------
        figure_blocks = getattr(
            region,
            "figure_blocks",
            []
        )

        for figure in figure_blocks:

            bbox = self._merge_bboxes(
                bbox,
                figure.bbox
            )

        # ---------------------------------------------
        # Add padding
        # ---------------------------------------------
        bbox = self._add_padding(
            bbox
        )

        # ---------------------------------------------
        # Page lookup
        # ---------------------------------------------
        page_number = region.page_start

        rendered_page = page_map[
            page_number
        ]

        # ---------------------------------------------
        # Convert PDF coords -> image coords
        # ---------------------------------------------
        x0, y0, x1, y1 = (
            rendered_page.pdf_to_image_coords(
                bbox
            )
        )

        # ---------------------------------------------
        # Clamp coordinates
        # ---------------------------------------------
        x0 = max(0, x0)
        y0 = max(0, y0)

        x1 = min(
            rendered_page.width,
            x1
        )

        y1 = min(
            rendered_page.height,
            y1
        )

        # ---------------------------------------------
        # Crop image
        # ---------------------------------------------
        img = rendered_page.image

        crop_img = img[
            y0:y1,
            x0:x1
        ]

        # ---------------------------------------------
        # Trim whitespace
        # ---------------------------------------------
        if self.enable_trim:

            crop_img = self._trim_whitespace(
                crop_img
            )

        # ---------------------------------------------
        # Build crop object
        # ---------------------------------------------
        return CropObject(

            crop_id=str(uuid.uuid4()),

            region_id=region.region_id,

            region_type=region.region_type,

            qid=region.qid,

            image=crop_img,

            bbox=bbox,

            page_number=page_number,

            metadata={

                "validation_score":
                    getattr(
                        region,
                        "validation_score",
                        None
                    ),

                "figure_count":
                    len(figure_blocks),

                "pages":
                    (
                        region.page_start,
                        region.page_end
                    )
            }
        )

    # =====================================================
    # PADDING
    # =====================================================

    def _add_padding(
        self,
        bbox
    ):

        x0, y0, x1, y1 = bbox

        return (
            x0 - self.padding,
            y0 - self.padding,
            x1 + self.padding,
            y1 + self.padding
        )

    # =====================================================
    # BBOX MERGING
    # =====================================================

    def _merge_bboxes(
        self,
        bbox1,
        bbox2
    ):

        return (

            min(bbox1[0], bbox2[0]),

            min(bbox1[1], bbox2[1]),

            max(bbox1[2], bbox2[2]),

            max(bbox1[3], bbox2[3]),
        )

    # =====================================================
    # WHITESPACE TRIMMING
    # =====================================================

    def _trim_whitespace(
        self,
        image
    ):

        if image.size == 0:
            return image

        # -----------------------------------------
        # Convert to grayscale manually
        # -----------------------------------------
        if len(image.shape) == 3:

            gray = np.mean(
                image,
                axis=2
            ).astype(np.uint8)

        else:
            gray = image

        # -----------------------------------------
        # Detect non-white pixels
        # -----------------------------------------
        mask = gray < 250

        coords = np.argwhere(mask)

        if coords.size == 0:
            return image

        # -----------------------------------------
        # Bounding box
        # -----------------------------------------
        y0, x0 = coords.min(axis=0)
        y1, x1 = coords.max(axis=0)

        # -----------------------------------------
        # Add safety margin
        # -----------------------------------------
        margin = self.whitespace_margin

        y0 = max(0, y0 - margin)
        x0 = max(0, x0 - margin)

        y1 = min(image.shape[0], y1 + margin)
        x1 = min(image.shape[1], x1 + margin)

        return image[
            y0:y1,
            x0:x1
        ]
    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_crop_summary(
        self,
        crops
    ):

        print(
            "\n========== GENERATED CROPS ==========\n"
        )

        for crop in crops:

            h, w = crop.image.shape[:2]

            print(
                f"[{crop.region_type.upper()}] "
                f"QID={crop.qid} | "
                f"Page={crop.page_number} | "
                f"Size={w}x{h}"
            )

            print(
                f"Validation Score: "
                f"{crop.metadata.get('validation_score')}"
            )

            print("-" * 80)
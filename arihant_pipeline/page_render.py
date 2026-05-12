import fitz
import numpy as np
from dataclasses import dataclass
from typing import Tuple, List, Optional


@dataclass
class RenderedPage:
    """
    Represents a rendered PDF page in image space.
    """

    page_number: int
    image: np.ndarray
    width: int
    height: int
    dpi: int

    # Coordinate transform factors
    scale_x: float
    scale_y: float

    # Original PDF dimensions
    pdf_width: float
    pdf_height: float

    # Optional cached path
    image_path: Optional[str] = None

    def pdf_to_image_coords(
        self,
        bbox: Tuple[float, float, float, float]
    ) -> Tuple[int, int, int, int]:
        """
        Convert PDF-space bbox to image-space bbox.
        """

        x0, y0, x1, y1 = bbox

        return (
            int(x0 * self.scale_x),
            int(y0 * self.scale_y),
            int(x1 * self.scale_x),
            int(y1 * self.scale_y),
        )

    def image_to_pdf_coords(
        self,
        bbox: Tuple[int, int, int, int]
    ) -> Tuple[float, float, float, float]:
        """
        Convert image-space bbox to PDF-space bbox.
        """

        x0, y0, x1, y1 = bbox

        return (
            x0 / self.scale_x,
            y0 / self.scale_y,
            x1 / self.scale_x,
            y1 / self.scale_y,
        )


class PageRenderer:
    """
    Responsible for rendering PDF pages into image-space.

    This class:
    - renders vector PDF pages into pixel images
    - preserves coordinate mappings
    - normalizes rotations
    - supports configurable DPI
    """

    def __init__(self, config):
        self.config = config

    def render(self, document) -> List[RenderedPage]:
        """
        Render all pages in the document.

        Returns:
            List[RenderedPage]
        """

        rendered_pages = []

        dpi = getattr(self.config, "dpi", 300)

        # PDF internally uses 72 DPI
        zoom = dpi / 72

        matrix = fitz.Matrix(zoom, zoom)

        pdf = fitz.open(document.pdf_path)

        try:
            for idx, page in enumerate(pdf):

                # ---------------------------------------
                # Handle page rotation
                # ---------------------------------------
                rotation = page.rotation

                if rotation != 0:
                    page.set_rotation(0)

                # ---------------------------------------
                # Render page
                # ---------------------------------------
                pix = page.get_pixmap(
                    matrix=matrix,
                    alpha=False
                )

                # ---------------------------------------
                # Convert pixmap to numpy image
                # ---------------------------------------
                img = np.frombuffer(
                    pix.samples,
                    dtype=np.uint8
                ).reshape(
                    pix.height,
                    pix.width,
                    pix.n
                )

                # ---------------------------------------
                # Handle grayscale pages
                # ---------------------------------------
                if pix.n == 1:
                    img = np.stack([img] * 3, axis=-1)

                # ---------------------------------------
                # Compute coordinate transforms
                # ---------------------------------------
                pdf_width = page.rect.width
                pdf_height = page.rect.height

                scale_x = pix.width / pdf_width
                scale_y = pix.height / pdf_height

                rendered_page = RenderedPage(
                    page_number=idx + 1,
                    image=img,
                    width=pix.width,
                    height=pix.height,
                    dpi=dpi,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    pdf_width=pdf_width,
                    pdf_height=pdf_height,
                )

                rendered_pages.append(rendered_page)

        finally:
            pdf.close()

        return rendered_pages

    def render_single_page(
        self,
        pdf_path: str,
        page_number: int,
        dpi: Optional[int] = None
    ) -> RenderedPage:
        """
        Render a single page independently. page_number is 1-based.

        Useful for:
        - retries
        - debugging
        - selective OCR
        """

        dpi = dpi or self.config.dpi

        zoom = dpi / 72

        matrix = fitz.Matrix(zoom, zoom)

        pdf = fitz.open(pdf_path)

        try:
            page = pdf[page_number - 1]

            rotation = page.rotation
            if rotation != 0:
                page.set_rotation(0)

            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False
            )

            img = np.frombuffer(
                pix.samples,
                dtype=np.uint8
            ).reshape(
                pix.height,
                pix.width,
                pix.n
            )

            if pix.n == 1:
                img = np.stack([img] * 3, axis=-1)

            pdf_width = page.rect.width
            pdf_height = page.rect.height

            scale_x = pix.width / pdf_width
            scale_y = pix.height / pdf_height

            return RenderedPage(
                page_number=page_number,
                image=img,
                width=pix.width,
                height=pix.height,
                dpi=dpi,
                scale_x=scale_x,
                scale_y=scale_y,
                pdf_width=pdf_width,
                pdf_height=pdf_height,
            )

        finally:
            pdf.close()

    def render_region(
        self,
        pdf_path: str,
        page_number: int,
        bbox: Tuple[float, float, float, float],
        dpi: Optional[int] = None,
        padding: int = 10,
    ) -> np.ndarray:
        """
        Render a specific PDF-space region.

        Extremely useful later for:
        - question crops
        - figure crops
        - OCR retries
        - high-resolution equations
        """

        dpi = dpi or self.config.dpi

        zoom = dpi / 72

        matrix = fitz.Matrix(zoom, zoom)

        pdf = fitz.open(pdf_path)

        try:
            page = pdf[page_number - 1]

            x0, y0, x1, y1 = bbox

            rect = fitz.Rect(
                x0 - padding,
                y0 - padding,
                x1 + padding,
                y1 + padding,
            )

            pix = page.get_pixmap(
                matrix=matrix,
                clip=rect,
                alpha=False
            )

            img = np.frombuffer(
                pix.samples,
                dtype=np.uint8
            ).reshape(
                pix.height,
                pix.width,
                pix.n
            )

            if pix.n == 1:
                img = np.stack([img] * 3, axis=-1)

            return img

        finally:
            pdf.close()
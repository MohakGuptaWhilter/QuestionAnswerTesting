import fitz
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional


@dataclass
class TextSpan:
    text: str
    font: str
    size: float
    bbox: tuple


@dataclass
class TextLine:
    bbox: tuple
    spans: list
    text: str


@dataclass
class TextBlock:
    bbox: tuple
    lines: list
    text: str


@dataclass
class PageNode:
    page_number: int
    width: float
    height: float
    text_blocks: list
    native_text: str
    is_scanned: bool
    rotation: int = 0
    font_statistics: dict = field(default_factory=dict)


@dataclass
class Document:
    pdf_path: str
    metadata: dict
    pages: list


class PDFLoadError(Exception):
    pass


class PDFLoader:
    def __init__(self, config):
        self.config = config

    def _parse_blocks(self, page_dict):
        blocks = []
        for block in page_dict["blocks"]:
            if block["type"] != 0:
                continue
            lines = []
            for line in block["lines"]:
                spans = []
                for span in line["spans"]:
                    spans.append(
                        TextSpan(
                            text=span["text"],
                            font=span["font"],
                            size=span["size"],
                            bbox=span["bbox"]
                        )
                    )
                line_text = " ".join(s.text for s in spans)
                lines.append(
                    TextLine(
                        bbox=line["bbox"],
                        spans=spans,
                        text=line_text
                    )
                )
            block_text = "\n".join(l.text for l in lines)
            blocks.append(
                TextBlock(
                    bbox=block["bbox"],
                    lines=lines,
                    text=block_text
                )
            )
        return blocks

    def _detect_scanned(self, page, native_text, blocks):
        text_chars = len(native_text.strip())
        if text_chars < 20:
            return True
        # Check image coverage vs page area
        page_area = page.rect.width * page.rect.height
        if page_area == 0:
            return True
        image_area = 0.0
        for img in page.get_image_info(hashes=False):
            x0, y0, x1, y1 = img["bbox"]
            image_area += (x1 - x0) * (y1 - y0)
        image_ratio = image_area / page_area
        # High image coverage with sparse text signals a scanned page
        if image_ratio > 0.7 and text_chars < 200:
            return True
        return False

    def _compute_font_statistics(self, blocks):
        sizes = []
        for block in blocks:
            for line in block.lines:
                for span in line.spans:
                    if span.text.strip():
                        sizes.append(round(span.size, 1))
        if not sizes:
            return {}
        counts = Counter(sizes)
        most_common_size, _ = counts.most_common(1)[0]
        return {
            "most_common_font_size": most_common_size,
            "largest_font_size": max(sizes),
            "smallest_font_size": min(sizes),
        }

    def _validate(self, doc, pdf_path):
        if doc.is_encrypted:
            raise PDFLoadError(f"PDF is encrypted: {pdf_path}")
        if len(doc) == 0:
            raise PDFLoadError(f"PDF has no pages: {pdf_path}")

    def load(self, pdf_path):
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFLoadError(f"Cannot open PDF '{pdf_path}': {e}") from e
        self._validate(doc, pdf_path)
        metadata = {
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "page_count": len(doc),
        }
        pages = []
        for idx in range(len(doc)):
            page = doc[idx]
            page_height = page.rect.height
            page_dict = page.get_text("dict")
            blocks = self._parse_blocks(page_dict)
            native_text = page.get_text()
            is_scanned = self._detect_scanned(page, native_text, blocks)
            font_stats = self._compute_font_statistics(blocks)
            pages.append(
                PageNode(
                    page_number=idx + 1,
                    width=page.rect.width,
                    height=page_height,
                    text_blocks=blocks,
                    native_text=native_text,
                    is_scanned=is_scanned,
                    rotation=page.rotation,
                    font_statistics=font_stats
                )
            )
        return Document(
            pdf_path=pdf_path,
            metadata=metadata,
            pages=pages
        )
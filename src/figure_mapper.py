import os
import re
import uuid
import tempfile
from typing import Dict, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None

try:
    import boto3
    from botocore.config import Config as BotocoreConfig
    _BOTO3 = True
except ImportError:
    _BOTO3 = False

_RENDER_ZOOM = 2.0


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _upload_to_s3(local_path: str) -> str:
    if not _BOTO3:
        raise RuntimeError("boto3 is not installed")
    bucket = os.environ['AWS_S3_BUCKET']
    region = os.getenv('AWS_REGION', 'us-east-1')
    key    = f"figures/{os.path.basename(local_path)}"
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=region,
        config=BotocoreConfig(signature_version='s3v4'),
    )
    s3.upload_file(local_path, bucket, key, ExtraArgs={'ContentType': 'image/png'})
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=604800,
    )


def _crop_and_upload(doc, page_idx: int, rect) -> Optional[str]:
    try:
        pix  = doc[page_idx].get_pixmap(matrix=fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM), clip=rect)
        path = os.path.join(tempfile.gettempdir(), f'qa_fig_{uuid.uuid4().hex}.png')
        pix.save(path)
        return _upload_to_s3(path)
    except Exception:
        return None


# ── Figure region detection ───────────────────────────────────────────────────

def _detect_figure_regions(page) -> List:
    """Return bboxes of embedded images, skipping tiny images and full-page scans."""
    page_area = page.rect.width * page.rect.height
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:
        return []

    smask_xrefs = {i['smask'] for i in infos if i.get('smask')}
    seen: set   = set()
    rects: List = []

    for info in infos:
        if info.get('xref', 0) in smask_xrefs:
            continue
        b = info.get('bbox')
        if not b:
            continue
        pos_key = (round(b[0]), round(b[1]), round(b[2]), round(b[3]))
        if pos_key in seen:
            continue
        seen.add(pos_key)
        w, h = b[2] - b[0], b[3] - b[1]
        if w < 50 or h < 50 or w * h > 0.85 * page_area:
            continue
        rects.append(fitz.Rect(*b))

    return sorted(rects, key=lambda r: (r.y0, r.x0))


# ── Mapper ────────────────────────────────────────────────────────────────────

class FigureMapper:
    """
    Builds a question-number → [s3_url, ...] mapping by page position
    BEFORE GPT runs, so figure URLs are never lost even if GPT omits [[FIGURE_N]].

    Also owns figure_map (counter→url) and page_regions (page→numbered rects)
    that the annotation and marker-replacement steps need, so there is only one
    S3 upload per figure.
    """

    _Q_NUM = re.compile(r'^\s*(?:Q\.?\s*)?(\d+)[\.\)\s]', re.IGNORECASE)

    def __init__(self, doc, page_indices: List[int]):
        self._doc          = doc
        self._page_indices = page_indices
        self.figure_map:   Dict[int, str]         = {}  # counter → s3_url
        self.page_regions: Dict[int, List[Tuple]] = {}  # page_idx → [(counter, rect)]
        self._q_figures:   Dict[str, List[str]]   = {}  # question_num → [url, ...]

    def build(self) -> "FigureMapper":
        fig_counter = 1
        for pi in self._page_indices:
            page    = self._doc[pi]
            figures = _detect_figure_regions(page)
            numbered: List[Tuple] = []
            q_pos = self._question_positions(page) if figures else []

            for rect in figures:
                url = _crop_and_upload(self._doc, pi, rect)
                if url:
                    self.figure_map[fig_counter] = url
                    q_num = self._nearest_above(rect.y0, q_pos)
                    if q_num:
                        self._q_figures.setdefault(q_num, []).append(url)
                numbered.append((fig_counter, rect))
                fig_counter += 1

            self.page_regions[pi] = numbered
        return self

    def inject(self, items: List[Dict]) -> None:
        """Append [[FIGURE_URL:...]] to any question that GPT did not annotate."""
        for item in items:
            q_text = item.get("question") or ""
            if not q_text or "[[FIGURE_URL:" in q_text:
                continue
            num = self._extract_num(str(item.get("number") or ""))
            if not num:
                continue
            for url in self._q_figures.get(num, []):
                q_text += f" [[FIGURE_URL:{url}]]"
            item["question"] = q_text

    @staticmethod
    def _question_positions(page) -> List[Tuple[str, float]]:
        positions = []
        for block in page.get_text("blocks"):
            first_line = str(block[4]).strip().split("\n")[0]
            m = FigureMapper._Q_NUM.match(first_line)
            if m:
                positions.append((m.group(1), float(block[1])))
        return sorted(positions, key=lambda t: t[1])

    @staticmethod
    def _nearest_above(fig_y: float, q_positions: List[Tuple[str, float]]) -> Optional[str]:
        best = None
        for num, y in q_positions:
            if y <= fig_y:
                best = num
        return best

    @staticmethod
    def _extract_num(raw: str) -> Optional[str]:
        m = re.search(r'(\d+)', raw)
        return m.group(1) if m else None

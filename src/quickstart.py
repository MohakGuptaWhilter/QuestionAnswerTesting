import os
import re
import uuid
import tempfile
import boto3
import fitz
from botocore.config import Config
from dotenv import load_dotenv
from landingai_ade import LandingAIADE

load_dotenv()
client = LandingAIADE()

_FIGURE_RE = re.compile(r'<::([\s\S]*?): figure::>')


def _crop_to_file(pdf_path: str, page_num: int, box, scale: float = 3.0) -> str:
    doc = fitz.open(pdf_path)
    page = doc[max(0, min(page_num, len(doc) - 1))]
    r = page.rect
    pad = 0.01
    clip = fitz.Rect(
        max(0.0, (box.left  - pad) * r.width),
        max(0.0, (box.top   - pad) * r.height),
        min(r.width,  (box.right  + pad) * r.width),
        min(r.height, (box.bottom + pad) * r.height),
    )
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
    path = os.path.join(tempfile.gettempdir(), f'qa_fig_{uuid.uuid4().hex}.png')
    pix.save(path)
    doc.close()
    return path


def _upload_to_s3(local_path: str) -> str:
    bucket = os.environ['AWS_S3_BUCKET']
    region = os.getenv('AWS_REGION', 'us-east-1')
    key    = f"figures/{os.path.basename(local_path)}"

    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=region,
        config=Config(signature_version='s3v4'),
    )
    s3.upload_file(local_path, bucket, key, ExtraArgs={'ContentType': 'image/png'})

    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=604800,  # 7 days
    )


def parse_pdf(pdf_source: str, model: str = "dpt-2-latest") -> dict:
    """Parse a PDF.  Figure placeholders are replaced with [[FIGURE_URL:<s3_url>]]
    so callers can extract them from question text without needing the chunks."""
    is_local = os.path.isfile(pdf_source)

    if is_local:
        with open(pdf_source, "rb") as f:
            parse_response = client.parse(document=f, model=model)
    else:
        parse_response = client.parse(document_url=pdf_source, model=model)

    markdown = parse_response.markdown

    if is_local:
        for chunk in parse_response.chunks:
            if chunk.type != 'figure':
                continue
            m = _FIGURE_RE.search(chunk.markdown)
            if not m:
                continue
            try:
                local_path = _crop_to_file(pdf_source, chunk.grounding.page, chunk.grounding.box)
                url = _upload_to_s3(local_path)
                markdown = markdown.replace(m.group(0), f'[[FIGURE_URL:{url}]]', 1)
            except Exception:
                markdown = markdown.replace(m.group(0), '', 1)

    return {
        "markdown": markdown,
        "metadata": parse_response.metadata,
    }

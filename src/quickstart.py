import os
from dotenv import load_dotenv
from landingai_ade import LandingAIADE

load_dotenv()

# Initialize the client
client = LandingAIADE()


def parse_pdf(pdf_source: str, model: str = "dpt-2-latest") -> dict:
    """Parse a PDF from a local file path or URL and return structured results."""
    is_local = os.path.isfile(pdf_source)

    if is_local:
        with open(pdf_source, "rb") as f:
            parse_response = client.parse(document=f, model=model)
    else:
        parse_response = client.parse(document_url=pdf_source, model=model)

    return {
        "markdown": parse_response.markdown,
        "chunks": parse_response.chunks,
        "grounding": parse_response.grounding,
        "metadata": parse_response.metadata,
    }

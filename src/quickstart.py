import json
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


def extract_questions(markdown: str, model: str = "extract-latest") -> list:
    """Extract only the questions from parsed markdown."""
    schema_dict = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "List of all questions extracted from the document, in order",
                "items": {
                    "type": "string",
                    "description": "The exact question text as it appears in the document"
                }
            }
        }
    }
    extract_response = client.extract(
        schema=json.dumps(schema_dict),
        markdown=markdown,
        model=model,
    )
    return extract_response.extraction.get("questions", [])


def extract_answers(markdown: str, model: str = "extract-latest") -> list:
    """Extract only the correct answers from parsed markdown."""
    schema_dict = {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "description": "List of correct answers extracted from the document, in order",
                "items": {
                    "type": "string",
                    "description": "The correct answer or option as it appears in the document"
                }
            }
        }
    }
    extract_response = client.extract(
        schema=json.dumps(schema_dict),
        markdown=markdown,
        model=model,
    )
    return extract_response.extraction.get("answers", [])


def extract_qa_pairs(markdown: str, model: str = "extract-latest") -> list:
    """Extract all question and answer pairs from parsed markdown."""
    schema_dict = {
        "type": "object",
        "properties": {
            "qa_pairs": {
                "type": "array",
                "description": "List of all question and answer pairs extracted from the document",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The exact question as it appears in the document"
                        },
                        "answer": {
                            "type": "string",
                            "description": "The exact answer as it appears in the document"
                        }
                    },
                    "required": ["question", "answer"]
                }
            }
        }
    }

    extract_response = client.extract(
        schema=json.dumps(schema_dict),
        markdown=markdown,
        model=model,
    )
    return extract_response.extraction.get("qa_pairs", [])


if __name__ == "__main__":
    parse_result = parse_pdf("https://docs.landing.ai/examples/bank-statement.pdf")
    qa_pairs = extract_qa_pairs(parse_result["markdown"])

    print("\nExtracted Q&A pairs:")
    for pair in qa_pairs:
        print(f"Q: {pair['question']}")
        print(f"A: {pair['answer']}")
        print()
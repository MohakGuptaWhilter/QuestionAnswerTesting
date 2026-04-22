import os
import re
import requests as http_requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment


SEARCH_API_URL = "https://dev.api.kb.whilter.ai/api/search"
_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMGZkY2M5YmMtYzY0OC00YzRiLWE5NDUtNWE1NGJhZmYyZWI1IiwiZXhwIjoxNzc4OTkyNjI4fQ.vXssK0Dg3xWdOoVnq3zlZ1txrXtzjy7vZlQneeUmqHU"

_ILLEGAL_EXCEL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿]')

NOISE_PATTERNS = [
    re.compile(r'<a\s[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<!--.*?-->', re.DOTALL),
    re.compile(r'Text\s*&\s*Video Solutions.*', re.IGNORECASE),
    re.compile(r'Download MARKS App.*', re.IGNORECASE),
    re.compile(r'https?://\S+'),
    re.compile(r'Mathematics Top \d+ PYQs.*', re.IGNORECASE),
    re.compile(r'^MathonGo\s*$', re.IGNORECASE | re.MULTILINE),
]


def sanitize(text: str) -> str:
    return _ILLEGAL_EXCEL_CHARS.sub('', text) if text else text


def clean_question(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = pattern.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def call_search_api(question: str, agent_id: str, deployment_slug: str) -> str:
    payload = {
        "query": question,
        "agent_id": agent_id,
        "tenant_id": "e6475d6e-f357-443f-8ab9-f0f61081191e",
        "top_k": 5,
        "filters": {"additionalProp1": {}},
        "chat_history": [],
        "deployment_slug": deployment_slug,
        "llm_provider": {
            "provider": "openai",
            "model": "intellirag-gpt-5.2",
            "api_key": "string",
            "base_url": "string"
        },
        "embedding_provider": {
            "provider": "openai",
            "model": "intellirag-text-embedding-3-small"
        },
        "llm_routing": "true",
        "system_prompt": "string",
        "summary_prompt": False,
        "followup_questions": False
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {_AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        resp = http_requests.post(SEARCH_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            return f"[API error {resp.status_code}]"
        data = resp.json()
        answer = data.get("answer") or ""
        if not answer:
            return "[No answer returned]"
        answer = re.sub(r'\[\d+\]', '', answer)
        answer = re.sub(r'^#{1,6}\s+', '', answer, flags=re.MULTILINE)
        return answer.strip()
    except http_requests.exceptions.Timeout:
        return "[timeout]"
    except Exception as exc:
        return f"[error: {exc}]"


def check_correctness(api_response: str, correct_answer: str) -> str:
    if not api_response or api_response.startswith("["):
        return "Manual Review"

    correct = (correct_answer or "").strip()
    response_lower = api_response.lower()

    # MCQ answer: (1), (2), (3), (4) — cannot reliably match free text
    if re.match(r'^\(\d+\)$', correct):
        return "Manual Review"

    try:
        correct_num = float(correct)
        found_nums = re.findall(r'-?\d+(?:\.\d+)?', api_response)
        for n in found_nums:
            if abs(float(n) - correct_num) < 0.01:
                return "Correct"
        return "Incorrect"
    except ValueError:
        pass

    if correct.lower() in response_lower:
        return "Correct"

    return "Manual Review"


def build_evaluation_excel(
    questions: list,
    answers: list,
    api_responses: list,
    statuses: list,
    output_path: str,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Evaluation"

    ws.append(["Question #", "Question", "Correct Answer", "API Response", "Status"])

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    status_styles = {
        "Correct":       (PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
                          Font(color="006100", bold=True)),
        "Incorrect":     (PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
                          Font(color="9C0006", bold=True)),
        "Manual Review": (PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
                          Font(color="9C6500", bold=True)),
    }

    for idx, (question, answer, api_resp, status) in enumerate(
        zip(questions, answers, api_responses, statuses), start=1
    ):
        ws.append([idx, sanitize(question), sanitize(answer), sanitize(api_resp), status])
        row = ws.max_row
        ws.cell(row, 1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row, 2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        ws.cell(row, 3).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(row, 4).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        fill, font = status_styles.get(status, status_styles["Manual Review"])
        status_cell = ws.cell(row, 5)
        status_cell.fill = fill
        status_cell.font = font
        status_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 60
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 55
    ws.column_dimensions['E'].width = 18

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)

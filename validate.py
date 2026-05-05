import os
import json
import base64
import pandas as pd
import requests as _http
from flask import Blueprint, request, send_file, jsonify, current_app
from werkzeug.utils import secure_filename
from rapidfuzz import fuzz as _fuzz
from src.helpers import sanitize, build_validation_excel, latex_to_unicode
from src.pdf_utils import crop_questions_from_pdf, build_question_mapping


_VLM_VALIDATE_URL   = "http://localhost:11434/api/chat"
_VLM_VALIDATE_MODEL = "qwen2.5vl:7b"

_VLM_COMPARE_PROMPT = (
    "You are a precise exam-question validator.\n\n"
    "The image shows a question cropped from the original exam PDF.\n"
    "Below is the text that was transcribed for this question:\n\n"
    "TRANSCRIPTION:\n{excel_text}\n\n"
    "Decide whether the transcription is an accurate and complete representation "
    "of the question in the image.\n\n"
    "Evaluate:\n"
    "1. Is the question stem word-for-word correct (wording, numbers, math, units)?\n"
    "2. Are all answer choices present and correctly transcribed?\n"
    "3. Is mathematical notation (fractions, exponents, symbols) accurately captured?\n\n"
    'Return ONLY valid JSON with no surrounding text:\n'
    '{{"match": true/false, "issues": ["describe each discrepancy"], "confidence": 0.0-1.0}}'
)


def _vlm_compare_question(image_path: str, excel_text: str) -> dict:
    """Send the PDF question crop + Excel transcription to a VLM and get a match verdict."""
    prompt = _VLM_COMPARE_PROMPT.format(excel_text=excel_text.strip() or "(empty)")
    try:
        with open(image_path, "rb") as fh:
            image_b64 = base64.b64encode(fh.read()).decode()
        payload = {
            "model": _VLM_VALIDATE_MODEL,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512},
        }
        resp = _http.post(_VLM_VALIDATE_URL, json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()
        return json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except Exception as exc:
        return {"match": False, "issues": [f"VLM error: {exc}"], "confidence": 0.0, "error": True}


def _normalise_cols(df: pd.DataFrame) -> dict:
    """Return {normalised_name: original_column_name} for all columns."""
    return {
        c.strip().lower().replace(" ", "_").replace("#", "num"): c
        for c in df.columns
    }


def _pick_col(norm: dict, aliases: list):
    for a in aliases:
        if a in norm:
            return norm[a]
    return None


def _allowed_pdf(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'
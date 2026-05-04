import os
import json
import base64
import requests
import pandas as pd
from PIL import Image
from tqdm import tqdm
from rapidfuzz import fuzz
from pix2tex.cli import LatexOCR

# -------------------------
# CONFIG
# -------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-r1:14b"

IMAGE_DIR = "input/questions"
EXCEL_PATH = "input/excel.xlsx"
OUTPUT_PATH = "output/validated.xlsx"

SIMILARITY_THRESHOLD = 80


# -------------------------
# OCR (Pix2Text)
# -------------------------
ocr_model = LatexOCR()

def image_to_latex(image_path):
    try:
        img = Image.open(image_path)
        latex = ocr_model(img)
        return latex.strip()
    except Exception as e:
        return f"[OCR_ERROR]: {str(e)}"


# -------------------------
# RULE-BASED CHECKS
# -------------------------
def basic_validation(ocr_text, excel_text):
    issues = []

    # similarity check
    similarity = fuzz.ratio(ocr_text, excel_text)

    if similarity < SIMILARITY_THRESHOLD:
        issues.append(f"Low similarity: {similarity}")

    # option count check
    option_count = sum(excel_text.count(opt) for opt in ["(A)", "(B)", "(C)", "(D)"])
    if option_count != 4:
        issues.append("Option count mismatch")

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "similarity": similarity
    }


# -------------------------
# OLLAMA CALL
# -------------------------
def call_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )
    return response.json()["response"]


# -------------------------
# LLM VALIDATION
# -------------------------
def llm_validate(source, extracted):
    prompt = f"""
SOURCE:
{source}

EXTRACTED:
{extracted}

Compare both.

Return ONLY JSON:
{{
  "match": true/false,
  "issues": ["list differences"],
  "confidence": 0-1
}}
"""

    try:
        raw = call_ollama(prompt)

        # extract JSON safely
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])

        return parsed

    except Exception as e:
        return {
            "match": False,
            "issues": [f"LLM parse error: {str(e)}"],
            "confidence": 0
        }


# -------------------------
# MAIN PIPELINE
# -------------------------
def run_pipeline():
    df = pd.read_excel(EXCEL_PATH)

    results = []

    for idx, row in tqdm(df.iterrows(), total=len(df)):
        q_num = row["question_number"]
        excel_text = row["question_text"]
        excel_answer = row.get("answer", "")

        image_path = os.path.join(IMAGE_DIR, f"Q{q_num}.png")

        if not os.path.exists(image_path):
            results.append({
                "validation_status": "missing_image",
                "issues": "Image not found",
                "confidence": 0
            })
            continue

        # -----------------
        # OCR
        # -----------------
        ocr_text = image_to_latex(image_path)

        # -----------------
        # RULE CHECK
        # -----------------
        rule_check = basic_validation(ocr_text, excel_text)

        if not rule_check["pass"]:
            results.append({
                "validation_status": "rule_fail",
                "issues": "; ".join(rule_check["issues"]),
                "confidence": 0.2
            })
            continue

        # -----------------
        # LLM VALIDATION
        # -----------------
        llm_result = llm_validate(
            source=ocr_text,
            extracted=excel_text
        )

        status = "correct" if llm_result["match"] else "mismatch"

        results.append({
            "validation_status": status,
            "issues": "; ".join(llm_result["issues"]),
            "confidence": llm_result["confidence"]
        })

    # -----------------
    # SAVE
    # -----------------
    result_df = pd.concat([df, pd.DataFrame(results)], axis=1)
    result_df.to_excel(OUTPUT_PATH, index=False)

    print(f"\n✅ Done. Saved to {OUTPUT_PATH}")


# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    run_pipeline()
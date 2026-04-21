"""
Run this on your questions PDF to check if superscripts/subscripts
are detectable via font size in PyMuPDF dict mode.

Usage:
    python debug_pdf.py path/to/questions.pdf
"""
import sys
import fitz

def analyze_page(pdf_path, page_num=0):
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    blocks = page.get_text("dict")["blocks"]

    font_sizes = set()
    samples = []

    for block in blocks:
        if block["type"] != 0:  # text block
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                font_sizes.add(round(span["size"], 1))
                # collect a sample of each unique size
                if round(span["size"], 1) not in {s for s, _ in samples}:
                    samples.append((round(span["size"], 1), span["text"]))

    print(f"\nPage {page_num + 1} — distinct font sizes found:")
    for size in sorted(font_sizes):
        sample = next((t for s, t in samples if s == size), "")
        print(f"  size {size:5.1f} → '{sample[:60]}'")

    doc.close()

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "questions.pdf"
    analyze_page(path, page_num=0)
    analyze_page(path, page_num=1)

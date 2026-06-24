import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from services.ocr_service import extract_text_from_pdf

print("Running pipeline diagnostics on media/documents/Updated_Gym_Split.pdf...")

try:
    with open("media/documents/Updated_Gym_Split.pdf", "rb") as f:
        pdf_bytes = f.read()
    res = extract_text_from_pdf(pdf_bytes)
    print("Execution completed successfully.")
    print("Page strategies:", res.get("page_strategies"))
    print("Dominant strategy:", res.get("dominant_strategy"))
except Exception as e:
    print("Error during execution:", str(e))

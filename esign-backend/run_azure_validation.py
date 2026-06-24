import os
import sys
import logging
from unittest.mock import patch

# Configure stdout encoding to utf-8 for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Set up django settings before importing models/services
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
import django
django.setup()

from services.ocr_service import extract_text_from_pdf
from services.authority_extraction_service import analyze_contract_authority

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("validation")

def validate_pdf(pdf_path):
    print(f"\n=======================================================")
    print(f"VALIDING PDF: {pdf_path}")
    print(f"=======================================================")
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # 1. Run PaddleOCR
    print("\n--- Running with PaddleOCR ---")
    with patch.dict(os.environ, {"OCR_PROVIDER": "paddle"}):
        res_paddle = extract_text_from_pdf(pdf_bytes)
    
    analysis_paddle = analyze_contract_authority(
        res_paddle["raw_text"], 
        english_text=res_paddle.get("english_text", res_paddle["raw_text"]),
        arabic_text=res_paddle.get("arabic_text", res_paddle["raw_text"])
    )
    
    # 2. Run Azure OCR
    print("\n--- Running with Azure OCR ---")
    with patch.dict(os.environ, {"OCR_PROVIDER": "azure"}):
        try:
            res_azure = extract_text_from_pdf(pdf_bytes)
            analysis_azure = analyze_contract_authority(
                res_azure["raw_text"],
                english_text=res_azure.get("english_text", res_azure["raw_text"]),
                arabic_text=res_azure.get("arabic_text", res_azure["raw_text"])
            )
        except Exception as e:
            print(f"Azure OCR run failed with error: {e}")
            res_azure = None
            analysis_azure = None

    # Comparison Output
    print("\n=================== COMPARISON RESULTS ===================")
    print(f"{'Field':<30} | {'PaddleOCR Baseline':<35} | {'Azure OCR Pilot':<35}")
    print("-" * 110)
    
    def print_row(field_name, val_paddle, val_azure):
        p_str = str(val_paddle).replace("\n", " ")[:35]
        a_str = str(val_azure).replace("\n", " ")[:35]
        print(f"{field_name:<30} | {p_str:<35} | {a_str:<35}")
        
    if res_azure:
        print_row("Provider Key", res_paddle.get("ocr_provider"), res_azure.get("ocr_provider"))
        print_row("Average Confidence", res_paddle.get("ocr_confidence"), res_azure.get("ocr_confidence"))
        print_row("Raw Text Length", len(res_paddle.get("raw_text", "")), len(res_azure.get("raw_text", "")))
        print_row("Representative En", analysis_paddle.get("representative_name_en"), analysis_azure.get("representative_name_en"))
        print_row("Representative Ar", analysis_paddle.get("representative_name_ar"), analysis_azure.get("representative_name_ar"))
        print_row("Title En", analysis_paddle.get("title_en"), analysis_azure.get("title_en"))
        print_row("Title Ar", analysis_paddle.get("title_ar"), analysis_azure.get("title_ar"))
        print_row("Authority Clause En", analysis_paddle.get("authority_clause_en"), analysis_azure.get("authority_clause_en"))
        print_row("Authority Clause Ar", analysis_paddle.get("authority_clause_ar"), analysis_azure.get("authority_clause_ar"))
        print_row("Authority Confidence Score", analysis_paddle.get("confidence_score"), analysis_azure.get("confidence_score"))
        
        print("\n--- SAMPLE EXTRACTED TEXT (First 300 Chars) ---")
        print(f"PaddleOCR Raw Text Snippet:\n{res_paddle.get('raw_text', '')[:300]}")
        print("-" * 50)
        print(f"Azure OCR Raw Text Snippet:\n{res_azure.get('raw_text', '')[:300]}")
    else:
        print("Comparison skipped because Azure OCR failed.")
    print("==========================================================")

if __name__ == "__main__":
    # We will test with a bilingual PDF
    pdf_to_test = "media/documents/Updated_Gym_Split.pdf"
    if len(sys.argv) > 1:
        pdf_to_test = sys.argv[1]
    
    validate_pdf(pdf_to_test)

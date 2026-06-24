import os
import sys
import csv
import json
import time
from unittest.mock import patch

# Configure stdout encoding to utf-8 for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Set up django settings before importing models/services
# The script is in tools/, so we need to add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')

import django
django.setup()

from services.ocr_service import extract_text_from_pdf
from services.authority_extraction_service import analyze_contract_authority

def run_comparison():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    
    pdf_files = [
        "contract_001_transport_contract.pdf",
        "contract_002_operations_agreement.pdf",
        "contract_003_operations_agreement.pdf",
        "contract_004_supplier_agreement.pdf",
        "contract_005_nda.pdf"
    ]
    
    csv_rows = []
    
    # Summary metrics
    documents_tested = len(pdf_files)
    azure_success_count = 0
    paddle_success_count = 0
    azure_fallback_count = 0
    
    total_azure_time = 0.0
    total_paddle_time = 0.0
    
    print("\n" + "="*80)
    print("STARTING CONTROLLED OCR COMPARISON (AZURE VS PADDLE)")
    print("="*80 + "\n")
    
    for pdf_name in pdf_files:
        pdf_path = os.path.join(tools_dir, pdf_name)
        if not os.path.exists(pdf_path):
            print(f"ERROR: File not found: {pdf_path}")
            continue
            
        print(f"Processing: {pdf_name}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        # 1. Run PaddleOCR
        print("  Running PaddleOCR...")
        t_paddle_start = time.perf_counter()
        with patch.dict(os.environ, {"OCR_PROVIDER": "paddle"}):
            try:
                res_paddle = extract_text_from_pdf(pdf_bytes)
                paddle_success = True
            except Exception as e:
                print(f"    PaddleOCR failed with error: {e}")
                res_paddle = {}
                paddle_success = False
        t_paddle_end = time.perf_counter()
        paddle_duration_ms = (t_paddle_end - t_paddle_start) * 1000
        
        # Determine extraction details for PaddleOCR
        paddle_ocr_ms = res_paddle.get("ocr_ms")
        if paddle_ocr_ms is None:
            paddle_ocr_ms = paddle_duration_ms
            
        paddle_raw_text = res_paddle.get("raw_text", "")
        paddle_raw_text_length = len(paddle_raw_text)
        
        paddle_name_en = ""
        paddle_name_ar = ""
        paddle_title_en = ""
        paddle_title_ar = ""
        paddle_authority_detected = False
        
        if paddle_success and paddle_raw_text:
            paddle_success_count += 1
            analysis_paddle = analyze_contract_authority(
                paddle_raw_text,
                english_text=res_paddle.get("english_text", paddle_raw_text),
                arabic_text=res_paddle.get("arabic_text", paddle_raw_text)
            )
            paddle_name_en = analysis_paddle.get("representative_name_en") or ""
            paddle_name_ar = analysis_paddle.get("representative_name_ar") or ""
            paddle_title_en = analysis_paddle.get("title_en") or ""
            paddle_title_ar = analysis_paddle.get("title_ar") or ""
            paddle_authority_detected = bool(
                analysis_paddle.get("representative_name_en") or
                analysis_paddle.get("representative_name_ar") or
                analysis_paddle.get("authority_clause_en") or
                analysis_paddle.get("authority_clause_ar")
            )
            total_paddle_time += paddle_ocr_ms
            
        # 2. Run Azure OCR
        print("  Running Azure OCR...")
        t_azure_start = time.perf_counter()
        with patch.dict(os.environ, {"OCR_PROVIDER": "azure"}):
            try:
                res_azure = extract_text_from_pdf(pdf_bytes)
                azure_success = True
            except Exception as e:
                print(f"    Azure OCR request failed with error: {e}")
                res_azure = {}
                azure_success = False
        t_azure_end = time.perf_counter()
        azure_duration_ms = (t_azure_end - t_azure_start) * 1000
        
        azure_ocr_ms = res_azure.get("ocr_ms")
        if azure_ocr_ms is None:
            azure_ocr_ms = azure_duration_ms
            
        azure_raw_text = res_azure.get("raw_text", "")
        azure_raw_text_length = len(azure_raw_text)
        
        azure_name_en = ""
        azure_name_ar = ""
        azure_title_en = ""
        azure_title_ar = ""
        azure_authority_detected = False
        
        # Check if fallback happened
        azure_fallback = res_azure.get("fallback_used", False) or (res_azure.get("ocr_provider") == "paddle")
        
        if azure_success and azure_raw_text:
            if azure_fallback:
                azure_fallback_count += 1
            else:
                azure_success_count += 1
                total_azure_time += azure_ocr_ms
                
            analysis_azure = analyze_contract_authority(
                azure_raw_text,
                english_text=res_azure.get("english_text", azure_raw_text),
                arabic_text=res_azure.get("arabic_text", azure_raw_text)
            )
            azure_name_en = analysis_azure.get("representative_name_en") or ""
            azure_name_ar = analysis_azure.get("representative_name_ar") or ""
            azure_title_en = analysis_azure.get("title_en") or ""
            azure_title_ar = analysis_azure.get("title_ar") or ""
            azure_authority_detected = bool(
                analysis_azure.get("representative_name_en") or
                analysis_azure.get("representative_name_ar") or
                analysis_azure.get("authority_clause_en") or
                analysis_azure.get("authority_clause_ar")
            )
            
        # Informational columns
        same_name_en = (paddle_name_en == azure_name_en)
        same_name_ar = (paddle_name_ar == azure_name_ar)
        same_title_en = (paddle_title_en == azure_title_en)
        same_title_ar = (paddle_title_ar == azure_title_ar)
        same_authority_detected = (paddle_authority_detected == azure_authority_detected)
        
        row = {
            "file_name": pdf_name,
            "paddle_name_en": paddle_name_en,
            "azure_name_en": azure_name_en,
            "paddle_name_ar": paddle_name_ar,
            "azure_name_ar": azure_name_ar,
            "paddle_title_en": paddle_title_en,
            "azure_title_en": azure_title_en,
            "paddle_title_ar": paddle_title_ar,
            "azure_title_ar": azure_title_ar,
            "paddle_ocr_ms": round(paddle_ocr_ms, 2),
            "azure_ocr_ms": round(azure_ocr_ms, 2) if not azure_fallback else "",
            "paddle_confidence": res_paddle.get("ocr_confidence"),
            "azure_confidence": res_azure.get("ocr_confidence") if not azure_fallback else "",
            "paddle_raw_text_length": paddle_raw_text_length,
            "azure_raw_text_length": azure_raw_text_length,
            "paddle_authority_detected": paddle_authority_detected,
            "azure_authority_detected": azure_authority_detected,
            "paddle_fallback_used": res_paddle.get("fallback_used", False),
            "azure_fallback_used": azure_fallback,
            "same_name_en": same_name_en,
            "same_name_ar": same_name_ar,
            "same_title_en": same_title_en,
            "same_title_ar": same_title_ar,
            "same_authority_detected": same_authority_detected
        }
        csv_rows.append(row)
        
        # Print comparison log
        print(f"    Paddle: Name='{paddle_name_ar}' | '{paddle_name_en}', Title='{paddle_title_ar}' | '{paddle_title_en}', Detected={paddle_authority_detected}, Time={paddle_ocr_ms:.1f}ms")
        print(f"    Azure:  Name='{azure_name_ar}' | '{azure_name_en}', Title='{azure_title_ar}' | '{azure_title_en}', Detected={azure_authority_detected}, Time={azure_ocr_ms:.1f}ms (Fallback={azure_fallback})")
        print("-" * 50)

    # Write CSV
    csv_path = os.path.join(tools_dir, "comparison_results.csv")
    csv_headers = [
        "file_name", "paddle_name_en", "azure_name_en", "paddle_name_ar", "azure_name_ar",
        "paddle_title_en", "azure_title_en", "paddle_title_ar", "azure_title_ar",
        "paddle_ocr_ms", "azure_ocr_ms", "paddle_confidence", "azure_confidence",
        "paddle_raw_text_length", "azure_raw_text_length", "paddle_authority_detected",
        "azure_authority_detected", "paddle_fallback_used", "azure_fallback_used",
        "same_name_en", "same_name_ar", "same_title_en", "same_title_ar", "same_authority_detected"
    ]
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for r in csv_rows:
            writer.writerow(r)
            
    print(f"\nWritten results to: {csv_path}")
    
    # Calculate averages
    avg_paddle_time = total_paddle_time / max(paddle_success_count, 1)
    avg_azure_time = total_azure_time / max(azure_success_count, 1) if azure_success_count > 0 else 0.0
    
    summary = {
        "documents_tested": documents_tested,
        "azure_success_count": azure_success_count,
        "paddle_success_count": paddle_success_count,
        "azure_fallback_count": azure_fallback_count,
        "average_azure_time_ms": round(avg_azure_time, 2),
        "average_paddle_time_ms": round(avg_paddle_time, 2)
    }
    
    # Write JSON summary
    json_path = os.path.join(tools_dir, "ocr_comparison_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print(f"Written summary to: {json_path}")
    
    # Format a comparison table for console
    print("\n" + "="*100)
    print(f"{'File Name':<30} | {'Paddle Name (Ar)':<20} | {'Azure Name (Ar)':<20} | {'Same?':<5}")
    print("-"*100)
    for r in csv_rows:
        p_name = r["paddle_name_ar"]
        a_name = r["azure_name_ar"]
        # truncate for clean printing
        p_disp = p_name[:18] + ".." if len(p_name) > 18 else p_name
        a_disp = a_name[:18] + ".." if len(a_name) > 18 else a_name
        same_lbl = "Yes" if r["same_name_ar"] else "No"
        print(f"{r['file_name']:<30} | {p_disp:<20} | {a_disp:<20} | {same_lbl:<5}")
    print("="*100 + "\n")
    
    print("Summary:")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    run_comparison()

import os
import sys

# Ensure stdout handles encoding properly for console printing
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.insert(0, BASE_DIR)
# Set up django settings as services import models and constants
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
import django
django.setup()

from services.azure_ocr_service import extract_text_with_azure
from services.national_identity_service import parse_identity_document

def run_validation(image_path):
    if not os.path.exists(image_path):
        print(f"Error: File '{image_path}' does not exist.")
        sys.exit(1)
        
    print(f"Loading local image file: {image_path}")
    with open(image_path, "rb") as f:
        image_bytes = f.read()
        
    print("Executing Azure Document Intelligence OCR directly...")
    try:
        ocr_result = extract_text_with_azure(image_bytes)
        print("\n================ RAW OCR TEXT ================\n")
        print(ocr_result["raw_text"])
        print("\n=============================================\n")
    except Exception as e:
        print(f"Azure OCR run failed with error: {e}")
        print("extraction_status: failed")
        print("failure_reason: azure_error")
        sys.exit(1)
        
    raw_text = ocr_result.get("raw_text", "").strip()
    if not raw_text:
        print("OCR extraction completed but returned empty text.")
        print("extraction_status: failed")
        print("failure_reason: no_text_detected")
        sys.exit(0)
        
    print("Parsing extracted document fields...")
    parsed_fields = parse_identity_document(raw_text)
    
    # Strictly mask national ID to avoid printing raw values
    raw_id = parsed_fields.get("national_id_number", "")
    masked_id = "*" * max(0, len(raw_id) - 4) + raw_id[-4:] if raw_id else ""
    
    print("\n--- IDENTITY OCR EXTRACTED DETAILS ---")
    print(f"full_name:          {parsed_fields.get('full_name', '')}")
    print(f"masked_national_id: {masked_id}")
    print(f"date_of_birth:      {parsed_fields.get('date_of_birth')}")
    print(f"expiry_date:        {parsed_fields.get('expiry_date')}")
    print(f"document_type:      {parsed_fields.get('document_type', 'unknown')}")
    print("extraction_status:  success")
    print("--------------------------------------")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/run_identity_ocr_validation.py <path_to_image>")
        sys.exit(1)
    run_validation(sys.argv[1])

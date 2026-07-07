import os
import django
import sys
import json

# Setup django environment
BASE_DIR = r"c:\Users\Mohammed Hamza\esign_Module\esign-backend"
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
django.setup()

from services.gemini_contract_ocr import extract_contract_authorization

# Use the supplied contract PDF from the tools directory
PDF_PATH = os.path.join(BASE_DIR, "tools", "contract_001_transport_contract.pdf")

print("=" * 50)
print("Testing Gemini Contract OCR...")
print("=" * 50)

# First run: should be a cache miss/API call
print("\n--- Running Extraction (First run - expected cache miss/API call) ---")
result1 = extract_contract_authorization(PDF_PATH)
print("Result 1 Output:")
print(json.dumps(result1, indent=4, ensure_ascii=False))

# Second run: should be a cache hit
print("\n--- Running Extraction (Second run - expected cache hit) ---")
result2 = extract_contract_authorization(PDF_PATH)
print("Result 2 Output:")
print(json.dumps(result2, indent=4, ensure_ascii=False))

print("\nVerification checks:")
assert "representatives" in result1, "Failed schema check: representatives not in result"
assert "document_language" in result1, "Failed schema check: document_language not in result"
assert result1 == result2, "Cache mismatch: run 1 and run 2 returned different results"
print("All contract OCR caching assertions passed successfully!")

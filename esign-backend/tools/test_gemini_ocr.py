import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
django.setup()

from services.gemini_ocr_service import extract_identity_data

IMAGE_PATH = r"C:\Users\Mohammed Hamza\Downloads\id_ocr.jpeg" # <-- Change this

print("=" * 50)
print("Testing Gemini OCR...")
print("=" * 50)

result = extract_identity_data(IMAGE_PATH)

print(json.dumps(result, indent=4, ensure_ascii=False))

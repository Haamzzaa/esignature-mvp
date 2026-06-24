import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import fitz
import io
import numpy as np
from PIL import Image
from unittest.mock import patch

# Create a bilingual PDF
doc = fitz.open()
page = doc.new_page(width=600, height=800)

font_path = "C:\\Windows\\Fonts\\arial.ttf"
# Left column: English
page.insert_text(fitz.Point(50, 100), "This Agreement is represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager.", fontname="helv", fontsize=12)
page.insert_text(fitz.Point(50, 200), "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John", fontname="helv", fontsize=12)

# Right column: Arabic
page.insert_text(fitz.Point(350, 100), "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام.", fontname="arial", fontfile=font_path, fontsize=12)
page.insert_text(fitz.Point(350, 200), "الرئيس التنفيذي الرئيس التنفيذي الرئيس التنفيذي الرئيس التنفيذي", fontname="arial", fontfile=font_path, fontsize=12)

pdf_bytes = doc.write()
doc.close()

from services.ocr_service import extract_text_from_pdf

print("Starting pipeline diagnostic test...")

# Mock evaluate_arabic_quality to return a score that triggers adaptive_split_ocr strategy
mock_quality = {
    "score": 0.5,
    "arabic_chars": 10,
    "arabic_words": 2,
    "printable_ratio": 0.9,
    "garbage_ratio": 0.0
}

with patch("services.ocr_service.evaluate_arabic_quality", return_value=mock_quality):
    res = extract_text_from_pdf(pdf_bytes)

print("Pipeline diagnostic completed successfully.")

import os
import logging
import base64
import requests
import json
import datetime
import hashlib
from PIL import Image
from esign.models import SignerIdentityVerification, OcrCache

logger = logging.getLogger(__name__)

def parse_date(date_val):
    """
    Safely parses a date value into a datetime.date object.
    Supports datetime.date, datetime.datetime, and string formats.
    """
    if not date_val:
        return None
    if isinstance(date_val, datetime.date):
        return date_val
    if isinstance(date_val, datetime.datetime):
        return date_val.date()
    
    date_str = str(date_val).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def extract_identity_data(image_path):
    """
    Performs Gemini OCR on the identity document at the given image_path.
    Includes validation, caching, API interaction, and strict JSON output.
    """
    # 1. Validation Logic
    # Verify the image file exists
    if not os.path.exists(image_path):
        return {
            "error": "validation_failed",
            "message": f"Image file does not exist: {image_path}"
        }

    # Verify the file format is supported
    _, ext = os.path.splitext(image_path.lower())
    supported_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    if ext not in supported_extensions:
        return {
            "error": "validation_failed",
            "message": f"Unsupported file format '{ext}'. Supported formats are: jpg, jpeg, png, webp."
        }

    # Verify minimum resolution and successful decoding
    try:
        with Image.open(image_path) as img:
            img.verify()
        with Image.open(image_path) as img:
            width, height = img.size
            if width < 300 or height < 300:
                return {
                    "error": "validation_failed",
                    "message": f"Image resolution {width}x{height} is below the minimum required 300x300 pixels."
                }
    except Exception as e:
        return {
            "error": "validation_failed",
            "message": f"Failed to decode or verify image: {str(e)}"
        }

    # 2. Caching Logic
    try:
        hasher = hashlib.sha256()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        
        cached_entry = OcrCache.objects.filter(file_hash=file_hash).first()
        if cached_entry:
            logger.info("[Gemini OCR] Using cached OCR")
            return cached_entry.raw_ocr_json
    except Exception as e:
        logger.warning(f"Error checking cached OCR data: {e}")
        file_hash = None

    # 3. Gemini Configuration & Verification
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "error": "backend_error",
            "message": "GEMINI_API_KEY environment variable is missing or empty."
        }

    # Prepare Image Payload
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    except OSError as e:
        return {
            "error": "backend_error",
            "message": f"Failed to read image bytes for API request: {str(e)}"
        }

    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }
    mime_type = mime_types.get(ext, "image/jpeg")

    # Call Gemini API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    prompt_text = (
        "Extract all visible identity information.\n"
        "If both Arabic and English versions of the name exist, return both.\n"
        "Follow these strict rules:\n"
        "- Preserve Arabic exactly as printed.\n"
        "- Preserve English exactly as printed.\n"
        "- Never translate.\n"
        "- Never guess missing values.\n"
        "- Return null if unavailable.\n"
        "- Return JSON only.\n"
        "- No markdown.\n"
        "- No explanations.\n\n"
        "Required Schema:\n"
        "{\n"
        '  "full_name_en": null,\n'
        '  "full_name_ar": null,\n'
        '  "national_id": null,\n'
        '  "date_of_birth": null,\n'
        '  "expiry_date": null,\n'
        '  "country": null,\n'
        '  "document_type": null\n'
        "}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt_text
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": encoded_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    logger.info("[Gemini OCR] Request started")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            return {
                "error": "backend_error",
                "message": f"Gemini API request failed with status code {response.status_code}."
            }
        logger.info("[Gemini OCR] Request completed")
    except requests.exceptions.RequestException as e:
        return {
            "error": "backend_error",
            "message": f"Failed to connect to Gemini API: {str(e)}"
        }

    # Parse and validate response JSON
    try:
        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if not candidates:
            return {
                "error": "backend_error",
                "message": "Gemini API response contained no candidates."
            }
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return {
                "error": "backend_error",
                "message": "Gemini API response candidate contained no parts."
            }

        text = parts[0].get("text", "").strip()
        # Strip potential markdown fences if returned
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                text = "\n".join(lines[1:-1]).strip()

        ocr_data = json.loads(text)
        if file_hash:
            try:
                OcrCache.objects.update_or_create(
                    file_hash=file_hash,
                    defaults={"raw_ocr_json": ocr_data}
                )
            except Exception as cache_err:
                logger.warning(f"Failed to save OCR cache: {cache_err}")
        return ocr_data
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        return {
            "error": "backend_error",
            "message": f"Failed to parse or process Gemini response: {str(e)}"
        }

import os
import logging
import base64
import requests
import json
import hashlib
from esign.models import Document, ContractAnalysis

logger = logging.getLogger(__name__)

def extract_contract_authorization(pdf_path, document=None):
    """
    Extracts representative authorization details from the given PDF contract.
    Utilizes file-hash-based caching in ContractAnalysis to minimize API token usage.
    """
    # 1. Calculate File Hash
    if not os.path.exists(pdf_path):
        return {
            "error": "contract_ocr_failed",
            "message": f"File does not exist: {pdf_path}"
        }

    try:
        hasher = hashlib.sha256()
        with open(pdf_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
    except OSError as e:
        return {
            "error": "contract_ocr_failed",
            "message": f"Failed to calculate file hash: {str(e)}"
        }

    # 2. Check Cache
    try:
        cached_analysis = ContractAnalysis.objects.filter(file_hash=file_hash, provider="gemini").first()
        if cached_analysis and cached_analysis.raw_response:
            logger.info("Contract OCR cache hit")
            return cached_analysis.raw_response
    except Exception as e:
        logger.warning(f"Error checking contract cache: {e}")

    # 3. Gemini Configuration
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("Contract OCR failed")
        return {
            "error": "contract_ocr_failed",
            "message": "GEMINI_API_KEY environment variable is missing or empty."
        }

    # 4. Prepare File Payload
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    except OSError as e:
        logger.info("Contract OCR failed")
        return {
            "error": "contract_ocr_failed",
            "message": f"Failed to read contract bytes: {str(e)}"
        }

    # Determine MIME Type
    _, ext = os.path.splitext(pdf_path.lower())
    if ext == ".pdf":
        mime_type = "application/pdf"
    elif ext in (".jpg", ".jpeg"):
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    else:
        mime_type = "application/pdf"

    # Define strict prompt
    prompt_text = (
        "Read the contract.\n"
        "Find ONLY information required to determine who is authorized to sign.\n"
        "Ignore every other clause.\n"
        "Return JSON only.\n"
        "Follow these strict rules:\n"
        "- Never summarize.\n"
        "- Never explain.\n"
        "- Never translate.\n"
        "- Preserve Arabic exactly.\n"
        "- Preserve English exactly.\n"
        "- Return null if a field cannot be found.\n\n"
        "Required Output Schema:\n"
        "{\n"
        '    "document_language": null,\n'
        '    "representatives": [\n'
        "        {\n"
        '            "name_en": null,\n'
        '            "name_ar": null,\n'
        '            "role": null,\n'
        '            "authority_text": null\n'
        "        }\n"
        "    ]\n"
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
                            "data": encoded_pdf
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

    # Call Gemini API
    logger.info("Contract OCR started")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            logger.info("Contract OCR failed")
            return {
                "error": "contract_ocr_failed",
                "message": f"Gemini API request failed with status code {response.status_code}."
            }
        logger.info("Contract OCR completed")
    except requests.exceptions.RequestException as e:
        logger.info("Contract OCR failed")
        return {
            "error": "contract_ocr_failed",
            "message": f"Failed to connect to Gemini API: {str(e)}"
        }

    # 5. Parse and Validate Response
    try:
        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if not candidates:
            logger.info("Contract OCR failed")
            return {
                "error": "json_parsing_failed",
                "message": "Gemini API response contained no candidates."
            }
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            logger.info("Contract OCR failed")
            return {
                "error": "json_parsing_failed",
                "message": "Gemini API response candidate contained no parts."
            }

        text = parts[0].get("text", "").strip()
        # Strip potential markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                text = "\n".join(lines[1:-1]).strip()

        ocr_data = json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        logger.info("Contract OCR failed")
        return {
            "error": "json_parsing_failed",
            "message": f"Failed to parse or process Gemini response: {str(e)}"
        }

    # 6. Storage in ContractAnalysis
    try:
        # Get or create Document
        doc = document
        if not doc:
            doc = Document.objects.filter(file_hash=file_hash).first()
        if not doc:
            from django.core.files import File
            with open(pdf_path, 'rb') as f:
                django_file = File(f)
                doc = Document.objects.create(
                    file=django_file,
                    file_hash=file_hash
                )

        representatives_list = ocr_data.get("representatives")
        if not isinstance(representatives_list, list):
            representatives_list = []

        # Store in ContractAnalysis table
        ContractAnalysis.objects.update_or_create(
            document=doc,
            file_hash=file_hash,
            provider="gemini",
            defaults={
                "representatives": representatives_list,
                "raw_response": ocr_data
            }
        )
    except Exception as db_err:
        # Fail gracefully on DB saving but still return extracted data
        logger.warning(f"Failed to store contract analysis in DB: {db_err}")

    return ocr_data

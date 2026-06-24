import os
import time
import requests
import logging

logger = logging.getLogger(__name__)

def extract_text_with_azure(pdf_bytes: bytes) -> dict:
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "").strip()
    
    if not endpoint or not key:
        raise ValueError("Azure Document Intelligence credentials are missing or blank.")
        
    # Standardize endpoint
    if not endpoint.startswith("http"):
        endpoint = f"https://{endpoint}"
    endpoint = endpoint.rstrip("/")
    
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/octet-stream"
    }
    
    # Try preferred endpoint first
    url = f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-11-30"
    logger.info(f"Attempting preferred Azure Read model API: {url}")
    
    try:
        response = requests.post(url, headers=headers, data=pdf_bytes, timeout=15)
        if response.status_code == 404:
            url = f"{endpoint}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31"
            logger.info(f"Preferred endpoint returned 404. Falling back to: {url}")
            response = requests.post(url, headers=headers, data=pdf_bytes, timeout=15)
    except requests.exceptions.RequestException as e:
        logger.error(f"Azure OCR POST request connection/network failure: {e}")
        raise
        
    if response.status_code != 202:
        logger.error(f"Azure OCR request failed with status code {response.status_code}: {response.text}")
        raise ValueError(f"Azure OCR request failed with status {response.status_code}: {response.text}")
        
    operation_location = response.headers.get("Operation-Location")
    if not operation_location:
        raise ValueError("Azure OCR response missing Operation-Location header.")
        
    # Polling phase
    poll_headers = {
        "Ocp-Apim-Subscription-Key": key
    }
    
    timeout = 60
    interval = 1
    start_time = time.perf_counter()
    
    result_json = None
    while time.perf_counter() - start_time < timeout:
        time.sleep(interval)
        try:
            poll_resp = requests.get(operation_location, headers=poll_headers, timeout=10)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Connection error during polling: {e}")
            continue
            
        if poll_resp.status_code != 200:
            raise ValueError(f"Azure OCR polling failed with status {poll_resp.status_code}: {poll_resp.text}")
            
        poll_data = poll_resp.json()
        status = poll_data.get("status")
        
        if status == "succeeded":
            result_json = poll_data
            break
        elif status == "failed":
            raise ValueError(f"Azure OCR analysis job failed: {poll_data.get('error', {})}")
            
    if not result_json:
        raise TimeoutError("Azure OCR polling timed out after 60 seconds.")
        
    # Parse Response
    analyze_result = result_json.get("analyzeResult", {})
    raw_text = analyze_result.get("content", "").strip()
    
    # Reconstruct english/arabic text using cleanup functions from ocr_service
    from services.ocr_service import extract_latin_segments, extract_arabic_segments
    english_text = extract_latin_segments(raw_text)
    arabic_text = extract_arabic_segments(raw_text)
    
    pages = analyze_result.get("pages", [])
    page_count = len(pages) if pages else 1
    
    # Calculate average confidence
    confidences = []
    for page in pages:
        for word in page.get("words", []):
            if "confidence" in word:
                confidences.append(word["confidence"])
    average_confidence = sum(confidences) / len(confidences) if confidences else 1.0
    
    # Compatibility metadata
    page_strategies = {i: "azure" for i in range(1, page_count + 1)}
    page_quality_scores = {i: 1.0 for i in range(1, page_count + 1)}
    page_regions = {i: "right" for i in range(1, page_count + 1)}
    
    ocr_ms = (time.perf_counter() - start_time) * 1000
    
    return {
        "raw_text": raw_text,
        "english_text": english_text,
        "arabic_text": arabic_text,
        "ocr_provider": "azure",
        "ocr_confidence": average_confidence,
        "fallback_used": False,
        
        # compatibility fields
        "extraction_source": "azure",
        "dominant_strategy": "azure",
        "extraction_strategy": "azure",
        "page_strategies": page_strategies,
        "page_quality_scores": page_quality_scores,
        "page_regions": page_regions,
        "page_count": page_count,
        "digital_extraction_ms": 0.0,
        "ocr_ms": ocr_ms
    }

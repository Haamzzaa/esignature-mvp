import fitz  # PyMuPDF
import re
import logging
import os

logger = logging.getLogger(__name__)

# Global singleton for OCR engine, lazily loaded
OCR_ENGINE = None

def get_ocr_engine():
    global OCR_ENGINE
    if OCR_ENGINE is None:
        logger.info("Initializing PaddleOCR engine")
        from paddleocr import PaddleOCR
        OCR_ENGINE = PaddleOCR(
            use_angle_cls=True,
            lang="ar",
            show_log=False,
        )
    return OCR_ENGINE

def is_text_sufficient(text: str) -> bool:
    """
    Determines if the extracted text is sufficient or if we should fallback to OCR.
    Criteria:
    * minimum character count (100 characters)
    * alphabetic density (at least 50 letters)
    * printable ratio check (at least 30% of total length are non-whitespace, printable chars)
    """
    if not text:
        return False
    
    # 1. Minimum character count
    if len(text) < 100:
        return False
    
    # 2. Alphabetic density (both English and Arabic letters)
    alphabetic_chars = len(re.findall(r'[a-zA-Z\u0600-\u06FF]', text))
    if alphabetic_chars < 50:
        return False
    
    # 3. Printable ratio check: printable non-whitespace chars / total length
    printable_non_space = len([c for c in text if c.isprintable() and not c.isspace()])
    if len(text) > 0:
        printable_ratio = printable_non_space / len(text)
        if printable_ratio < 0.3:
            return False
            
    return True

def extract_text_with_pymupdf(pdf_bytes: bytes) -> str:
    """
    Extracts raw text from PDF bytes using PyMuPDF (fitz).
    """
    raw_text = ""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_list = []
    for page in doc:
        text_list.append(page.get_text())
    raw_text = "\n".join(text_list).strip()
    doc.close()
    return raw_text

def extract_text_with_paddleocr(pdf_bytes: bytes) -> tuple[str, float]:
    """
    Converts PDF pages into images and runs PaddleOCR on each page.
    """
    import io
    from PIL import Image
    import numpy as np
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_text_list = []
    confidences = []
    ocr = get_ocr_engine()
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap()
        img_bytes = pix.tobytes("png")
        
        img = Image.open(io.BytesIO(img_bytes))
        img_np = np.array(img.convert("RGB"))
        
        result = ocr.ocr(img_np, cls=True)
        if result and result[0]:
            page_lines = []
            for line in result[0]:
                text = line[1][0]
                conf = line[1][1]
                page_lines.append(text)
                confidences.append(conf)
            all_text_list.append(" ".join(page_lines))
            
    doc.close()
    
    combined_text = "\n".join(all_text_list).strip()
    avg_conf = sum(confidences) / len(confidences) if confidences else 1.0
    return combined_text, avg_conf

def extract_text_from_image(image_bytes: bytes) -> tuple[str, float]:
    """
    Processes image bytes directly with PaddleOCR.
    """
    import io
    from PIL import Image
    import numpy as np
    
    ocr = get_ocr_engine()
    img = Image.open(io.BytesIO(image_bytes))
    img_np = np.array(img.convert("RGB"))
    
    result = ocr.ocr(img_np, cls=True)
    text_list = []
    confidences = []
    if result and result[0]:
        for line in result[0]:
            text_list.append(line[1][0])
            confidences.append(line[1][1])
            
    combined_text = " ".join(text_list).strip()
    avg_conf = sum(confidences) / len(confidences) if confidences else 1.0
    return combined_text, avg_conf

def extract_latin_segments(text: str) -> str:
    if not text:
        return ""
    # keeps only Latin letters, digits, punctuation and spaces
    return "".join(re.findall(r'[a-zA-Z0-9\s.,!?;:()\'"\-+=\[\]{}/\\<>#@$%^&*`~|]', text))

def extract_arabic_segments(text: str) -> str:
    if not text:
        return ""
    # keeps only Arabic Unicode ranges, suspicious unicode ranges, and surrounding punctuation/whitespace
    return "".join(re.findall(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u1400-\u16FF\u2200-\u22FF\u2A00-\u2AFF\uE000-\uF8FF\u2300-\u23FF\s.,!?;:()\'"\-+=\[\]{}/\\<>#@$%^&*`~|]', text))


def count_suspicious_unicode(text: str) -> int:
    if not text:
        return 0
    count = 0
    for c in text:
        o = ord(c)
        if (0x1400 <= o <= 0x16FF) or (0x2200 <= o <= 0x22FF) or (0x2A00 <= o <= 0x2AFF) or (0xE000 <= o <= 0xF8FF) or (0x2300 <= o <= 0x23FF):
            count += 1
    return count

def evaluate_english_quality(text: str) -> dict:
    if not text:
        return {
            "score": 0.0,
            "suspicious_unicode_count": 0,
            "suspicious_unicode_detected": False,
            "word_count": 0,
            "char_count": 0,
            "garbage_ratio": 0.0
        }
    suspicious_count = count_suspicious_unicode(text)
    detected = suspicious_count > 5
    
    words = text.split()
    word_count = len([w for w in words if re.search(r'[a-zA-Z]', w)])
    char_count = len(re.findall(r'[a-zA-Z]', text))
    
    garbage_ratio = suspicious_count / len(text) if len(text) > 0 else 0.0
    
    if detected:
        score = 0.0
    else:
        non_space_len = len([c for c in text if not c.isspace()])
        printable_non_space = len([c for c in text if c.isprintable() and not c.isspace()])
        printable_ratio = printable_non_space / non_space_len if non_space_len > 0 else 1.0
        score = printable_ratio * (1.0 - garbage_ratio)
        
    return {
        "score": score,
        "suspicious_unicode_count": suspicious_count,
        "suspicious_unicode_detected": detected,
        "word_count": word_count,
        "char_count": char_count,
        "garbage_ratio": garbage_ratio
    }

def evaluate_arabic_quality(text: str) -> dict:
    if not text:
        return {
            "score": 0.0,
            "suspicious_unicode_count": 0,
            "suspicious_unicode_detected": False,
            "word_count": 0,
            "char_count": 0,
            "arabic_chars": 0,
            "arabic_words": 0,
            "garbage_ratio": 0.0
        }
    suspicious_count = count_suspicious_unicode(text)
    detected = suspicious_count > 5
    
    words = text.split()
    word_count = len([w for w in words if re.search(r'[\u0600-\u06FF]', w)])
    char_count = len(re.findall(r'[\u0600-\u06FF]', text))
    
    garbage_ratio = suspicious_count / len(text) if len(text) > 0 else 0.0
    
    if detected:
        score = 0.0
    else:
        if char_count == 0:
            score = 1.0
        else:
            non_space_len = len([c for c in text if not c.isspace()])
            printable_non_space = len([c for c in text if c.isprintable() and not c.isspace()])
            printable_ratio = printable_non_space / non_space_len if non_space_len > 0 else 1.0
            score = printable_ratio * (1.0 - garbage_ratio)
            
    return {
        "score": score,
        "suspicious_unicode_count": suspicious_count,
        "suspicious_unicode_detected": detected,
        "word_count": word_count,
        "char_count": char_count,
        "arabic_chars": char_count,
        "arabic_words": word_count,
        "garbage_ratio": garbage_ratio
    }

def extract_text_with_paddle(pdf_bytes: bytes, fallback_used: bool = False) -> dict:
    """
    Extracts raw text from PDF bytes using a layout-aware adaptive strategy layer.
    """
    import time
    import io
    from PIL import Image
    import numpy as np
    
    start_time = time.perf_counter()
    
    # Get page count
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
    except Exception as e:
        logger.error(f"Error checking page count: {str(e)}")
        page_count = 1
        doc = None

    digital_extraction_ms = 0.0
    ocr_ms = 0.0
    
    page_strategies = {}
    page_quality_scores = {}
    page_regions = {}
    region_metrics = {}
    page_metadata = []
    
    all_english_text = []
    all_arabic_text = []
    all_confidences = []
    
    left_votes = 0
    right_votes = 0
    
    if doc:
        ocr_engine = None  # Lazily loaded when strategy requires OCR
        
        for page_num in range(page_count):
            page_idx = page_num + 1
            page = doc.load_page(page_num)
            
            # Step 1: Digital extraction
            t_dig_start = time.perf_counter()
            digital_text_page = page.get_text()
            digital_extraction_ms += (time.perf_counter() - t_dig_start) * 1000
            
            # Step 2: Separate English and Arabic Quality Evaluation
            english_text_candidate = extract_latin_segments(digital_text_page)
            arabic_text_candidate = extract_arabic_segments(digital_text_page)
            
            eng_quality = evaluate_english_quality(english_text_candidate)
            ara_quality = evaluate_arabic_quality(arabic_text_candidate)
            page_suspicious_count = count_suspicious_unicode(digital_text_page)
            
            page_quality_scores[page_idx] = ara_quality["score"]
            
            # Step 3: Page-Level Strategy Selection
            if not is_text_sufficient(digital_text_page) or eng_quality["score"] < 0.80:
                strategy = "full_page_ocr"
            elif eng_quality["score"] >= 0.80:
                if ara_quality["char_count"] == 0 and page_suspicious_count <= 5:
                    strategy = "english_only"
                elif page_suspicious_count > 5:
                    strategy = "corrupted_text_layer"
                elif ara_quality["score"] < 0.80:
                    strategy = "hybrid_arabic_replacement"
                else:
                    strategy = "digital_pdf"
            else:
                strategy = "full_page_ocr"
                
            page_strategies[page_idx] = strategy
            
            if page_suspicious_count > 5:
                logger.warning(f"Corrupted Unicode detected on page {page_num}")
            logger.info(f"Using strategy: {strategy}")
            
            # Step 4: Run strategy
            english_text_page = ""
            arabic_text_page = ""
            page_confidence = 1.0
            
            if strategy in ("english_only", "digital_pdf"):
                logger.info(f"Using {strategy} strategy")
                english_text_page = digital_text_page
                arabic_text_page = "" if strategy == "english_only" else digital_text_page
                page_confidence = 1.0
                
                # If digital_pdf, run region checks
                if strategy == "digital_pdf":
                    # Expose region metrics for digital_pdf strategy by checking PyMuPDF text distribution
                    rect = page.rect
                    left_rect = fitz.Rect(0, 0, rect.width / 2, rect.height)
                    right_rect = fitz.Rect(rect.width / 2, 0, rect.width, rect.height)
                    left_text = page.get_text("text", clip=left_rect)
                    right_text = page.get_text("text", clip=right_rect)
                    
                    left_arabic_chars = len(re.findall(r'[\u0600-\u06FF]', left_text))
                    left_density = left_arabic_chars / max(len(left_text), 1)
                    
                    right_arabic_chars = len(re.findall(r'[\u0600-\u06FF]', right_text))
                    right_density = right_arabic_chars / max(len(right_text), 1)
                    
                    selected_region = "left" if left_density > right_density else "right"
                    page_regions[page_idx] = selected_region
                    region_metrics[page_idx] = {
                        "left_arabic_density": left_density,
                        "right_arabic_density": right_density,
                        "selected_region": selected_region
                    }
                    if selected_region == "left":
                        logger.info("Arabic detected on left side")
                        left_votes += 1
                    else:
                        logger.info("Arabic detected on right side")
                        right_votes += 1
                
            elif strategy in ("adaptive_split_ocr", "hybrid_arabic_replacement", "corrupted_text_layer"):
                logger.info(f"Using {strategy} strategy")
                t_ocr_start = time.perf_counter()
                
                if ocr_engine is None:
                    ocr_engine = get_ocr_engine()
                    
                # Render page at 300 DPI
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                image = np.array(img.convert("RGB"))
                height, width, _ = image.shape
                
                # Split image into left and right halves
                left_half = image[:, :width//2]
                right_half = image[:, width//2:]
                
                # Run PaddleOCR on both halves
                left_result = ocr_engine.ocr(left_half, cls=True)
                right_result = ocr_engine.ocr(right_half, cls=True)
                
                left_lines = []
                left_confs = []
                if left_result and left_result[0]:
                    for line in left_result[0]:
                        left_lines.append(line[1][0])
                        left_confs.append(line[1][1])
                left_text = " ".join(left_lines)
                
                right_lines = []
                right_confs = []
                if right_result and right_result[0]:
                    for line in right_result[0]:
                        right_lines.append(line[1][0])
                        right_confs.append(line[1][1])
                right_text = " ".join(right_lines)
                
                # Compute densities
                left_arabic_chars = len(re.findall(r'[\u0600-\u06FF]', left_text))
                left_density = left_arabic_chars / max(len(left_text), 1)
                
                right_arabic_chars = len(re.findall(r'[\u0600-\u06FF]', right_text))
                right_density = right_arabic_chars / max(len(right_text), 1)
                
                if left_density > right_density:
                    logger.info("Arabic detected on left side")
                    left_votes += 1
                    selected_region = "left"
                    arabic_text_page = left_text
                    confs = left_confs
                else:
                    logger.info("Arabic detected on right side")
                    right_votes += 1
                    selected_region = "right"
                    arabic_text_page = right_text
                    confs = right_confs
                    
                page_regions[page_idx] = selected_region
                region_metrics[page_idx] = {
                    "left_arabic_density": left_density,
                    "right_arabic_density": right_density,
                    "selected_region": selected_region
                }
                
                # Preserve healthy digital English
                english_text_page = digital_text_page
                page_confidence = sum(confs) / len(confs) if confs else 1.0
                
                ocr_ms += (time.perf_counter() - t_ocr_start) * 1000
                
            elif strategy == "full_page_ocr":
                logger.info("Using full-page OCR strategy")
                t_ocr_start = time.perf_counter()
                
                if ocr_engine is None:
                    ocr_engine = get_ocr_engine()
                    
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                img_np = np.array(img.convert("RGB"))
                height, width, _ = img_np.shape
                
                result = ocr_engine.ocr(img_np, cls=True)
                
                page_lines = []
                confs = []
                if result and result[0]:
                    for line in result[0]:
                        page_lines.append(line[1][0])
                        confs.append(line[1][1])
                ocr_text = " ".join(page_lines)
                
                arabic_text_page = ocr_text
                english_text_page = digital_text_page if eng_quality["score"] >= 0.80 else ocr_text
                page_confidence = sum(confs) / len(confs) if confs else 1.0
                
                # Expose region metrics for full_page_ocr using line bounding box positions
                left_chars = 0
                right_chars = 0
                left_len = 0
                right_len = 0
                
                if result and result[0]:
                    for line in result[0]:
                        box = line[0]
                        text = line[1][0]
                        x_center = sum(pt[0] for pt in box) / 4
                        arabic_count = len(re.findall(r'[\u0600-\u06FF]', text))
                        
                        if x_center < width / 2:
                            left_chars += arabic_count
                            left_len += len(text)
                        else:
                            right_chars += arabic_count
                            right_len += len(text)
                            
                left_density = left_chars / max(left_len, 1)
                right_density = right_chars / max(right_len, 1)
                
                selected_region = "left" if left_density > right_density else "right"
                page_regions[page_idx] = selected_region
                region_metrics[page_idx] = {
                    "left_arabic_density": left_density,
                    "right_arabic_density": right_density,
                    "selected_region": selected_region
                }
                if selected_region == "left":
                    logger.info("Arabic detected on left side")
                    left_votes += 1
                else:
                    logger.info("Arabic detected on right side")
                    right_votes += 1
                    
                ocr_ms += (time.perf_counter() - t_ocr_start) * 1000
                
            all_english_text.append(english_text_page.strip())
            all_arabic_text.append(arabic_text_page.strip())
            all_confidences.append(page_confidence)
            
            page_metadata.append({
                "page_num": page_idx,
                "strategy": strategy,
                "english_quality_score": eng_quality["score"],
                "arabic_quality_score": ara_quality["score"],
                "suspicious_unicode_count": page_suspicious_count,
                "ocr_confidence": page_confidence
            })
            
        doc.close()
    else:
        page_count = 1
        page_strategies[1] = "full_page_ocr"
        page_quality_scores[1] = 0.0
        all_confidences.append(1.0)
        all_english_text.append("")
        all_arabic_text.append("")
        page_metadata.append({
            "page_num": 1,
            "strategy": "full_page_ocr",
            "english_quality_score": 0.0,
            "arabic_quality_score": 0.0,
            "suspicious_unicode_count": 0,
            "ocr_confidence": 1.0
        })
        
    raw_english = "\n".join(all_english_text).strip()
    raw_arabic = "\n".join(all_arabic_text).strip()
    raw_text = raw_english + "\n" + raw_arabic
    
    ocr_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 1.0
    logger.info(f"Average OCR confidence: {ocr_confidence}")
    
    # Calculate dominant strategy
    strategy_counts = {}
    for s in page_strategies.values():
        strategy_counts[s] = strategy_counts.get(s, 0) + 1
    dominant_strategy = max(strategy_counts, key=strategy_counts.get) if strategy_counts else "full_page_ocr"
    
    # Calculate dominant region
    dominant_arabic_region = "left" if left_votes > right_votes else "right"
    
    languages = []
    if re.search(r'[a-zA-Z]', raw_text):
        languages.append("en")
    if re.search(r'[\u0600-\u06FF]', raw_text):
        languages.append("ar")
        
    # BENCHMARK DEBUG ONLY
    # SAFE TO REMOVE AFTER OCR EVALUATION
    logger.info("PaddleOCR completed successfully.")

    return {
        "raw_text": raw_text,
        "english_text": raw_english,
        "arabic_text": raw_arabic,
        "language_detected": languages,
        "extraction_source": dominant_strategy,
        "extraction_strategy": dominant_strategy,
        "dominant_strategy": dominant_strategy,
        "page_strategies": page_strategies,
        "page_quality_scores": page_quality_scores,
        "dominant_arabic_region": dominant_arabic_region,
        "page_regions": page_regions,
        "region_metrics": region_metrics,
        "ocr_confidence": None,
        "page_count": page_count,
        "digital_extraction_ms": digital_extraction_ms,
        "ocr_ms": ocr_ms,
        "page_metadata": page_metadata,
        "ocr_provider": "paddle",
        "fallback_used": fallback_used
    }

def extract_text_from_pdf(pdf_bytes: bytes) -> dict:
    """
    OCR router that routes PDF processing to either Microsoft Azure Document Intelligence
    or the local PaddleOCR engine based on the OCR_PROVIDER environment variable.
    """
    provider = os.getenv("OCR_PROVIDER", "azure").strip()
    
    # BENCHMARK DEBUG ONLY
    # SAFE TO REMOVE AFTER OCR EVALUATION
    logger.info(f"OCR Provider Requested: {provider}")
    
    if provider == "azure":
        try:
            from services.azure_ocr_service import extract_text_with_azure
            res = extract_text_with_azure(pdf_bytes)
            
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR EVALUATION
            logger.info("Azure OCR completed successfully.")
            logger.info(f"Azure OCR confidence: {res.get('ocr_confidence')}")
            
            return res
        except Exception as e:
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR EVALUATION
            logger.info("Azure OCR failed. Falling back to PaddleOCR.")
            logger.warning(f"Azure OCR failed with error: {e}. Falling back to PaddleOCR.")
            return extract_text_with_paddle(pdf_bytes, fallback_used=True)
            
    return extract_text_with_paddle(pdf_bytes, fallback_used=False)

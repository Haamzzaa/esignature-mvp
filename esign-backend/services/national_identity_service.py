import re
import logging
import datetime
import unicodedata
from django.db import transaction
from django.utils import timezone

from services.azure_ocr_service import extract_text_with_azure
from PIL import Image, ImageOps, ImageEnhance
from io import BytesIO

logger = logging.getLogger(__name__)

# Externalize Enhancement Factors
CONTRAST_FACTOR = 1.3
SHARPNESS_FACTOR = 1.3

def preprocess_identity_image(image_bytes: bytes) -> dict:
    """
    Establish a lightweight, provider-agnostic image preprocessing layer
    that improves OCR quality while preserving auditability and future extensibility.
    Does not mutate the original byte array.
    """
    metadata = {
        "orientation_corrected": False,
        "autocontrast_applied": False,
        "contrast_factor": CONTRAST_FACTOR,
        "sharpness_factor": SHARPNESS_FACTOR,
        "pdf_bypass": False,
        "fallback_used": False
    }

    # 1. PDF Bypass Check
    if image_bytes.startswith(b'%PDF'):
        metadata["pdf_bypass"] = True
        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(
            "Identity Image Preprocessing Debug: Format=PDF, "
            "Dimensions Before=N/A, Dimensions After=N/A, "
            "PDF Bypass=True, Fallback=False"
        )
        return {
            "processed_bytes": image_bytes,
            "metadata": metadata
        }

    try:
        # Avoid mutating the original array by using separate in-memory buffer
        in_buffer = BytesIO(image_bytes)
        with Image.open(in_buffer) as img:
            orig_format = img.format
            orig_size = img.size

            # 1. EXIF orientation correction
            corrected_img = ImageOps.exif_transpose(img)
            
            # Determine if EXIF orientation tag was corrected
            has_orientation = False
            try:
                exif = img.getexif()
                if exif and 274 in exif and exif[274] > 1:
                    has_orientation = True
            except Exception:
                pass

            # 2. Convert to RGB
            rgb_img = corrected_img.convert("RGB")

            # 3. Autocontrast
            autocontrast_img = ImageOps.autocontrast(rgb_img)

            # 4. Contrast enhancement
            contrast_enhancer = ImageEnhance.Contrast(autocontrast_img)
            enhanced_contrast = contrast_enhancer.enhance(CONTRAST_FACTOR)

            # 5. Sharpness enhancement
            sharpness_enhancer = ImageEnhance.Sharpness(enhanced_contrast)
            final_img = sharpness_enhancer.enhance(SHARPNESS_FACTOR)

            final_size = final_img.size

            # Save processed image to a separate in-memory buffer, preserving format
            if orig_format:
                save_format = orig_format.upper()
                if save_format not in ("PNG", "JPEG", "WEBP"):
                    if save_format == "JPG":
                        save_format = "JPEG"
                    else:
                        save_format = "PNG"
            else:
                save_format = "PNG"

            out_buffer = BytesIO()
            final_img.save(out_buffer, format=save_format)
            processed_bytes = out_buffer.getvalue()

            # Clean up resources
            if corrected_img is not img:
                corrected_img.close()
            rgb_img.close()
            if autocontrast_img is not rgb_img:
                autocontrast_img.close()
            enhanced_contrast.close()
            final_img.close()

            metadata["orientation_corrected"] = has_orientation
            metadata["autocontrast_applied"] = True

            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(
                f"Identity Image Preprocessing Debug: Format={orig_format}, "
                f"Dimensions Before={orig_size}, Dimensions After={final_size}, "
                f"PDF Bypass=False, Fallback=False"
            )

            return {
                "processed_bytes": processed_bytes,
                "metadata": metadata
            }

    except Exception as e:
        logger.warning(f"Error during identity image preprocessing: {e}. Falling back to original bytes.")
        metadata["fallback_used"] = True

        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(
            "Identity Image Preprocessing Debug: Format=Unknown, "
            "Dimensions Before=N/A, Dimensions After=N/A, "
            "PDF Bypass=False, Fallback=True"
        )

        return {
            "processed_bytes": image_bytes,
            "metadata": metadata
        }

def extract_identity_data(front_image, back_image=None):
    """
    Runs Azure OCR on the uploaded image file(s).
    Returns a dictionary with raw_text, ocr_confidence, and ocr_provider.
    """
    if not front_image:
        raise ValueError("Front image is required for OCR extraction.")
    
    # Read front image bytes
    front_image.seek(0)
    front_bytes = front_image.read()
    front_image.seek(0)
    
    # Preprocess front ID image
    front_preprocess_res = preprocess_identity_image(front_bytes)
    front_bytes_processed = front_preprocess_res["processed_bytes"]
    
    logger.info(f"Running Azure OCR on front image: {front_image.name}")
    front_res = extract_text_with_azure(front_bytes_processed)
    
    raw_text = front_res.get("raw_text", "")
    ocr_confidence = front_res.get("ocr_confidence")
    ocr_provider = front_res.get("ocr_provider", "azure")
    
    # Process back image if provided
    if back_image:
        back_image.seek(0)
        back_bytes = back_image.read()
        back_image.seek(0)
        
        # Preprocess back ID image
        back_preprocess_res = preprocess_identity_image(back_bytes)
        back_bytes_processed = back_preprocess_res["processed_bytes"]
        
        logger.info(f"Running Azure OCR on back image: {back_image.name}")
        try:
            back_res = extract_text_with_azure(back_bytes_processed)
            back_text = back_res.get("raw_text", "")
            if back_text:
                raw_text = f"{raw_text}\n{back_text}"
            
            back_conf = back_res.get("ocr_confidence")
            if ocr_confidence is not None and back_conf is not None:
                ocr_confidence = (ocr_confidence + back_conf) / 2.0
            elif back_conf is not None:
                ocr_confidence = back_conf
        except Exception as e:
            logger.warning(f"Failed to extract back image OCR: {e}. Continuing with front image only.")

    return {
        "raw_text": raw_text,
        "ocr_confidence": ocr_confidence,
        "ocr_provider": ocr_provider,
    }

def normalize_identity_fields(text):
    """
    Performs:
    * whitespace cleanup
    * Arabic unicode normalization
    * punctuation cleanup
    """
    if not text:
        return ""
    
    # Arabic and general unicode normalization (NFKC)
    normalized = unicodedata.normalize("NFKC", text)
    
    # Arabic character normalization: standardizing alefs, yahs, teh marbutas
    normalized = re.sub(r'[\u0622\u0623\u0625]', '\u0627', normalized)  # آأإ -> ا
    normalized = re.sub(r'\u0649', '\u064a', normalized)  # ى -> ي
    normalized = re.sub(r'\u0629', '\u0647', normalized)  # ة -> ه
    
    # Punctuation cleanup (replace with spaces)
    normalized = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', normalized)
    
    # Whitespace cleanup
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def hijri_to_gregorian(hijri_year, hijri_month, hijri_day):
    """
    Approximates a Hijri date to a Gregorian date for model storage.
    Formula: G = H * 0.97 + 622
    """
    g_year = int(hijri_year * 0.97 + 622)
    g_month = max(1, min(12, hijri_month))
    g_day = max(1, min(31, hijri_day))
    try:
        return datetime.date(g_year, g_month, g_day)
    except ValueError:
        return datetime.date(g_year, g_month, 1)

def extract_dates(text):
    """
    Finds and parses all Gregorian and Hijri date patterns in the text.
    """
    dates = []
    
    # Match YYYY-MM-DD or YYYY/MM/DD
    for m in re.finditer(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', text):
        y, m_val, d = map(int, m.groups())
        dates.append((y, m_val, d))
        
    # Match DD-MM-YYYY or DD/MM/YYYY
    for m in re.finditer(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', text):
        d, m_val, y = map(int, m.groups())
        dates.append((y, m_val, d))
        
    parsed_dates = []
    for y, m_val, d in dates:
        if 1300 <= y <= 1500:  # Hijri range
            parsed_dates.append(hijri_to_gregorian(y, m_val, d))
        elif 1900 <= y <= 2100:  # Gregorian range
            try:
                parsed_dates.append(datetime.date(y, m_val, d))
            except ValueError:
                pass
                
    return sorted(list(set(parsed_dates)))

IGNORE_LIST_ENGLISH = [
    "government of india",
    "kingdom of saudi arabia",
    "ministry of interior",
    "passport",
    "residence permit",
    "saudi national id",
    "national identity card",
    "national identity",
    "identity card",
    "unique identification authority of india",
    "my aadhaar my identity",
    "my aadhaar",
    "issue date",
    "enrollment no",
    "male",
    "female",
]

IGNORE_LIST_LOCAL = [
    "المملكة العربية السعودية",
    "وزارة الداخلية",
    "الهوية الوطنية",
    "إقامة",
    "جواز السفر",
    "سत्यमेव जयते",
    "भारत सरकार",
    "आधार",
    "मेरा आधार",
    "मेरी पहचान",
    "भारतीय विशिष्ट पहचान प्राधिकरण",
    "भारतीय विशिष्ट पहचान",
    "जन्म तिथि",
    "जन्मवर्ष",
]

def is_ignored_name(name_str):
    val = name_str.lower().strip()
    val = unicodedata.normalize("NFKC", val)
    # Standardize Arabic variations
    val = re.sub(r'[\u0622\u0623\u0625]', '\u0627', val)
    val = re.sub(r'\u0649', '\u064a', val)
    val = re.sub(r'\u0629', '\u0647', val)
    
    for eng in IGNORE_LIST_ENGLISH:
        if eng.lower() in val:
            return True
            
    for loc in IGNORE_LIST_LOCAL:
        loc_norm = unicodedata.normalize("NFKC", loc.lower().strip())
        loc_norm = re.sub(r'[\u0622\u0623\u0625]', '\u0627', loc_norm)
        loc_norm = re.sub(r'\u0649', '\u064a', loc_norm)
        loc_norm = re.sub(r'\u0629', '\u0647', loc_norm)
        if loc_norm in val:
            return True
    return False

def clean_candidate_name(line):
    # Strip label prefixes like Name: or الاسم:
    cleaned = re.sub(r'(?i)^(full\s+)?name\s*[:\s-]*\s*', '', line)
    cleaned = re.sub(r'^الاسم(\s+الكامل)?\s*[:\s-]*\s*', '', cleaned)
    cleaned = re.sub(r'^رقم(\s+الإقامة)?\s*[:\s-]*\s*', '', cleaned)
    return cleaned.strip(" :-\t/")

def get_candidate_names(raw_text):
    if not raw_text:
        return []
    
    candidates = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    for line in lines:
        processed_line = line
        dob_match = re.search(r'(?i)(.*?)\b(?:dob|d\.o\.b|yob|birth|जन्म|ولد|تاريخ|ميلاد)[:\s/-]', line)
        if dob_match:
            prefix = dob_match.group(1).strip()
            if prefix:
                processed_line = prefix
        else:
            gender_match = re.search(r'(?i)(.*?)\b(?:male|female|पुरुष|مؤنث|ذكر|أنثى)\b', line)
            if gender_match:
                prefix = gender_match.group(1).strip()
                if prefix:
                    processed_line = prefix

        if re.search(r'\d', processed_line):
            continue
        if is_ignored_name(processed_line):
            continue
        
        cleaned = clean_candidate_name(processed_line)
        if "<" in cleaned:
            continue
        if is_ignored_name(cleaned):
            continue
            
        words = cleaned.split()
        if 1 <= len(words) <= 6:
            candidates.append(cleaned)
            
    return candidates

def get_candidate_identifiers(raw_text):
    if not raw_text:
        return []
        
    candidates = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    for line in lines:
        # Strip spaces and dashes before parsing
        cleaned = re.sub(r'[\s-]', '', line)
        for m in re.finditer(r'\b([a-zA-Z]?\d{7,14})\b', cleaned):
            candidates.append(m.group(1))
            
    return list(set(candidates))

def get_candidate_dates(raw_text):
    temp_normalized = unicodedata.normalize("NFKC", raw_text) if raw_text else ""
    return extract_dates(temp_normalized)

def detect_document_type(raw_text):
    if not raw_text:
        return "unknown"
    
    text_lower = raw_text.lower()
    
    # Aadhaar detection
    if any(x in text_lower for x in ["government of india", "uidai"]) or \
       any(x in raw_text for x in ["भारत सरकार", "आधार"]):
        return "aadhaar"
        
    # Saudi National ID detection
    if any(x in text_lower for x in ["kingdom of saudi arabia", "national identity card", "saudi national id", "saudi id", "national identity"]) or \
       "الهوية الوطنية" in raw_text:
        return "saudi_id"
        
    # Iqama detection
    if "residence permit" in text_lower or "إقامة" in raw_text:
        return "iqama"
        
    # Passport detection
    if "passport" in text_lower or "جواز السفر" in raw_text or "p<" in raw_text:
        return "passport"
        
    return "unknown"

def parse_aadhaar(raw_text):
    # Match pattern \b\d{4}\s\d{4}\s\d{4}\b and normalize spaces
    national_id_number = ""
    match = re.search(r'\b\d{4}\s\d{4}\s\d{4}\b', raw_text)
    if match:
        national_id_number = re.sub(r'\s', '', match.group(0))
    else:
        for line in raw_text.split('\n'):
            cleaned = re.sub(r'[\s-]', '', line)
            m = re.search(r'\b\d{12}\b', cleaned)
            if m:
                national_id_number = m.group(0)
                break

    # DOB extraction: DOB: dd/mm/yyyy
    date_of_birth = None
    dob_match = re.search(r'(?i)dob[:\s]*(\d{1,2})[-/](\d{1,2})[-/](\d{4})', raw_text)
    if dob_match:
        d, m, y = map(int, dob_match.groups())
        try:
            date_of_birth = datetime.date(y, m, d)
        except ValueError:
            pass
    if not date_of_birth:
        dates = get_candidate_dates(raw_text)
        date_of_birth = dates[0] if dates else None

    # Name: Prefer lines above the DOB or gender line, ignoring headers
    full_name = ""
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    dob_idx = -1
    for idx, line in enumerate(lines):
        if any(x in line.lower() for x in ["dob:", "dob", "male", "female", "year of birth"]):
            dob_idx = idx
            break
            
    if dob_idx != -1:
        line_itself = lines[dob_idx]
        dob_match = re.search(r'(?i)(.*?)\b(?:dob|d\.o\.b|yob|birth|जन्म|ولد|تاريخ|ميلاد)[:\s/-]', line_itself)
        if dob_match:
            prefix = dob_match.group(1).strip()
            cleaned_prefix = clean_candidate_name(prefix)
            if cleaned_prefix and not re.search(r'\d', cleaned_prefix) and not is_ignored_name(cleaned_prefix):
                if re.search(r'[a-zA-Z\u0900-\u097F]', cleaned_prefix):
                    words = cleaned_prefix.split()
                    if 1 <= len(words) <= 6:
                        full_name = cleaned_prefix

        if not full_name:
            for offset in range(1, 4):
                candidate_idx = dob_idx - offset
                if candidate_idx >= 0:
                    candidate = lines[candidate_idx]
                    if not is_ignored_name(candidate) and not re.search(r'\d', candidate):
                        if re.search(r'[a-zA-Z\u0900-\u097F]', candidate):
                            full_name = candidate
                            break

    if not full_name:
        candidates = get_candidate_names(raw_text)
        for c in candidates:
            if re.search(r'[a-zA-Z\u0900-\u097F]', c):
                full_name = c
                break

    return {
        "full_name": full_name,
        "national_id_number": national_id_number,
        "date_of_birth": date_of_birth,
        "expiry_date": None,
        "document_type": "aadhaar",
    }

def parse_saudi_id(raw_text):
    # ID starts with 1, 10 digits
    national_id_number = ""
    for line in raw_text.split('\n'):
        cleaned = re.sub(r'[\s-]', '', line)
        m = re.search(r'\b1\d{9}\b', cleaned)
        if m:
            national_id_number = m.group(0)
            break

    dates = get_candidate_dates(raw_text)
    date_of_birth = None
    expiry_date = None
    if len(dates) >= 2:
        date_of_birth = dates[0]
        expiry_date = dates[-1]
    elif len(dates) == 1:
        d = dates[0]
        if d.year < datetime.date.today().year - 10:
            date_of_birth = d
        else:
            expiry_date = d

    # Arabic Names
    candidates = get_candidate_names(raw_text)
    arabic_candidates = [c for c in candidates if re.search(r'[\u0600-\u06FF]', c)]
    full_name = arabic_candidates[0] if arabic_candidates else (candidates[0] if candidates else "")

    return {
        "full_name": full_name,
        "national_id_number": national_id_number,
        "date_of_birth": date_of_birth,
        "expiry_date": expiry_date,
        "document_type": "saudi_id",
    }

def parse_iqama(raw_text):
    # ID starts with 2, 10 digits
    national_id_number = ""
    for line in raw_text.split('\n'):
        cleaned = re.sub(r'[\s-]', '', line)
        m = re.search(r'\b2\d{9}\b', cleaned)
        if m:
            national_id_number = m.group(0)
            break

    dates = get_candidate_dates(raw_text)
    date_of_birth = None
    expiry_date = None
    if len(dates) >= 2:
        date_of_birth = dates[0]
        expiry_date = dates[-1]
    elif len(dates) == 1:
        d = dates[0]
        if d.year < datetime.date.today().year - 10:
            date_of_birth = d
        else:
            expiry_date = d

    # Names
    candidates = get_candidate_names(raw_text)
    arabic_candidates = [c for c in candidates if re.search(r'[\u0600-\u06FF]', c)]
    full_name = arabic_candidates[0] if arabic_candidates else (candidates[0] if candidates else "")

    return {
        "full_name": full_name,
        "national_id_number": national_id_number,
        "date_of_birth": date_of_birth,
        "expiry_date": expiry_date,
        "document_type": "iqama",
    }

def parse_passport(raw_text):
    # TODO Phase 10.x
    # Future phase will implement full MRZ parsing from:
    # P<SAUDI<<NAME<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    
    national_id_number = ""
    for line in raw_text.split('\n'):
        cleaned = re.sub(r'[\s-]', '', line)
        m = re.search(r'\b[A-Za-z]\d{7,9}\b', cleaned)
        if m:
            national_id_number = m.group(0).upper()
            break

    dates = get_candidate_dates(raw_text)
    date_of_birth = None
    expiry_date = None
    if len(dates) >= 2:
        date_of_birth = dates[0]
        expiry_date = dates[-1]
    elif len(dates) == 1:
        d = dates[0]
        if d.year < datetime.date.today().year - 10:
            date_of_birth = d
        else:
            expiry_date = d

    candidates = get_candidate_names(raw_text)
    english_candidates = [c for c in candidates if re.search(r'[a-zA-Z]', c)]
    full_name = english_candidates[0] if english_candidates else (candidates[0] if candidates else "")

    return {
        "full_name": full_name,
        "national_id_number": national_id_number,
        "date_of_birth": date_of_birth,
        "expiry_date": expiry_date,
        "document_type": "passport",
    }

def parse_generic(raw_text):
    candidates = get_candidate_names(raw_text)
    full_name = max(candidates, key=len) if candidates else ""

    candidate_ids = get_candidate_identifiers(raw_text)
    national_id_number = max(candidate_ids, key=len) if candidate_ids else ""

    dates = get_candidate_dates(raw_text)
    date_of_birth = None
    expiry_date = None
    if len(dates) >= 2:
        date_of_birth = dates[0]
        expiry_date = dates[-1]
    elif len(dates) == 1:
        d = dates[0]
        if d.year < datetime.date.today().year - 10:
            date_of_birth = d
        else:
            expiry_date = None

    return {
        "full_name": full_name,
        "national_id_number": national_id_number,
        "date_of_birth": date_of_birth,
        "expiry_date": expiry_date,
        "document_type": "unknown",
    }

def parse_identity_document(raw_text):
    """
    Maps OCR text into structured fields using specialized parsing strategies.
    """
    if not raw_text:
        return {
            "full_name": "",
            "national_id_number": "",
            "date_of_birth": None,
            "expiry_date": None,
            "document_type": "unknown",
        }

    document_type = detect_document_type(raw_text)
    
    if document_type == "aadhaar":
        layout_fields = parse_aadhaar(raw_text)
    elif document_type == "saudi_id":
        layout_fields = parse_saudi_id(raw_text)
    elif document_type == "iqama":
        layout_fields = parse_iqama(raw_text)
    elif document_type == "passport":
        layout_fields = parse_passport(raw_text)
    else:
        layout_fields = parse_generic(raw_text)

    # BENCHMARK DEBUG ONLY
    # SAFE TO REMOVE AFTER OCR TUNING
    from services.identity_candidate_service import (
        generate_name_candidates,
        generate_identifier_candidates,
        generate_date_candidates
    )
    from services.identity_scoring_service import (
        score_name_candidates,
        score_identifier_candidates,
        score_date_candidates
    )
    from services.identity_selection_service import (
        select_best_name_candidate,
        select_best_identifier_candidate,
        select_best_birth_date_candidate,
        select_best_expiry_date_candidate
    )
    name_candidates = generate_name_candidates(raw_text)
    identifier_candidates = generate_identifier_candidates(raw_text)
    date_candidates = generate_date_candidates(raw_text)

    scored_name_candidates = score_name_candidates(name_candidates, raw_text)

    # BENCHMARK DEBUG ONLY — convert to debug log
    for candidate in scored_name_candidates:
        cand_str = candidate.value + ' -> ' + str(candidate.score) + ' | ' + str(candidate.reasons)
        logger.debug("[OCRDebug] Name candidate: %s", cand_str.encode('ascii', 'backslashreplace').decode('ascii'))

    scored_identifier_candidates = score_identifier_candidates(identifier_candidates, raw_text)
    scored_date_candidates = score_date_candidates(date_candidates, raw_text)

    selected_name = select_best_name_candidate(scored_name_candidates)
    selected_identifier = select_best_identifier_candidate(scored_identifier_candidates)
    selected_birth_date = select_best_birth_date_candidate(scored_date_candidates)
    selected_expiry_date = select_best_expiry_date_candidate(scored_date_candidates)

    # Mask selected identifier for logging
    sel_id_val = selected_identifier.value if selected_identifier else None
    masked_sel_id = "*" * max(0, len(sel_id_val) - 4) + sel_id_val[-4:] if sel_id_val else "None"

    def _log_safe(label, val):
        val_str = str(val).encode('ascii', 'backslashreplace').decode('ascii')
        logger.debug("[OCRDebug] %s: %s", label, val_str)

    _log_safe("SELECTED NAME", selected_name.value if selected_name else "None")
    _log_safe("SELECTED IDENTIFIER", masked_sel_id)
    _log_safe("SELECTED BIRTH DATE", selected_birth_date.value if selected_birth_date else "None")
    _log_safe("SELECTED EXPIRY DATE", selected_expiry_date.value if selected_expiry_date else "None")

    from services.identity_confidence_service import (
        calculate_name_confidence,
        calculate_identifier_confidence,
        calculate_birth_date_confidence,
        calculate_expiry_date_confidence,
        calculate_overall_confidence
    )
    
    name_conf = calculate_name_confidence(
        scored_name_candidates,
        selected_name,
        layout_name=layout_fields.get("full_name")
    )
    ident_conf = calculate_identifier_confidence(
        scored_identifier_candidates,
        selected_identifier
    )
    dob_conf = calculate_birth_date_confidence(
        scored_date_candidates,
        selected_birth_date
    )
    exp_conf = calculate_expiry_date_confidence(
        scored_date_candidates,
        selected_expiry_date
    )
    overall_conf = calculate_overall_confidence(
        name_conf,
        ident_conf,
        dob_conf,
        exp_conf
    )

    # Log confidence scores and reasons safely
    _log_safe("NAME CONFIDENCE", name_conf.confidence if selected_name else 0.0)
    _log_safe("REASONS", "\n".join(name_conf.reasons) if selected_name else "no_name_selected")
    
    _log_safe("IDENTIFIER CONFIDENCE", ident_conf.confidence if selected_identifier else 0.0)
    _log_safe("REASONS", "\n".join(ident_conf.reasons) if selected_identifier else "no_identifier_selected")
    
    _log_safe("BIRTH DATE CONFIDENCE", dob_conf.confidence if selected_birth_date else 0.0)
    _log_safe("REASONS", "\n".join(dob_conf.reasons) if selected_birth_date else "no_birth_date_selected")
    
    _log_safe("EXPIRY DATE CONFIDENCE", exp_conf.confidence if exp_conf else "None")
    _log_safe("REASONS", "\n".join(exp_conf.reasons) if exp_conf else "None")
    
    _log_safe("OVERALL CONFIDENCE", overall_conf)

    # Mask identifier values to prevent logging raw PII
    masked_scored_identifiers = []
    for sc in scored_identifier_candidates:
        val = sc.value
        masked_val = "*" * max(0, len(val) - 4) + val[-4:] if val else ""
        masked_scored_identifiers.append({
            "value": masked_val,
            "score": sc.score,
            "reasons": sc.reasons,
            "source_line": sc.source_line
        })

    logger.info(
        f"[BENCHMARK DEBUG ONLY] Candidate Count: Names={len(scored_name_candidates)}, "
        f"Identifiers={len(scored_identifier_candidates)}, Dates={len(scored_date_candidates)}"
    )
    logger.info(f"[BENCHMARK DEBUG ONLY] Scored/Sorted Candidate Names: {scored_name_candidates}")
    logger.info(f"[BENCHMARK DEBUG ONLY] Scored/Sorted Candidate Dates: {scored_date_candidates}")
    logger.info(f"[BENCHMARK DEBUG ONLY] Scored/Sorted Masked Identifiers: {masked_scored_identifiers}")
    
    return {
        "full_name": selected_name.value if selected_name else "",
        "national_id_number": selected_identifier.normalized_value if selected_identifier else "",
        "date_of_birth": datetime.date.fromisoformat(selected_birth_date.value) if selected_birth_date else None,
        "expiry_date": datetime.date.fromisoformat(selected_expiry_date.value) if selected_expiry_date else None,
        "document_type": document_type,
        "confidence": {
            "name": {
                "score": name_conf.confidence if selected_name else 0.0,
                "reasons": name_conf.reasons if selected_name else ["no_name_selected"]
            },
            "identifier": {
                "score": ident_conf.confidence if selected_identifier else 0.0,
                "reasons": ident_conf.reasons if selected_identifier else ["no_identifier_selected"]
            },
            "birth_date": {
                "score": dob_conf.confidence if selected_birth_date else 0.0,
                "reasons": dob_conf.reasons if selected_birth_date else ["no_birth_date_selected"]
            },
            "expiry_date": {
                "score": exp_conf.confidence,
                "reasons": exp_conf.reasons
            } if exp_conf is not None else None,
            "overall": overall_conf
        }
    }



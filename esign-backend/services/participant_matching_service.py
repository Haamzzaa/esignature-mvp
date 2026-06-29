import string
import unicodedata
import difflib
from esign.config import esign_config

def normalize_string(s: str) -> str:
    """
    Normalizes a string for deterministic comparison:
    - Converts to uppercase.
    - Replaces common separators with spaces.
    - Decomposes Unicode characters (NFKD) and discards combining marks (Mn, e.g., accents, tashkeel).
    - Removes punctuation.
    - Strips leading/trailing spaces and collapses multiple internal spaces.
    """
    if not s:
        return ""
    
    # Convert to uppercase
    s = s.upper()
    
    # Replace common separators with spaces
    for sep in ['-', '_', '/', '.']:
        s = s.replace(sep, ' ')
        
    # Normalize Unicode characters (NFKD decomposes base characters + combining marks)
    s = unicodedata.normalize('NFKD', s)
    
    # Remove combining marks (category Mn covers Latin accents and Arabic diacritics/tashkeel)
    s = "".join([c for c in s if unicodedata.category(c) != 'Mn'])
    
    # Remove standard punctuation
    translator = str.maketrans('', '', string.punctuation)
    s = s.translate(translator)
    
    # Trim and collapse spaces
    s = " ".join(s.split())
    
    return s

def check_name_match(participant, parsed_fields) -> dict:
    """
    Calculates name similarity between participant configured name and OCR extracted name.
    """
    participant_name = participant.name or ""
    ocr_name = parsed_fields.get("full_name") or ""
    
    norm_participant = normalize_string(participant_name)
    norm_ocr = normalize_string(ocr_name)
    
    if not norm_participant and not norm_ocr:
        score = 1.0
    elif not norm_participant or not norm_ocr:
        score = 0.0
    else:
        matcher = difflib.SequenceMatcher(None, norm_participant, norm_ocr)
        score = matcher.ratio()
        
    threshold = esign_config.identity_match_threshold
    matched = (score >= threshold)
    
    return {
        "matched": matched,
        "match_score": score,
        "details": {
            "participant_name": participant_name,
            "ocr_name": ocr_name,
            "normalized_participant_name": norm_participant,
            "normalized_ocr_name": norm_ocr,
            "threshold": threshold
        }
    }

def match_participant_identity(participant, parsed_fields) -> dict:
    """
    Main entry point for comparing participant credentials.
    Designed for future extensibility without changing the public caller interface.
    """
    name_match = check_name_match(participant, parsed_fields)
    
    # Future compatibility checks (DOB, ID number, etc.) can be merged here
    matched = name_match["matched"]
    match_score = name_match["match_score"]
    
    return {
        "matched": matched,
        "match_score": match_score,
        "details": {
            "name": name_match
        }
    }

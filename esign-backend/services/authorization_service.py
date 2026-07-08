import re
import unicodedata
import logging
from esign.models import BiometricVerification

logger = logging.getLogger(__name__)

# Constants for English and Arabic honorifics
ENGLISH_HONORIFICS = [
    "Mr", "Mr.", "Mrs", "Mrs.", "Ms", "Ms.", "Miss", "Dr", "Dr.",
    "Prof", "Prof.", "Professor", "Eng", "Eng.", "Engineer",
    "Sheikh", "Shaikh", "His Excellency", "H.E."
]

ARABIC_HONORIFICS = [
    "السيد", "السيدة", "الدكتور", "د", "د.", "المهندس", "م", "م.",
    "الأستاذ", "استاذ", "الشيخ", "سمو", "معالي"
]

def strip_honorifics(name: str) -> str:
    """
    Strips leading English and Arabic honorifics from a name iteratively.
    Also strips common leading separators following the honorifics.
    """
    if not name:
        return ""
    
    separators = ('/', ':', '.', '،', ',', '-')
    current_name = name.strip()
    
    while True:
        stripped_something = False
        
        # 1. Try stripping English honorifics case-insensitively
        for honorific in ENGLISH_HONORIFICS:
            h_len = len(honorific)
            if len(current_name) >= h_len:
                prefix = current_name[:h_len]
                if prefix.lower() == honorific.lower():
                    rest = current_name[h_len:]
                    if not rest or rest[0].isspace() or rest[0] in separators:
                        current_name = rest.strip()
                        while current_name and (current_name[0] in separators or current_name[0].isspace()):
                            current_name = current_name[1:].strip()
                        stripped_something = True
                        break
        
        if stripped_something:
            continue
            
        # 2. Try stripping Arabic honorifics
        for honorific in ARABIC_HONORIFICS:
            h_len = len(honorific)
            if len(current_name) >= h_len:
                prefix = current_name[:h_len]
                if prefix == honorific:
                    rest = current_name[h_len:]
                    if not rest or rest[0].isspace() or rest[0] in separators:
                        current_name = rest.strip()
                        while current_name and (current_name[0] in separators or current_name[0].isspace()):
                            current_name = current_name[1:].strip()
                        stripped_something = True
                        break
                        
        if not stripped_something:
            break
            
    return current_name

def normalize_text(text):
    """
    Normalizes a text string:
    - trim whitespace
    - collapse multiple spaces
    - normalize Arabic Unicode (NFKC + letter variations)
    - remove invisible Unicode characters
    """
    if not text:
        return ""
    
    # Trim whitespace
    s = str(text).strip()
    
    # Remove invisible Unicode characters (category starting with 'C' covers format/control characters)
    s = "".join(c for c in s if not unicodedata.category(c).startswith('C'))
    
    # Normalize Unicode NFKC
    s = unicodedata.normalize("NFKC", s)
    
    # Normalize Arabic character variations
    s = re.sub(r'[\u0622\u0623\u0625]', '\u0627', s)  # آ أ إ -> ا
    s = re.sub(r'\u0649', '\u064a', s)              # ى -> ي
    s = re.sub(r'\u0629', '\u0647', s)              # ة -> ه
    
    # Collapse multiple internal spaces
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def normalize_english(text):
    """
    Normalizes English text (case-insensitive).
    """
    s = normalize_text(text)
    return s.lower()

def normalize_arabic(text):
    """
    Normalizes Arabic text.
    """
    return normalize_text(text)

def authorize_signer(participant, verification, contract_analysis):
    """
    Determines whether the authenticated signer is authorized to sign the contract.
    """
    logger.info("Authorization started")

    # Step 1: Verify identity verification completed successfully
    if not verification or verification.status != "verified":
        logger.info("Authorization failed")
        return {
            "authorized": False,
            "status": "NOT_AUTHORIZED",
            "matched_language": None,
            "matched_representative": None,
            "reason": "Identity verification incomplete."
        }

    # Step 2: Verify biometric comparison passed
    biometric = BiometricVerification.objects.filter(participant=participant).first()
    if not biometric or biometric.status != "matched":
        logger.info("Authorization failed")
        return {
            "authorized": False,
            "status": "NOT_AUTHORIZED",
            "matched_language": None,
            "matched_representative": None,
            "reason": "Face biometric verification failed."
        }

    # Step 3: Verify OCR extracted a valid name
    signer_name_en_raw = (verification.full_name_en or "").strip()
    signer_name_ar_raw = (verification.full_name_ar or "").strip()
    
    signer_name_en = strip_honorifics(signer_name_en_raw)
    signer_name_ar = strip_honorifics(signer_name_ar_raw)
    
    if not signer_name_en and not signer_name_ar:
        logger.info("Authorization failed")
        return {
            "authorized": False,
            "status": "NOT_AUTHORIZED",
            "matched_language": None,
            "matched_representative": None,
            "reason": "Unable to determine signer identity."
        }

    # Step 4: Verify the contract contains at least one representative
    representatives = []
    if contract_analysis and contract_analysis.representatives:
        # Filter invalid/empty representatives once before matching loop
        for rep in contract_analysis.representatives:
            rep_name_en_val = (rep.get("name_en") or "").strip()
            rep_name_ar_val = (rep.get("name_ar") or "").strip()
            if rep_name_en_val or rep_name_ar_val:
                representatives.append(rep)

    if not representatives or len(representatives) == 0:
        logger.info("Manual review required")
        return {
            "authorized": False,
            "status": "MANUAL_REVIEW_REQUIRED",
            "matched_language": None,
            "matched_representative": None,
            "reason": "No representative found in contract."
        }

    # Step 5: Compare signer name against every representative
    norm_signer_en = normalize_english(signer_name_en)
    norm_signer_ar = normalize_arabic(signer_name_ar)

    for rep in representatives:
        rep_name_en_raw = (rep.get("name_en") or "").strip()
        rep_name_ar_raw = (rep.get("name_ar") or "").strip()
        
        rep_name_en = strip_honorifics(rep_name_en_raw)
        rep_name_ar = strip_honorifics(rep_name_ar_raw)

        norm_rep_en = normalize_english(rep_name_en)
        norm_rep_ar = normalize_arabic(rep_name_ar)

        # Compare English with English
        en_matched = False
        if signer_name_en and rep_name_en:
            en_matched = (norm_signer_en == norm_rep_en)

        # Compare Arabic with Arabic
        ar_matched = False
        if signer_name_ar and rep_name_ar:
            ar_matched = (norm_signer_ar == norm_rep_ar)

        if en_matched or ar_matched:
            matched_language = "english" if en_matched else "arabic"
            logger.info("Authorization successful")
            return {
                "authorized": True,
                "status": "AUTHORIZED",
                "matched_language": matched_language,
                "matched_representative": {
                    "name_en": rep.get("name_en"),
                    "name_ar": rep.get("name_ar"),
                    "role": rep.get("role"),
                    "signature_label": rep.get("signature_label"),
                    "authority_text": rep.get("authority_text")
                },
                "reason": None
            }

    # Step 6: If no representative matches
    logger.info("Authorization failed")
    return {
        "authorized": False,
        "status": "NOT_AUTHORIZED",
        "matched_language": None,
        "matched_representative": None,
        "reason": "Authenticated signer is not listed as an authorized representative."
    }

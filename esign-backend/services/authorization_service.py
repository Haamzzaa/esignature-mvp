import re
import unicodedata
import logging
from esign.models import BiometricVerification

logger = logging.getLogger(__name__)

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
    signer_name_en = (verification.full_name_en or "").strip()
    signer_name_ar = (verification.full_name_ar or "").strip()
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
        representatives = contract_analysis.representatives

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
        rep_name_en = (rep.get("name_en") or "").strip()
        rep_name_ar = (rep.get("name_ar") or "").strip()

        # Compare English with English
        en_matched = False
        if signer_name_en and rep_name_en:
            en_matched = (norm_signer_en == normalize_english(rep_name_en))

        # Compare Arabic with Arabic
        ar_matched = False
        if signer_name_ar and rep_name_ar:
            ar_matched = (norm_signer_ar == normalize_arabic(rep_name_ar))

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

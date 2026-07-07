import logging
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import transaction
from esign.models import SignerIdentityVerification
from services.gemini_ocr_service import extract_identity_data, parse_date
from services.reference_face_service import extract_reference_face

logger = logging.getLogger(__name__)

def perform_identity_verification(participant, document_image_bytes):
    """
    Performs identity verification for a participant:
    1. Store document image.
    2. Execute existing OCR pipeline.
    3. Extract the face image from the ID card using reference_face_service.
    4. Populate details.
    5. Set status="verified" or "requires_manual_review" on exceptions.
    """
    from esign.timing import timed_operation

    logger.info("[IdentityVerification] Starting: participant_id=%s", participant.id)

    with transaction.atomic():
        # Get or create the verification object
        verification, created = SignerIdentityVerification.objects.get_or_create(
            participant=participant,
        )

    # Store document image
    verification.document_image.save(
        f"doc_{participant.id}.jpg",
        ContentFile(document_image_bytes),
        save=False
    )

    try:
        # Execute Gemini OCR extraction
        with timed_operation("identity_ocr_extraction", logger, participant_id=participant.id):
            ocr_result = extract_identity_data(verification.document_image.path)
        
        if "error" in ocr_result:
            raise ValueError(ocr_result["message"])

        # Populate verification model fields
        verification.raw_ocr_json = ocr_result
        verification.ocr_provider = "gemini"
        
        full_name_en = ocr_result.get("full_name_en") or ""
        full_name_ar = ocr_result.get("full_name_ar") or ""
        
        # Backward compatibility fallback for older cached OCR results
        if not full_name_en and not full_name_ar and "full_name" in ocr_result:
            old_name = ocr_result.get("full_name") or ""
            if any('\u0600' <= char <= '\u06FF' for char in old_name):
                full_name_ar = old_name
            else:
                full_name_en = old_name

        verification.full_name_en = full_name_en
        verification.full_name_ar = full_name_ar

        # Select full_name based on presence of Arabic characters in participant's registered name
        participant_name = participant.name or ""
        has_arabic = any('\u0600' <= char <= '\u06FF' for char in participant_name)
        if has_arabic:
            verification.full_name = full_name_ar or full_name_en
        else:
            verification.full_name = full_name_en or full_name_ar

        verification.national_id_number = ocr_result.get("national_id") or ""
        verification.date_of_birth = parse_date(ocr_result.get("date_of_birth"))
        verification.expiry_date = parse_date(ocr_result.get("expiry_date"))
        verification.country = ocr_result.get("country") or ""
        verification.document_type = ocr_result.get("document_type") or "unknown"

        # Build parsed_fields for matching and downstream tasks
        parsed_fields = {
            "full_name": verification.full_name,
            "national_id_number": verification.national_id_number,
            "date_of_birth": verification.date_of_birth,
            "expiry_date": verification.expiry_date,
            "country": verification.country,
            "document_type": verification.document_type,
        }

        # Check identity matching
        from services.participant_matching_service import match_participant_identity
        with timed_operation("identity_matching", logger, participant_id=participant.id):
            match_res = match_participant_identity(participant, parsed_fields)

        verification.identity_match_score = match_res["match_score"]
        verification.identity_matched = match_res["matched"]

        logger.info(
            "[IdentityVerification] Match result: participant_id=%s matched=%s score=%.4f",
            participant.id, match_res["matched"], match_res.get("match_score", 0)
        )

        if not match_res["matched"]:
            verification.status = "requires_manual_review"
            verification.failure_reason = "identity_name_mismatch"
        else:
            # Extract the face from the ID card using reference_face_service
            with timed_operation("reference_face_extraction", logger, participant_id=participant.id):
                reference_face_bytes = extract_reference_face(document_image_bytes)

            # Save reference face image
            verification.reference_face_image.save(
                f"face_{participant.id}.jpg",
                ContentFile(reference_face_bytes),
                save=False
            )

            verification.status = "verified"
            verification.failure_reason = ""
            logger.info("[IdentityVerification] Verified: participant_id=%s", participant.id)
            from esign.models import AuditLog
            AuditLog.objects.create(
                envelope=participant.envelope,
                event="Identity verified"
            )

    except Exception as e:
        logger.exception("[IdentityVerification] Failed: participant_id=%s", participant.id)
        verification.status = "requires_manual_review"
        verification.failure_reason = str(e)

    verification.save()
    return verification

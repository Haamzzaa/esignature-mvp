import logging
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import transaction
from esign.models import SignerIdentityVerification
from services.national_identity_service import extract_identity_data, parse_identity_document
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
        # Wrap image bytes in a BytesIO file-like object for OCR extraction
        document_file = BytesIO(document_image_bytes)
        document_file.name = "document.jpg"

        # Execute existing OCR pipeline
        with timed_operation("identity_ocr_extraction", logger, participant_id=participant.id):
            ocr_result = extract_identity_data(document_file)
        raw_text = ocr_result.get("raw_text", "")
        parsed_fields = parse_identity_document(raw_text)

        verification.full_name = parsed_fields.get("full_name", "")
        verification.national_id_number = parsed_fields.get("national_id_number", "")
        verification.date_of_birth = parsed_fields.get("date_of_birth")
        verification.document_type = parsed_fields.get("document_type", "unknown")

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

    except Exception as e:
        logger.exception("[IdentityVerification] Failed: participant_id=%s", participant.id)
        verification.status = "requires_manual_review"
        verification.failure_reason = str(e)

    verification.save()
    return verification

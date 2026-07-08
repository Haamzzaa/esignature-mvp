import logging
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import transaction
from esign.models import SignerIdentityVerification
from services.gemini_ocr_service import extract_identity_data, parse_date
from services.reference_face_service import extract_reference_face

logger = logging.getLogger(__name__)

def perform_identity_verification(participant, document_image_bytes):
    from esign.timing import timed_operation
    import time
    t_total_start = time.perf_counter()

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
            import cv2
            import numpy as np
            from services.enterprise_biometric_service import get_face_analysis_app, align_and_crop, generate_embedding
            
            # 1. Load ID image
            t_load_start = time.perf_counter()
            nparr = np.frombuffer(document_image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            t_load_ms = int((time.perf_counter() - t_load_start) * 1000)
            logger.info("[Timing] Load ID image completed in %dms", t_load_ms)

            # 2. Face model initialization
            t_init_start = time.perf_counter()
            app = get_face_analysis_app()
            t_init_ms = int((time.perf_counter() - t_init_start) * 1000)
            logger.info("[Timing] Face model initialization completed in %dms", t_init_ms)

            # 3. Face detection
            t_det_start = time.perf_counter()
            faces = app.get(img)
            t_det_ms = int((time.perf_counter() - t_det_start) * 1000)
            logger.info("[Timing] Face detection completed in %dms", t_det_ms)

            if not faces:
                raise ValueError("no_face_detected")
            face = faces[0]

            # 4. Face alignment
            t_align_start = time.perf_counter()
            aligned_face = align_and_crop(img, face)
            t_align_ms = int((time.perf_counter() - t_align_start) * 1000)
            logger.info("[Timing] Face alignment completed in %dms", t_align_ms)

            # 5. Face embedding generation
            t_emb_start = time.perf_counter()
            emb = generate_embedding(face)
            t_emb_ms = int((time.perf_counter() - t_emb_start) * 1000)
            logger.info("[Timing] Face embedding generation completed in %dms", t_emb_ms)

            # Crop the reference face using the standard logic
            bbox = face.bbox
            h_img, w_img, _ = img.shape
            x1 = max(0, int(bbox[0] - 0.25 * (bbox[2] - bbox[0])))
            y1 = max(0, int(bbox[1] - 0.25 * (bbox[3] - bbox[1])))
            x2 = min(w_img, int(bbox[2] + 0.25 * (bbox[2] - bbox[0])))
            y2 = min(h_img, int(bbox[3] + 0.25 * (bbox[3] - bbox[1])))
            cropped_face = img[y1:y2, x1:x2]
            success, face_barr = cv2.imencode('.jpg', cropped_face)
            if not success:
                raise ValueError("Failed to encode cropped face to JPEG format.")
            reference_face_bytes = face_barr.tobytes()

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

    # 6. Database save
    t_db_start = time.perf_counter()
    verification.save()
    t_db_ms = int((time.perf_counter() - t_db_start) * 1000)
    logger.info("[Timing] Database save completed in %dms", t_db_ms)

    # Total verification time
    t_total_ms = int((time.perf_counter() - t_total_start) * 1000)
    logger.info("[Timing] Total verification time completed in %dms", t_total_ms)

    return verification

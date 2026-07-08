import logging
import numpy as np
import cv2
from esign.config import esign_config
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

from services.enterprise_biometric_service import get_face_analysis_app

def extract_face_embedding(image_bytes):
    """
    Parses the image bytes and extracts the ArcFace embedding of the first detected face.
    Raises ValueError("no_face_detected") if no face is detected.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes.")

    app = get_face_analysis_app()
    faces = app.get(img)
    if not faces:
        raise ValueError("no_face_detected")

    return faces[0].normed_embedding

def calculate_face_similarity(reference_image_bytes, selfie_image_bytes):
    """
    Detects faces from both images and computes their cosine similarity.
    """
    emb1 = extract_face_embedding(reference_image_bytes)
    emb2 = extract_face_embedding(selfie_image_bytes)

    dot_product = np.dot(emb1, emb2)
    norm_a = np.linalg.norm(emb1)
    norm_b = np.linalg.norm(emb2)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))

def perform_face_match(participant, selfie_image_bytes):
    """
    Runs face verification workflow, updating state in BiometricVerification.
    Retrieves the reference face image from signer_identity_verification dynamically.
    """
    from services.biometric_verification_service import (
        mark_biometric_processing,
        mark_biometric_matched,
        mark_biometric_failed,
        mark_biometric_manual_review
    )
    from esign.providers.registry import esign_provider_registry
    from esign.timing import timed_operation

    logger.info("[FaceMatch] Starting face match: participant_id=%s", participant.id)
    mark_biometric_processing(participant)

    try:
        has_verification = hasattr(participant, "signer_identity_verification") and participant.signer_identity_verification is not None
        if not has_verification:
            logger.warning("[FaceMatch] No identity verification found: participant_id=%s", participant.id)
            return mark_biometric_manual_review(
                participant,
                reason="Signer identity verification does not exist for this participant."
            )

        verification = participant.signer_identity_verification
        if not verification.reference_face_image:
            logger.warning("[FaceMatch] No reference face image: participant_id=%s", participant.id)
            return mark_biometric_manual_review(
                participant,
                reason="No reference face image found on participant's identity verification."
            )

        verification.reference_face_image.open('rb')
        reference_image_bytes = verification.reference_face_image.read()
        verification.reference_face_image.close()

    except Exception as e:
        logger.error("[FaceMatch] Failed to retrieve reference face: participant_id=%s error=%s", participant.id, str(e))
        return mark_biometric_manual_review(
            participant,
            reason=f"Failed to retrieve reference face: {str(e)}"
        )

    try:
        with timed_operation("face_similarity", logger, participant_id=participant.id):
            score = esign_provider_registry.face_provider.calculate_similarity(reference_image_bytes, selfie_image_bytes)
        threshold = esign_config.face_match_threshold

        logger.info(
            "[FaceMatch] Similarity result: participant_id=%s score=%.4f threshold=%.4f matched=%s",
            participant.id, score, threshold, score >= threshold
        )

        if score >= threshold:
            with timed_operation("liveness_check", logger, participant_id=participant.id):
                liveness = esign_provider_registry.liveness_provider.check_liveness(selfie_image_bytes)
            if not liveness.passed:
                logger.info("[FaceMatch] Liveness failed: participant_id=%s reason=%s", participant.id, liveness.reason)
                return mark_biometric_manual_review(
                    participant,
                    reason=liveness.reason or "liveness_failed"
                )

            logger.info("[FaceMatch] Match succeeded: participant_id=%s score=%.4f", participant.id, score)
            return mark_biometric_matched(
                participant,
                similarity_score=score,
                liveness_score=liveness.score,
                provider="insightface"
            )
        else:
            logger.info("[FaceMatch] Match failed: participant_id=%s score=%.4f below threshold=%.4f", participant.id, score, threshold)
            return mark_biometric_failed(
                participant,
                reason="similarity_below_threshold",
                similarity_score=score
            )
    except ValueError as e:
        if str(e) == "no_face_detected":
            logger.warning("[FaceMatch] No face detected in image: participant_id=%s", participant.id)
            return mark_biometric_manual_review(
                participant,
                reason="no_face_detected"
            )
        logger.error("[FaceMatch] ValueError: participant_id=%s error=%s", participant.id, str(e))
        return mark_biometric_manual_review(
            participant,
            reason=str(e)
        )
    except Exception as e:
        logger.error("[FaceMatch] Unexpected error: participant_id=%s error=%s", participant.id, str(e))
        return mark_biometric_manual_review(
            participant,
            reason=str(e)
        )

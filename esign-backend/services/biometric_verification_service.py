from django.utils import timezone
from django.db import transaction
from esign.models import BiometricVerification
from services.verification_session_service import get_or_create_verification_session

def get_or_create_biometric_verification(participant):
    """
    Gets or creates a BiometricVerification instance for the given participant.
    """
    with transaction.atomic():
        session = get_or_create_verification_session(participant)
        biometric, created = BiometricVerification.objects.get_or_create(
            participant=participant,
            defaults={"verification_session": session}
        )
    return biometric

def mark_biometric_processing(participant):
    """
    Sets status="processing" on the biometric verification.
    """
    with transaction.atomic():
        biometric = get_or_create_biometric_verification(participant)
        biometric.status = "processing"
        biometric.save(update_fields=["status"])
    return biometric

def mark_biometric_matched(participant, similarity_score=None, liveness_score=None, provider=""):
    """
    Sets status="matched", similarity_score, liveness_score, provider, and completed_at.
    """
    with transaction.atomic():
        biometric = get_or_create_biometric_verification(participant)
        biometric.status = "matched"
        biometric.similarity_score = similarity_score
        biometric.liveness_score = liveness_score
        biometric.provider = provider
        biometric.completed_at = timezone.now()
        biometric.save(update_fields=["status", "similarity_score", "liveness_score", "provider", "completed_at"])

        from esign.models import AuditLog
        AuditLog.objects.create(
            envelope=participant.envelope,
            event="Face verified"
        )
    return biometric

def mark_biometric_failed(participant, reason="", similarity_score=None):
    """
    Sets status="failed", failure_reason=reason, and completed_at.
    """
    with transaction.atomic():
        biometric = get_or_create_biometric_verification(participant)
        biometric.status = "failed"
        biometric.failure_reason = reason
        if similarity_score is not None:
            biometric.similarity_score = similarity_score
        biometric.completed_at = timezone.now()
        biometric.save(update_fields=["status", "failure_reason", "similarity_score", "completed_at"])
    return biometric

def mark_biometric_manual_review(participant, reason=""):
    """
    Sets status="requires_manual_review", failure_reason=reason, and completed_at.
    """
    with transaction.atomic():
        biometric = get_or_create_biometric_verification(participant)
        biometric.status = "requires_manual_review"
        biometric.failure_reason = reason
        biometric.completed_at = timezone.now()
        biometric.save(update_fields=["status", "failure_reason", "completed_at"])
    return biometric

from django.utils import timezone
from django.db import transaction
from esign.models import VerificationSession

def get_or_create_verification_session(participant):
    """
    Retrieves the existing VerificationSession for the given participant,
    or creates one with status="pending" if it does not exist.
    """
    with transaction.atomic():
        session, created = VerificationSession.objects.get_or_create(
            participant=participant
        )
    return session

def mark_verification_processing(participant):
    """
    Transitions the verification session status to "processing".
    """
    with transaction.atomic():
        session = get_or_create_verification_session(participant)
        session.status = "processing"
        session.save(update_fields=["status"])
    return session

def mark_verification_approved(participant):
    """
    Transitions the verification session status to "approved" and sets completed_at.
    """
    with transaction.atomic():
        session = get_or_create_verification_session(participant)
        session.status = "approved"
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at"])
    return session

def mark_verification_failed(participant, reason=""):
    """
    Transitions the verification session status to "failed", stores the failure reason,
    and sets completed_at.
    """
    with transaction.atomic():
        session = get_or_create_verification_session(participant)
        session.status = "failed"
        session.failure_reason = reason
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "failure_reason", "completed_at"])
    return session

def mark_verification_manual_review(participant, reason=""):
    """
    Transitions the verification session status to "requires_manual_review",
    stores the failure reason, and sets completed_at.
    """
    with transaction.atomic():
        session = get_or_create_verification_session(participant)
        session.status = "requires_manual_review"
        session.failure_reason = reason
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "failure_reason", "completed_at"])
    return session

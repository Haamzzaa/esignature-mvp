from django.utils import timezone
from django.db import transaction
from esign.models import ParticipantAuthorizationState


def accept_terms(participant, terms_version="v1"):
    """
    Records that the participant has accepted the Terms & Conditions.

    Creates or updates ParticipantAuthorizationState atomically.
    Sets accepted_terms=True, accepted_terms_at=now(), and terms_version.

    Returns the updated ParticipantAuthorizationState instance.
    """
    with transaction.atomic():
        state, _ = ParticipantAuthorizationState.objects.get_or_create(
            participant=participant
        )
        state.accepted_terms = True
        state.accepted_terms_at = timezone.now()
        state.terms_version = terms_version
        state.save(update_fields=["accepted_terms", "accepted_terms_at", "terms_version", "updated_at"])
    return state

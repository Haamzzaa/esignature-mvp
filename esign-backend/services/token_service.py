from django.utils import timezone
from esign.models import ParticipantToken, SigningToken, Participant, Signer

class TokenContext:
    def __init__(self, participant_token, participant, envelope, legacy_signing_token=None):
        self.participant_token = participant_token
        self.participant = participant
        self.envelope = envelope
        self.legacy_signing_token = legacy_signing_token

def resolve_token(token_str, allow_used=False):
    """
    Resolves token_str to a tuple (token_obj, error_msg).
    This preserves the interface expected by handle_token_error/views.
    It queries ParticipantToken first, falling back to legacy SigningToken.
    """
    import uuid
    try:
        uuid.UUID(str(token_str))
    except ValueError:
        return None, "Invalid token."

    # 1. Look up ParticipantToken
    pt = ParticipantToken.objects.filter(token=token_str).first()
    if pt:
        if not allow_used:
            if pt.participant.envelope.status == "completed":
                return None, "This package has already been completed."
            if pt.participant.has_completed or pt.participant.status in ('completed', 'declined', 'returned'):
                return None, "Your step has already been completed."
            if pt.is_used:
                return None, "Your step has already been completed."
            if pt.expires_at < timezone.now():
                return None, "This signing link has expired."
        return pt, None

    # 2. Look up legacy SigningToken
    st = SigningToken.objects.filter(token=token_str).first()
    if st:
        if not allow_used:
            if st.signer.envelope.status == "completed":
                return None, "This package has already been completed."
            if st.is_used:
                return None, "Your step has already been completed."
            if st.expires_at < timezone.now():
                return None, "This signing link has expired."
        return st, None

    return None, "Invalid token."

def get_token_context(token_str, allow_used=False):
    """
    Resolves token_str to a TokenContext object.
    Raises a ValueError with the error message if validation fails.
    """
    token_obj, error_msg = resolve_token(token_str, allow_used)
    if error_msg:
        raise ValueError(error_msg)

    if isinstance(token_obj, ParticipantToken):
        return TokenContext(
            participant_token=token_obj,
            participant=token_obj.participant,
            envelope=token_obj.participant.envelope,
            legacy_signing_token=None
        )
    elif isinstance(token_obj, SigningToken):
        signer = token_obj.signer
        envelope = signer.envelope
        # Resolve the corresponding participant using invariant (by email)
        participant = envelope.participants.filter(email=signer.email).first()
        # Fallback safety (if invariant is somehow not populated, pick the first signer)
        if not participant:
            participant = envelope.participants.filter(role="signer").first() or envelope.participants.first()
        
        pt = None
        if participant:
            try:
                pt = participant.token
            except ParticipantToken.DoesNotExist:
                pt = None

        return TokenContext(
            participant_token=pt,
            participant=participant,
            envelope=envelope,
            legacy_signing_token=token_obj
        )
    
    raise ValueError("Invalid token.")

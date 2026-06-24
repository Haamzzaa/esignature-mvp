import random
import string
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.db import transaction

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10


def generate_email_otp():
    """
    Generates a random 6-digit numeric OTP string.
    """
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def send_email_otp(participant):
    """
    Generates a new OTP, stores it on ParticipantAuthorizationState,
    and dispatches it to the participant's email address via Django's
    configured email backend.

    Returns the ParticipantAuthorizationState instance after saving.
    """
    from esign.models import ParticipantAuthorizationState

    otp = generate_email_otp()
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    with transaction.atomic():
        state, _ = ParticipantAuthorizationState.objects.get_or_create(
            participant=participant
        )
        state.email_otp_code = otp
        state.email_otp_sent_at = now
        state.email_otp_expires_at = expires_at
        # Reset any prior verification when a new OTP is issued
        state.email_verified = False
        state.email_verified_at = None
        state.save(update_fields=[
            "email_otp_code",
            "email_otp_sent_at",
            "email_otp_expires_at",
            "email_verified",
            "email_verified_at",
            "updated_at",
        ])

    send_mail(
        subject="Your verification code",
        message=(
            f"Hi {participant.name},\n\n"
            f"Your one-time verification code is: {otp}\n\n"
            f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"If you did not request this code, please ignore this email."
        ),
        from_email=None,  # uses DEFAULT_FROM_EMAIL from settings
        recipient_list=[participant.email],
        fail_silently=False,
    )

    return state


def verify_email_otp(participant, otp):
    """
    Verifies the supplied OTP against the stored code for the participant.

    Returns a dict:
        {"verified": True}                           — on success
        {"verified": False, "error": "Invalid OTP"}  — wrong code
        {"verified": False, "error": "OTP expired"}  — expired code
        {"verified": False, "error": "No OTP sent"}  — no code on record
    """
    from esign.models import ParticipantAuthorizationState

    try:
        state = ParticipantAuthorizationState.objects.get(participant=participant)
    except ParticipantAuthorizationState.DoesNotExist:
        return {"verified": False, "error": "No OTP sent"}

    if not state.email_otp_code:
        return {"verified": False, "error": "No OTP sent"}

    if timezone.now() > state.email_otp_expires_at:
        return {"verified": False, "error": "OTP expired"}

    if otp != state.email_otp_code:
        return {"verified": False, "error": "Invalid OTP"}

    # Success — mark verified and clear the code
    with transaction.atomic():
        state.email_verified = True
        state.email_verified_at = timezone.now()
        state.email_otp_code = ""
        state.save(update_fields=[
            "email_verified",
            "email_verified_at",
            "email_otp_code",
            "updated_at",
        ])

    return {"verified": True}

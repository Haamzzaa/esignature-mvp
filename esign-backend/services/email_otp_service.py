import hashlib
import logging
import secrets
import string
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from esign.config import esign_config

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = esign_config.otp_expiry


class EmailDeliveryError(Exception):
    """Raised when OTP email delivery fails after retries."""
    pass


def generate_email_otp():
    """
    Generates a cryptographically secure random 6-digit numeric OTP string.
    """
    return "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))


def _deliver_otp_email(recipient_email, recipient_name, otp):
    """
    Transports the OTP verification email to the recipient with bounded retries
    for transient transport failures.
    Never logs the plaintext OTP or credentials.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com") or esign_config.default_from_email
    subject = "Your verification code"
    body = (
        f"Hi {recipient_name},\n\n"
        f"Your one-time verification code is: {otp}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If you did not request this code, please ignore this email."
    )

    max_attempts = 3
    backoff_delay = 0.2

    for attempt in range(1, max_attempts + 1):
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            logger.info(
                "[EmailOTP] Verification code email delivered successfully to %s (attempt %d/%d)",
                recipient_email, attempt, max_attempts
            )
            return True
        except Exception as exc:
            logger.warning(
                "[EmailOTP] Transport attempt %d/%d failed for %s: %s",
                attempt, max_attempts, recipient_email, exc.__class__.__name__
            )
            if attempt < max_attempts:
                time.sleep(backoff_delay * (2 ** (attempt - 1)))
            else:
                logger.error(
                    "[EmailOTP] All %d transport attempts failed for recipient %s",
                    max_attempts, recipient_email
                )
                raise EmailDeliveryError("Failed to deliver verification code email after retries.") from exc


def send_email_otp(participant):
    """
    Generates a new OTP, stores it securely on ParticipantAuthorizationState,
    and dispatches it to the participant's email address via Django's
    configured email backend with delivery retry.

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
        otp_hash = hashlib.sha256(otp.encode('utf-8')).hexdigest()
        state.email_otp_code = otp_hash
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

    _deliver_otp_email(participant.email, participant.name, otp)

    return state


def verify_email_otp(participant, otp):
    """
    Verifies the supplied OTP against the stored code for the participant,
    protecting against concurrent race conditions using atomic select_for_update.

    Returns a dict:
        {"verified": True}                           — on success
        {"verified": False, "error": "Invalid OTP"}  — wrong code
        {"verified": False, "error": "OTP expired"}  — expired code
        {"verified": False, "error": "No OTP sent"}  — no code on record
    """
    from esign.models import ParticipantAuthorizationState

    with transaction.atomic():
        try:
            # Query and acquire row-lock to prevent race conditions
            state = ParticipantAuthorizationState.objects.select_for_update().get(participant=participant)
        except ParticipantAuthorizationState.DoesNotExist:
            return {"verified": False, "error": "No OTP sent"}

        if not state.email_otp_code:
            return {"verified": False, "error": "No OTP sent"}

        if timezone.now() > state.email_otp_expires_at:
            # Invalidate expired code immediately
            state.email_otp_code = ""
            state.save(update_fields=["email_otp_code", "updated_at"])
            return {"verified": False, "error": "OTP expired"}

        input_hash = hashlib.sha256(str(otp).encode('utf-8')).hexdigest()
        if input_hash != state.email_otp_code:
            return {"verified": False, "error": "Invalid OTP"}

        # Success — mark verified and immediately invalidate the code to prevent replay
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

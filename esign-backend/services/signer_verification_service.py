import logging
from django.db import transaction
from django.utils import timezone
from esign.models import SignerVerification, VerificationEvent
from esign.constants import (
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_ID_UPLOADED,
    VERIFICATION_STATUS_SELFIE_UPLOADED,
    VERIFICATION_STATUS_UNDER_REVIEW,
    VERIFICATION_STATUS_VERIFIED,
    VERIFICATION_STATUS_FAILED,
    VERIFICATION_METHOD_INTERNAL,
    EVENT_ID_FRONT_UPLOADED,
    EVENT_ID_BACK_UPLOADED,
    EVENT_SELFIE_UPLOADED,
    EVENT_VERIFICATION_STARTED,
    EVENT_VERIFICATION_COMPLETED,
    EVENT_VERIFICATION_FAILED,
)

logger = logging.getLogger(__name__)

def create_verification(participant, method=VERIFICATION_METHOD_INTERNAL):
    """
    Creates a SignerVerification record for a participant if missing.
    Returns (verification_obj, created)
    """
    return SignerVerification.objects.get_or_create(
        participant=participant,
        defaults={
            "status": VERIFICATION_STATUS_PENDING,
            "verification_method": method,
        }
    )

def upload_national_id(participant, id_number, front_file, back_file):
    """
    Saves ID front/back files and ID number, transitions status,
    and logs verification events.
    """
    with transaction.atomic():
        verification, _ = create_verification(participant)
        
        verification.national_id_number = id_number
        if front_file:
            verification.national_id_front = front_file
        if back_file:
            verification.national_id_back = back_file
        verification.save()
            
        verification.transition_to(VERIFICATION_STATUS_ID_UPLOADED)
        
        # Log append-only audit events
        if front_file:
            VerificationEvent.objects.create(
                signer_verification=verification,
                event_type=EVENT_ID_FRONT_UPLOADED,
                metadata={"filename": front_file.name}
            )
        if back_file:
            VerificationEvent.objects.create(
                signer_verification=verification,
                event_type=EVENT_ID_BACK_UPLOADED,
                metadata={"filename": back_file.name}
            )
            
        return verification

def upload_selfie(participant, selfie_file):
    """
    Saves the selfie file, transitions status to selfie_uploaded,
    then automatically advances to under_review, logging appropriate events.
    """
    with transaction.atomic():
        verification, _ = create_verification(participant)
        
        if selfie_file:
            verification.selfie_image = selfie_file
        verification.save()
            
        # First transition to selfie_uploaded
        verification.transition_to(VERIFICATION_STATUS_SELFIE_UPLOADED)
        
        # Log selfie event
        if selfie_file:
            VerificationEvent.objects.create(
                signer_verification=verification,
                event_type=EVENT_SELFIE_UPLOADED,
                metadata={"filename": selfie_file.name}
            )
            
        # Then auto-advance to under_review (evaluation ready)
        verification.transition_to(VERIFICATION_STATUS_UNDER_REVIEW)
        
        # Log verification started event
        VerificationEvent.objects.create(
            signer_verification=verification,
            event_type=EVENT_VERIFICATION_STARTED,
            metadata={}
        )
        
        return verification

def update_status(verification, target_status, metadata=None):
    """
    Transitions the verification record to target_status and logs completion/failure events.
    """
    if metadata is None:
        metadata = {}
        
    with transaction.atomic():
        if target_status == VERIFICATION_STATUS_VERIFIED:
            verification.verified_at = timezone.now()
            verification.save()
            event_type = EVENT_VERIFICATION_COMPLETED
        elif target_status == VERIFICATION_STATUS_FAILED:
            event_type = EVENT_VERIFICATION_FAILED
        else:
            event_type = None
            
        verification.transition_to(target_status)
        
        if event_type:
            VerificationEvent.objects.create(
                signer_verification=verification,
                event_type=event_type,
                metadata=metadata
            )
            
        return verification

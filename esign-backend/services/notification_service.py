import os
import logging
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from esign.models import Participant, Signer, ParticipantToken, SigningToken

logger = logging.getLogger(__name__)

def get_envelope_title(envelope):
    if envelope.title:
        return envelope.title
    if envelope.document and envelope.document.file:
        return os.path.basename(envelope.document.file.name)
    return f"Package #{envelope.id}"

def get_sender_name(envelope):
    if envelope.owner:
        if envelope.owner.first_name or envelope.owner.last_name:
            return f"{envelope.owner.first_name} {envelope.owner.last_name}".strip()
        return envelope.owner.username
    return "System"

def send_participant_email(participant, envelope, request=None):
    """
    Sends an email to a specific participant with their secure link.
    """
    token_obj, created = ParticipantToken.objects.get_or_create(
        participant=participant,
        defaults={
            "expires_at": timezone.now() + timedelta(hours=24),
            "is_used": False
        }
    )
    token_val = token_obj.token
    logger.warning("DEBUG EMAIL FUNCTION REACHED")

    logger.warning(f"EMAIL_HOST={repr(settings.EMAIL_HOST)}")
    logger.warning(f"EMAIL_PORT={repr(settings.EMAIL_PORT)}")
    logger.warning(f"EMAIL_HOST_USER={repr(settings.EMAIL_HOST_USER)}")
    logger.warning(f"EMAIL_USE_TLS={repr(settings.EMAIL_USE_TLS)}")
    logger.warning(f"PASSWORD_SET={bool(settings.EMAIL_HOST_PASSWORD)}")
    
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    secure_link = f"{frontend_url}/sign/{token_val}"
    
    package_title = get_envelope_title(envelope)
    sender_name = get_sender_name(envelope)
    role = participant.role or "signer"
    role_lower = role.lower()
    
    if role_lower == 'approver':
        subject = "Document waiting for your approval"
    elif role_lower == 'reviewer':
        subject = "Document waiting for your review"
    else:
        subject = "Document waiting for your signature"
        
    body = f"""Hello {participant.name},

{sender_name} has sent you a document: "{package_title}".
Role: {role}

Please use the following secure link to access the document and perform your action:
{secure_link}

This link is valid for 24 hours.

Thank you,
The E-Signature Team
"""
    
    try:
        logger.info(f"Sending role email to {participant.email} for role {role}")
        logger.info(f"EMAIL_HOST={settings.EMAIL_HOST}")
        logger.info(f"EMAIL_PORT={settings.EMAIL_PORT}")
        logger.info(f"EMAIL_HOST_USER={settings.EMAIL_HOST_USER}")
        logger.info(f"EMAIL_USE_TLS={settings.EMAIL_USE_TLS}")
        logger.info(f"DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL}")

        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com"),
            recipient_list=[participant.email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send email to participant {participant.email}: {str(e)}", exc_info=True)


def send_legacy_signer_email(signer, envelope, request=None):
    """
    Sends an email to a legacy signer with their secure link.
    """
    token_obj, created = SigningToken.objects.get_or_create(
        signer=signer,
        defaults={
            "expires_at": timezone.now() + timedelta(hours=24),
            "is_used": False
        }
    )
    token_val = token_obj.token
    
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    secure_link = f"{frontend_url}/sign/{token_val}"
    
    package_title = get_envelope_title(envelope)
    sender_name = get_sender_name(envelope)
    
    subject = "Document waiting for your signature"
    
    body = f"""Hello {signer.name},

{sender_name} has sent you a document: "{package_title}".
Role: Signer

Please use the following secure link to access the document and sign it:
{secure_link}

This link is valid for 24 hours.

Thank you,
The E-Signature Team
"""
    
    try:
        logger.info(f"Sending legacy signer email to {signer.email}")
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com"),
            recipient_list=[signer.email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f"Failed to send email to legacy signer {signer.email}: {str(e)}", exc_info=True)


def send_package_sent_notifications(envelope, request=None):
    """
    Sends email to the first active participant when a package is sent.
    If no participants exist, falls back to legacy Signer.
    """
    active_participants = envelope.participants.filter(status__in=['active', 'viewed']).order_by('step_number', 'order', 'id')
    if active_participants.exists():
        first_p = active_participants.first()
        send_participant_email(first_p, envelope, request)
    else:
        # Fallback to legacy signer
        signer = Signer.objects.filter(envelope=envelope).first()
        if signer:
            send_legacy_signer_email(signer, envelope, request)


def send_next_step_notifications(envelope, step_number, request=None):
    """
    Sends email to all participants in the newly activated step.
    """
    active_participants = envelope.participants.filter(step_number=step_number, status__in=['active', 'viewed'])
    for p in active_participants:
        send_participant_email(p, envelope, request)


def send_completion_email(envelope, certificate_id=None, request=None):
    """
    Sends a final completion email to the package owner and additional recipients.
    """
    token_val = None
    
    first_p = envelope.participants.order_by('step_number', 'order', 'id').first()
    if first_p:
        token_obj = ParticipantToken.objects.filter(participant=first_p).first()
        if token_obj:
            token_val = token_obj.token
            
    if not token_val:
        signer = Signer.objects.filter(envelope=envelope).first()
        if signer:
            token_obj = SigningToken.objects.filter(signer=signer).first()
            if token_obj:
                token_val = token_obj.token
                
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    
    if request:
        base_api_url = request.build_absolute_uri('/')[:-1]
    else:
        base_api_url = "http://localhost:8000"
        
    if token_val:
        view_url = f"{frontend_url}/sign/{token_val}"
        download_url = f"{base_api_url}/api/sign/{token_val}/download/"
    else:
        view_url = f"{frontend_url}/packages/{envelope.id}"
        download_url = f"{base_api_url}/api/packages/{envelope.id}/download/"
        
    package_title = get_envelope_title(envelope)
    
    subject = "Package completed successfully"
    body_header = f"""Hello,

The document "{package_title}" has been fully completed by all participants.
"""
    if certificate_id:
        body_header += f"Certificate ID: {certificate_id}\n"

    body = body_header + f"""
You can preview the signed document on the platform at:
{view_url}

Or download the completed PDF directly from this link:
{download_url}

Thank you,
The E-Signature Team
"""
    
    recipients = []
    if envelope.owner and envelope.owner.email:
        recipients.append(envelope.owner.email)
        
    if envelope.additional_recipients:
        for email in envelope.additional_recipients:
            if email and email not in recipients:
                recipients.append(email)
                
    if not recipients:
        logger.info("No recipients found to send completion email to.")
        return
        
    # Build attachments
    attachments_list = []
    
    # 1. Signed Document PDF
    signed_doc = getattr(envelope, 'signeddocument', None)
    if signed_doc and signed_doc.file:
        try:
            signed_doc.file.open('rb')
            content = signed_doc.file.read()
            filename = os.path.basename(signed_doc.file.name) or f"signed_{envelope.id}.pdf"
            attachments_list.append((filename, content, "application/pdf"))
        except Exception as e:
            logger.error(f"Failed to read signed document for attachment: {str(e)}", exc_info=True)
        finally:
            signed_doc.file.close()
            
    # 2. Certificate of Completion PDF
    cert_doc = getattr(envelope, 'completion_certificate', None)
    if cert_doc and cert_doc.file:
        try:
            cert_doc.file.open('rb')
            content = cert_doc.file.read()
            filename = os.path.basename(cert_doc.file.name) or f"certificate_{envelope.id}.pdf"
            attachments_list.append((filename, content, "application/pdf"))
        except Exception as e:
            logger.error(f"Failed to read certificate for attachment: {str(e)}", exc_info=True)
        finally:
            cert_doc.file.close()

    for email in recipients:
        try:
            logger.info(f"Sending completion email to {email} with attachments")
            email_message = EmailMessage(
                subject=subject,
                body=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com"),
                to=[email],
            )
            # Attach both files
            for filename, content, mimetype in attachments_list:
                email_message.attach(filename, content, mimetype)
                
            email_message.send(fail_silently=False)
        except Exception as e:
            logger.error(f"Failed to send completion email with attachments to {email}: {str(e)}", exc_info=True)

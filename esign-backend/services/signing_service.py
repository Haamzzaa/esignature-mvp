import base64
import io
import hashlib
import logging
from PIL import Image
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.core.files.base import ContentFile
from django.urls import reverse
from django.db.models import Max

from esign.models import Envelope, Participant, ParticipantToken, SigningToken, Signer, SignedDocument, AuditLog
from services.token_service import get_token_context
from services.pdf_signing_service import sign_document
from services.workflow_service import check_and_advance_step
from services.field_service import get_fields_for_participant

logger = logging.getLogger(__name__)

def get_signing_session_data(token_str, request):
    try:
        context = get_token_context(token_str, allow_used=True)
    except ValueError as e:
        return None, str(e)

    participant = context.participant
    envelope = context.envelope
    role = participant.role
    name = participant.name
    email = participant.email
    p_status = participant.status
    step_num = participant.step_number
    total_steps = envelope.participants.aggregate(max_step=Max('step_number'))['max_step'] or 1

    signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
    fields_qs = get_fields_for_participant(participant)
    fields_list = []
    for f in fields_qs:
        fields_list.append({
            "id": f.id,
            "field_type": f.field_type,
            "page": f.page,
            "x_ratio": f.x_ratio,
            "y_ratio": f.y_ratio,
            "required": f.required
        })

    data = {
        "participant_id": participant.id if participant else None,
        "signer_name": name,
        "signer_email": email,
        "participant_role": role,
        "participant_status": p_status,
        "participant_step": step_num,
        "total_steps": total_steps,
        "envelope_id": envelope.id,
        "status": envelope.status,
        "fields": fields_list
    }

    if envelope.status == "completed" and signed_doc:
        data["status"] = "completed"
        data["document_url"] = request.build_absolute_uri(
            reverse('signing-signed', kwargs={'token': token_str})
        )
        data["signed_document_url"] = request.build_absolute_uri(
            reverse('signing-signed', kwargs={'token': token_str})
        )
    else:
        data["document_url"] = request.build_absolute_uri(
            reverse('signing-document', kwargs={'token': token_str})
        )

    return data, None


def process_action(token_str, request_data, request):
    try:
        context = get_token_context(token_str)
    except ValueError as e:
        return None, str(e)

    participant = context.participant
    envelope = context.envelope
    role = participant.role
    name = participant.name
    email = participant.email
    p_status = participant.status

    ip_address = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT")
    action = request_data.get("action")

    if action == "view":
        with transaction.atomic():
            # Lock order: Token -> Participant -> Envelope
            if context.participant_token:
                locked_token = ParticipantToken.objects.select_for_update().get(id=context.participant_token.id)
            else:
                locked_token = None

            if context.legacy_signing_token:
                locked_legacy_token = SigningToken.objects.select_for_update().get(id=context.legacy_signing_token.id)
            else:
                locked_legacy_token = None

            locked_participant = Participant.objects.select_for_update().get(id=participant.id)
            locked_envelope = Envelope.objects.select_for_update().get(id=envelope.id)
            
            if locked_legacy_token:
                # Legacy signer viewed
                AuditLog.objects.get_or_create(
                    envelope=locked_envelope,
                    event="viewed",
                    defaults={
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                    }
                )
                if locked_envelope.status == "sent":
                    locked_envelope.transition_to("viewed")
                
                if locked_participant and locked_participant.status == 'active':
                    locked_participant.status = 'viewed'
                    locked_participant.save(update_fields=["status"])
            else:
                # Modern participant viewed
                if locked_participant.status == 'active':
                    locked_participant.status = 'viewed'
                    locked_participant.save(update_fields=['status'])
                    
                    AuditLog.objects.get_or_create(
                        envelope=locked_envelope,
                        event="Participant Viewed",
                        defaults={
                            "ip_address": ip_address,
                            "user_agent": user_agent,
                        }
                    )

        return {
            "message": "View registered successfully.",
            "envelope_id": envelope.id,
            "status": envelope.status,
        }, None

    # Check if already completed/declined
    if envelope.status in ("completed", "declined"):
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        return {
            "detail": "Envelope already processed or declined.",
            "status": envelope.status,
            "signed_document_url": request.build_absolute_uri(
                reverse('signing-download', kwargs={'token': token_str})
            ) if signed_doc else None,
        }, "ALREADY_PROCESSED"

    # Enforce that only active/viewed participants can act
    if p_status not in ('active', 'viewed'):
        return None, "Workflow stage is not yet active for your role. Actions are restricted."

    # Check authorization requirements for completing actions (approve, acknowledge, sign)
    is_completing_action = False
    if role == "signer":
        is_completing_action = True
    elif role != "signer" and action in ("approve", "acknowledge"):
        is_completing_action = True

    if is_completing_action:
        from services.security_policy_service import get_authorization_status
        auth_status = get_authorization_status(participant)
        if not auth_status["authorized"]:
            logger.warning(
                f"Authorization denied for participant {participant.id} on action '{action}'. "
                f"Missing requirements: {auth_status['missing_requirements']}"
            )
            status_val = auth_status.get("status")
            reason_val = auth_status.get("reason")
            
            if status_val == "MANUAL_REVIEW_REQUIRED" or reason_val == "No representative found in contract.":
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Manual review required",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                return {
                    "detail": "An administrator must review the authorization.",
                    "status": "MANUAL_REVIEW_REQUIRED",
                    "reason": reason_val or "No representative found in contract."
                }, "MANUAL_REVIEW_REQUIRED"
            elif reason_val == "Identity verification incomplete.":
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Authorization failed",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                return {
                    "detail": "Identity verification incomplete.",
                    "status": "NOT_AUTHORIZED",
                    "reason": "Identity verification incomplete."
                }, "IDENTITY_OCR_FAILED"
            elif reason_val == "Face biometric verification failed.":
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Authorization failed",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                return {
                    "detail": "Face biometric verification failed.",
                    "status": "NOT_AUTHORIZED",
                    "reason": "Face biometric verification failed."
                }, "BIOMETRIC_FAILED"
            else:
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Authorization failed",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                return {
                    "detail": "Authorization failed.",
                    "status": "NOT_AUTHORIZED",
                    "reason": reason_val or "Authorization requirements not satisfied."
                }, "AUTHORIZATION_FAILED"
        else:
            # Succeeded
            AuditLog.objects.create(
                envelope=envelope,
                event="Authorization passed",
                ip_address=ip_address,
                user_agent=user_agent
            )

    # ── Non-Signer Role Actions handling ───────────────────────────────────────────
    if role != "signer":
        allowed_actions = ("approve", "return", "reject")
        if role == "cc":
            allowed_actions = ("acknowledge",)
            
        if action not in allowed_actions:
            return None, f"Invalid action '{action}' for role '{role}'."

        with transaction.atomic():
            # Acquire locks: Token -> Participant -> Envelope
            if context.participant_token:
                locked_token = ParticipantToken.objects.select_for_update().get(id=context.participant_token.id)
            else:
                locked_token = None

            if context.legacy_signing_token:
                locked_legacy_token = SigningToken.objects.select_for_update().get(id=context.legacy_signing_token.id)
            else:
                locked_legacy_token = None

            locked_participant = Participant.objects.select_for_update().get(id=participant.id)
            locked_envelope = Envelope.objects.select_for_update().get(id=envelope.id)

            # Re-verify lock eligibility under lock
            if (locked_token and locked_token.is_used) or (locked_legacy_token and locked_legacy_token.is_used) or locked_envelope.status in ('completed', 'declined'):
                return None, "Envelope already processed or declined."

            if role == "reviewer":
                if action == "approve":
                    locked_participant.status = "completed"
                    locked_participant.completed_at = timezone.now()
                    locked_participant.save(update_fields=["status", "completed_at"])
                    
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Reviewer Approved",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Participant Approved",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                elif action == "return":
                    locked_participant.status = "returned"
                    locked_participant.completed_at = timezone.now()
                    locked_participant.save(update_fields=["status", "completed_at"])
                    locked_envelope.transition_to("declined")
                    
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Reviewer Returned",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Participant Returned",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
            elif role == "approver":
                if action == "approve":
                    locked_participant.status = "completed"
                    locked_participant.completed_at = timezone.now()
                    locked_participant.save(update_fields=["status", "completed_at"])
                    
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Approver Approved",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Participant Approved",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                elif action == "reject":
                    locked_participant.status = "declined"
                    locked_participant.completed_at = timezone.now()
                    locked_participant.save(update_fields=["status", "completed_at"])
                    locked_envelope.transition_to("declined")
                    
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Approver Rejected",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="Participant Rejected",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
            elif role == "cc":
                if action == "acknowledge":
                    locked_participant.status = "completed"
                    locked_participant.completed_at = timezone.now()
                    locked_participant.save(update_fields=["status", "completed_at"])
                    
                    AuditLog.objects.create(
                        envelope=locked_envelope,
                        event="CC Acknowledged",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
            
            # Invalidate tokens
            if locked_token:
                locked_token.is_used = True
                locked_token.save(update_fields=["is_used"])

            if locked_legacy_token:
                locked_legacy_token.is_used = True
                locked_legacy_token.save(update_fields=["is_used"])

            # Check and advance step if not declined
            if locked_envelope.status != "declined":
                check_and_advance_step(locked_envelope, locked_participant.step_number, request)

        return {
            "message": f"Action {action} processed successfully.",
            "envelope_id": locked_envelope.id,
            "status": locked_envelope.status,
        }, None

    # ── Signer Role logic (PDF embedding) ──────────────────────────────────────────
    sig_type = request_data.get("signature_type", "typed")

    if sig_type == "typed":
        signature_text = request_data.get("signature_text", "").strip()
        if not signature_text:
            return None, "signature_text is required for typed signatures."
        signature_image_b64 = None

    elif sig_type in ("upload", "draw"):
        signature_image_b64 = request_data.get("signature_image", "").strip()
        if not signature_image_b64:
            return None, "signature_image (base64) is required for upload/draw signatures."
        
        if sig_type == "upload":
            try:
                b64_data = signature_image_b64
                if "," in b64_data:
                    b64_data = b64_data.split(",", 1)[1]
                
                decoded_bytes = base64.b64decode(b64_data)
                
                if len(decoded_bytes) > 2 * 1024 * 1024:
                    return None, "Signature image exceeds maximum allowed size (2MB)."
                
                try:
                    with Image.open(io.BytesIO(decoded_bytes)) as img:
                        img_format = img.format
                except Exception:
                    return None, "Unable to parse signature image format."
                
                if not img_format or img_format.upper() not in ("PNG", "JPEG", "WEBP"):
                    return None, "Unsupported image format. Allowed formats: PNG, JPG, JPEG, WEBP."
            except Exception:
                return None, "Invalid base64 signature image data."

        signature_text = None
    else:
        return None, f"Unsupported signature_type: '{sig_type}'. Use 'typed', 'upload', or 'draw'."

    # Database mutations under lock
    with transaction.atomic():
        # Acquire locks: Token -> Participant -> Envelope
        if context.participant_token:
            locked_token = ParticipantToken.objects.select_for_update().get(id=context.participant_token.id)
        else:
            locked_token = None

        if context.legacy_signing_token:
            locked_legacy_token = SigningToken.objects.select_for_update().get(id=context.legacy_signing_token.id)
        else:
            locked_legacy_token = None

        locked_participant = Participant.objects.select_for_update().get(id=participant.id)
        locked_envelope = Envelope.objects.select_for_update().get(id=envelope.id)

        # Re-verify lock eligibility under lock
        if (locked_token and locked_token.is_used) or (locked_legacy_token and locked_legacy_token.is_used) or locked_envelope.status in ('completed', 'declined'):
            return None, "Envelope already processed or declined."

        # Fetch latest SignedDocument while lock is held
        signed_doc = SignedDocument.objects.filter(envelope=locked_envelope).select_for_update().first()

        # Deterministic document source resolution
        locked_document = locked_envelope.document
        if not locked_document or not locked_document.file:
            raise ValidationError("Original document file is missing.")

        if signed_doc and signed_doc.file:
            signed_doc.file.open("rb")
            try:
                original_bytes = signed_doc.file.read()
            finally:
                signed_doc.file.close()
        else:
            locked_document.file.open("rb")
            try:
                original_bytes = locked_document.file.read()
            finally:
                locked_document.file.close()

        final_hash    = hashlib.sha256(original_bytes).hexdigest()
        original_name = locked_document.file.name.rsplit("/", 1)[-1] or "signed.pdf"

        # PDF Signing (inside lock transaction)
        fields_payload = request_data.get('fields', {})

        try:
            pdf_bytes = sign_document(
                envelope=locked_envelope,
                participant_rec=locked_participant,
                name=name,
                sig_type=sig_type,
                signature_text=signature_text,
                signature_image_b64=signature_image_b64,
                fields_payload=fields_payload,
                original_bytes=original_bytes,
            )
        except Exception as e:
            logger.error(f"Image/PDF processing failed: {str(e)}", exc_info=True)
            raise ValidationError("Unable to process uploaded signature image.")

        # Update existing SignedDocument record in place or create new one
        if signed_doc:
            signed_doc.final_hash = final_hash
            signed_doc.file.save(original_name, ContentFile(pdf_bytes), save=True)
        else:
            signed_doc = SignedDocument(envelope=locked_envelope, final_hash=final_hash)
            signed_doc.file.save(original_name, ContentFile(pdf_bytes), save=True)

        if locked_token:
            locked_token.is_used   = True
            locked_token.expires_at = timezone.now() + timedelta(minutes=15)
            locked_token.save(update_fields=["is_used", "expires_at"])

        if locked_legacy_token:
            locked_legacy_token.is_used   = True
            locked_legacy_token.expires_at = timezone.now() + timedelta(minutes=15)
            locked_legacy_token.save(update_fields=["is_used", "expires_at"])

        locked_participant.has_completed = True
        locked_participant.status = 'completed'
        locked_participant.completed_at = timezone.now()
        locked_participant.save(update_fields=["has_completed", "status", "completed_at"])
        current_step = locked_participant.step_number

        # Create audit events
        AuditLog.objects.create(
            envelope=locked_envelope,
            event="signed",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        AuditLog.objects.create(
            envelope=locked_envelope,
            event="Signer Completed",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        AuditLog.objects.create(
            envelope=locked_envelope,
            event="Participant Signed",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        p_name = locked_participant.name
        AuditLog.objects.create(
            envelope=locked_envelope,
            event=f"Participant {p_name} Completed",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        check_and_advance_step(locked_envelope, current_step, request)

    return {
        "message": "Document signed successfully.",
        "envelope_id": locked_envelope.id,
        "status": locked_envelope.status,
        "signed_document_id": signed_doc.id,
        "signed_document_url": request.build_absolute_uri(
            reverse('signing-signed', kwargs={'token': token_str})
        ),
        "download_url": request.build_absolute_uri(
            reverse('signing-download', kwargs={'token': token_str})
        ),
    }, None

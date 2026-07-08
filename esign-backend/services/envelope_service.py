from esign.config import esign_config
import logging
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.core.validators import validate_email as dj_validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.generics import get_object_or_404

from esign.models import Envelope, Document, DocumentField, Participant, ParticipantToken, Signer, SigningToken, AuditLog
from esign.serializers import EnvelopeCreateSerializer
from services.workflow_service import activate_workflow_step
from services.notification_service import send_package_sent_notifications

logger = logging.getLogger(__name__)

def create_envelope(request_data, owner):
    is_draft = request_data.get('is_draft', False)
    
    # ── Mandatory Placement Validation (skipped for drafts) ──────────────
    if not is_draft:
        sig_page = request_data.get('signature_page')
        sig_x = request_data.get('signature_x_ratio')
        sig_y = request_data.get('signature_y_ratio')
        fields = request_data.get('fields', [])

        if not fields and (sig_page is None or sig_x is None or sig_y is None):
            return None, "Signature placement is required."

    serializer = EnvelopeCreateSerializer(data=request_data, context={'owner': owner})
    if serializer.is_valid():
        envelope = serializer.save(owner=owner)
        return {
            "envelope_id": envelope.id,
            "status": envelope.status,
            "send_reminders": envelope.send_reminders,
            "send_final_email": envelope.send_final_email,
            "allow_printing": envelope.allow_printing,
            "additional_recipients": envelope.additional_recipients,
            "email_otp_required": envelope.email_otp_required,
            "sms_otp_required": envelope.sms_otp_required,
            "national_id_required": envelope.national_id_required,
            "face_biometric_required": envelope.face_biometric_required,
            "representative_match_required": envelope.representative_match_required,
            "terms_acceptance_required": envelope.terms_acceptance_required,
        }, None
        
    return None, serializer.errors


def validate_envelope_for_send(envelope):
    errors = []
    
    # 1. Required package metadata
    if not envelope.title or not envelope.title.strip():
        errors.append("Package title is required.")
    if not envelope.document:
        errors.append("Document is required.")
        
    # 2. Participants & Workflow configuration
    participants = envelope.participants.all()
    if not participants.exists():
        errors.append("At least one participant is required.")
    else:
        has_signer = participants.filter(role='signer').exists()
        if not has_signer:
            errors.append("At least one participant must have the 'Signer' role.")
            
        for p in participants:
            if p.role not in ['signer', 'approver', 'reviewer', 'cc']:
                errors.append(f"Participant {p.email} has an invalid role: {p.role}.")
            if p.step_number < 1:
                errors.append(f"Participant {p.email} has an invalid step number: {p.step_number}.")
                
        # 3. Every signer has at least one required signature field
        fields = envelope.fields.all()
        signers = participants.filter(role='signer')
        for signer in signers:
            has_sig_field = fields.filter(participant=signer, field_type='signature', required=True).exists()
            if not has_sig_field:
                is_first_signer = (signer == signers.order_by('step_number', 'order', 'id').first())
                has_legacy_sig = (not fields.exists() and is_first_signer and 
                                  envelope.signature_x_ratio is not None and 
                                  envelope.signature_y_ratio is not None)
                if not has_legacy_sig:
                    errors.append(f"Signer {signer.name} ({signer.email}) must have at least one required signature field placed.")
                    
    return len(errors) == 0, errors


def send_envelope(envelope_id, owner, request):
    envelope = get_object_or_404(Envelope, id=envelope_id, owner=owner)
    
    is_valid, errors = validate_envelope_for_send(envelope)
    if not is_valid:
        return None, errors

    expires_at = timezone.now() + timedelta(hours=esign_config.signing_link_expiry)

    with transaction.atomic():
        participants = envelope.participants.all()

        # Activate the first workflow step
        step_numbers = sorted(set(participants.values_list('step_number', flat=True)))
        min_step = step_numbers[0]
        activate_workflow_step(envelope, min_step)

        # Ensure a legacy Signer record exists (required for token resolution/compatibility)
        first_signer_p = (
            participants.filter(role='signer')
            .order_by('step_number', 'order', 'id')
            .first()
        )
        signer, _ = Signer.objects.get_or_create(
            envelope=envelope,
            defaults={'name': first_signer_p.name, 'email': first_signer_p.email},
        )

        # Issue / refresh the signing token (legacy compat, used in response URL)
        signing_token, created = SigningToken.objects.get_or_create(
            signer=signer,
            defaults={"expires_at": expires_at, "is_used": False},
        )
        if not created:
            signing_token.expires_at = expires_at
            signing_token.is_used = False
            signing_token.save()

        envelope.transition_to("sent")

        AuditLog.objects.create(
            envelope=envelope,
            event="sent",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        base_api_url = request.build_absolute_uri('/')[:-1] if request else None
        from esign.events.dispatcher import esign_dispatcher
        from esign.events.definitions import EnvelopeSent
        
        event = EnvelopeSent(envelope_id=envelope.id, expires_at=expires_at.isoformat())
        event.payload["base_api_url"] = base_api_url
        
        transaction.on_commit(
            lambda: esign_dispatcher.publish(event)
        )

    return {
        "message": "Envelope sent to signer.",
        "expires_at": expires_at.isoformat(),
        "email_warning": None,
    }, None


def patch_envelope(envelope_id, request_data, owner):
    envelope = get_object_or_404(Envelope, id=envelope_id, owner=owner)
    if envelope.status != 'draft':
        return None, "Only draft packages can be updated this way."

    with transaction.atomic():
        # ── Simple scalar fields ──────────────────────────────────────────
        simple_map = {
            'title': 'title',
            'description': 'description',
            'signature_page': 'signature_page',
            'signature_x_ratio': 'signature_x_ratio',
            'signature_y_ratio': 'signature_y_ratio',
            'send_reminders': 'send_reminders',
            'send_final_email': 'send_final_email',
            'allow_printing': 'allow_printing',
            'email_otp_required': 'email_otp_required',
            'sms_otp_required': 'sms_otp_required',
            'national_id_required': 'national_id_required',
            'face_biometric_required': 'face_biometric_required',
            'representative_match_required': 'representative_match_required',
            'terms_acceptance_required': 'terms_acceptance_required',
        }
        for req_key, model_field in simple_map.items():
            if req_key in request_data:
                setattr(envelope, model_field, request_data[req_key])

        # ── additional_recipients ─────────────────────────────────────────
        if 'additional_recipients' in request_data:
            recipients = request_data['additional_recipients']
            if not isinstance(recipients, list):
                return None, {'additional_recipients': ['Must be a list of email strings.']}
            validated_recipients = []
            for email in recipients:
                email_str = str(email).strip()
                if not email_str:
                    continue
                try:
                    dj_validate_email(email_str)
                except DjangoValidationError:
                    return None, {'additional_recipients': [f"Enter a valid email address: '{email_str}'."]}
                validated_recipients.append(email_str)
            envelope.additional_recipients = validated_recipients

        # ── Optional document update ──────────────────────────────────────
        if 'document_id' in request_data:
            try:
                new_doc = Document.objects.get(id=request_data['document_id'])
                if new_doc.owner and new_doc.owner != owner:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("You do not have permission to use this document.")
                envelope.document = new_doc
            except Document.DoesNotExist:
                return None, {'document_id': ['Document not found.']}

        envelope.save()

        # ── Replace participants ───────────────────────────────────────────
        if 'participants' in request_data:
            participants_raw = request_data['participants']
            if not isinstance(participants_raw, list):
                return None, {'participants': ['Must be a list.']}

            # Validate emails before deleting existing records
            for p_data in participants_raw:
                email_str = str(p_data.get('email', '')).strip()
                if email_str:
                    try:
                        dj_validate_email(email_str)
                    except DjangoValidationError:
                        name_str = str(p_data.get('name', '')).strip() or email_str
                        return None, {'participants': [f"Enter a valid email address for '{name_str}'."]}

            # Replace atomically
            envelope.participants.all().delete()  # cascades ParticipantToken

            for idx, p_data in enumerate(participants_raw):
                p = Participant.objects.create(
                    envelope=envelope,
                    name=str(p_data.get('name', '')).strip(),
                    email=str(p_data.get('email', '')).strip(),
                    role=p_data.get('role', 'signer'),
                    step_number=p_data.get('step_number', 1),
                    order=p_data.get('order', idx + 1),
                    status='pending',
                )
                ParticipantToken.objects.create(
                    participant=p,
                    expires_at=timezone.now() + timedelta(hours=24),
                    is_used=False,
                )

        # ── Replace fields ────────────────────────────────────────────────
        if 'fields' in request_data:
            fields_raw = request_data['fields']
            DocumentField.objects.filter(envelope=envelope).delete()

            if isinstance(fields_raw, list) and fields_raw:
                from services.field_service import create_field
                participants_by_email = {
                    p.email: p for p in envelope.participants.all()
                }
                for field in fields_raw:
                    if not isinstance(field, dict):
                        continue
                    p_email = field.get('participant_email')
                    participant_inst = participants_by_email.get(p_email)
                    if participant_inst:
                        try:
                            create_field(
                                envelope=envelope,
                                participant=participant_inst,
                                field_type=field.get('field_type'),
                                page=field.get('page'),
                                x_ratio=field.get('x_ratio'),
                                y_ratio=field.get('y_ratio'),
                                required=field.get('required', True),
                            )
                        except Exception as exc:
                            # Log field creation failures during draft saves rather than silently swallowing
                            logger.warning(f"Failed to create field during draft save for {p_email}: {exc}", exc_info=True)

    return {"envelope_id": envelope.id, "status": envelope.status}, None


def save_envelope_from_validated_data(validated_data):
    """
    Creates an envelope, participants, legacy signers, and fields from validated serializer data.
    Moves core creation business logic out of the serializer class.
    """
    from django.db import transaction
    from esign.models import Document, Envelope, Signer, Participant, ParticipantToken, AuditLog
    from django.utils import timezone
    from datetime import timedelta
    from services.workflow_service import activate_workflow_step
    from esign.serializers import clean_filename

    with transaction.atomic():
        is_draft          = validated_data.pop('is_draft', False)
        owner             = validated_data.pop('owner', None)
        fields_data       = validated_data.pop('fields', [])
        title             = validated_data.get('title')
        document_id       = validated_data['document_id']
        signer_data       = validated_data.get('signer')
        participants_data = validated_data.get('participants', [])
        signature_page    = validated_data.get('signature_page', 1)
        signature_x_ratio = validated_data.get('signature_x_ratio')
        signature_y_ratio = validated_data.get('signature_y_ratio')
        send_reminders    = validated_data.get('send_reminders', False)
        send_final_email  = validated_data.get('send_final_email', True)
        allow_printing    = validated_data.get('allow_printing', True)
        additional_recipients = validated_data.get('additional_recipients', [])

        email_otp_required = validated_data.get('email_otp_required', False)
        sms_otp_required = validated_data.get('sms_otp_required', False)
        national_id_required = validated_data.get('national_id_required', False)
        face_biometric_required = validated_data.get('face_biometric_required', False)
        representative_match_required = validated_data.get('representative_match_required', False)
        terms_acceptance_required = validated_data.get('terms_acceptance_required', False)

        document = Document.objects.get(id=document_id)
        if not title or not title.strip():
            if document and document.file and document.file.name:
                title = clean_filename(document.file.name)
            else:
                title = ""

        envelope = Envelope.objects.create(
            document=document,
            title=title,
            signature_page=signature_page,
            signature_x_ratio=signature_x_ratio,
            signature_y_ratio=signature_y_ratio,
            send_reminders=send_reminders,
            send_final_email=send_final_email,
            allow_printing=allow_printing,
            additional_recipients=additional_recipients,
            owner=owner,
            email_otp_required=email_otp_required,
            sms_otp_required=sms_otp_required,
            national_id_required=national_id_required,
            face_biometric_required=face_biometric_required,
            representative_match_required=representative_match_required,
            terms_acceptance_required=terms_acceptance_required,
        )

        # Map legacy signer to modern participant if no participants are provided
        if not participants_data and signer_data:
            participants_data = [{
                'name': signer_data['name'],
                'email': signer_data['email'],
                'role': 'signer',
                'step_number': 1,
                'order': 1
            }]

        # Determine the lowest step_number
        step_numbers = [p_data.get('step_number', 1) for p_data in participants_data]
        min_step = min(step_numbers) if step_numbers else 1

        for p_idx, p_data in enumerate(participants_data):
            p_data = p_data.copy()
            order = p_data.pop('order', p_idx + 1)

            p = Participant.objects.create(
                envelope=envelope,
                order=order,
                status='pending',
                **p_data
            )
            ParticipantToken.objects.create(
                participant=p,
                expires_at=timezone.now() + timedelta(hours=24),
                is_used=False
            )

        if not is_draft:
            # Audit logging for sequential workflow initiation
            AuditLog.objects.create(envelope=envelope, event="Workflow Started")
            AuditLog.objects.create(envelope=envelope, event=f"Step {min_step} Activated")

            # Legacy compatibility: create Signer record for the first signer participant
            signer_record_created = False
            if participants_data:
                first_signer = None
                for p in participants_data:
                    if p.get('role') == 'signer':
                        first_signer = p
                        break
                if first_signer:
                    Signer.objects.create(
                        envelope=envelope,
                        name=first_signer['name'],
                        email=first_signer['email']
                    )
                    signer_record_created = True

            if not signer_record_created and signer_data:
                Signer.objects.create(envelope=envelope, **signer_data)

            # Activate Step 1 / min_step participants and provision their ParticipantTokens
            activate_workflow_step(envelope, min_step)

        # Create fields (safe for both draft and non-draft)
        if fields_data:
            from services.field_service import create_field

            participants_by_email = {p.email: p for p in envelope.participants.all()}

            # Legacy fallback: if no participants, create a Participant record for the legacy signer
            if not participants_by_email:
                legacy_signer = Signer.objects.filter(envelope=envelope).first()
                if legacy_signer:
                    p_instance = Participant.objects.create(
                        envelope=envelope,
                        name=legacy_signer.name,
                        email=legacy_signer.email,
                        role='signer',
                        order=1,
                        step_number=1,
                        status='active'
                    )
                    participants_by_email[p_instance.email] = p_instance

            for field in fields_data:
                p_email = field.get('participant_email')
                participant_inst = participants_by_email.get(p_email)
                if participant_inst:
                    create_field(
                        envelope=envelope,
                        participant=participant_inst,
                        field_type=field.get('field_type'),
                        page=field.get('page'),
                        x_ratio=field.get('x_ratio'),
                        y_ratio=field.get('y_ratio'),
                        required=field.get('required', True)
                    )

        return envelope

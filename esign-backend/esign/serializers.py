# pyrefly: ignore [missing-import]
from rest_framework import serializers
import hashlib
import os
import re
from django.db import transaction
from .models import Document, Signer, Envelope, Participant, AuditLog, Template

def clean_filename(filename):
    if not filename:
        return ""
    
    # 1. Remove the file extension
    original_stem = os.path.splitext(os.path.basename(filename))[0]
    
    parts = original_stem.split('_')
    if len(parts) > 1:
        # Check leading numeric prefix
        has_leading_numeric = parts[0].isdigit()
        
        # Check trailing random suffix
        last_part = parts[-1]
        has_trailing_random = False
        if 5 <= len(last_part) <= 8 and last_part.isalnum():
            if not re.match(r'^v\d+$', last_part, re.IGNORECASE):
                has_letters = any(c.isalpha() for c in last_part)
                has_digits = any(c.isdigit() for c in last_part)
                if has_letters and has_digits:
                    has_trailing_random = True
                elif has_letters:
                    has_uppercase_after_start = any(c.isupper() for c in last_part[1:])
                    has_lowercase = any(c.islower() for c in last_part)
                    if has_uppercase_after_start and has_lowercase:
                        has_trailing_random = True
                        
        if has_leading_numeric:
            parts.pop(0)
        if has_trailing_random:
            if parts:
                parts.pop()
                
    # 4. Replace remaining underscores with spaces (done by joining parts with space)
    stem = ' '.join(parts)
    
    # 5. Trim whitespace
    stem = stem.strip()
    
    # 7. Fall back to original stem if empty
    if not stem:
        stem = original_stem
        
    return stem

class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['file']

    def create(self, validated_data):
        file = validated_data['file']
        owner = validated_data.get('owner')
        hasher = hashlib.sha256()
        for chunk in file.chunks():
            hasher.update(chunk)
        file_hash = hasher.hexdigest()
        document = Document.objects.create(file=file, file_hash=file_hash, owner=owner)
        return document
        
class SignerSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()

    class Meta:
        model = Signer
        fields = ['name', 'email']

class ParticipantSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()

    class Meta:
        model = Participant
        fields = ['name', 'email', 'role', 'order', 'step_number', 'status', 'completed_at']
        read_only_fields = ['status', 'completed_at']

class EnvelopeCreateSerializer(serializers.Serializer):
    title             = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    document_id       = serializers.IntegerField()
    signer            = SignerSerializer(required=False, allow_null=True)
    participants      = ParticipantSerializer(many=True, required=False)
    signature_page    = serializers.IntegerField(default=1)
    # Ratio-based placement (0.0–1.0).  Optional — omitted when no position selected.
    signature_x_ratio = serializers.FloatField(allow_null=True, required=False, default=None)
    signature_y_ratio = serializers.FloatField(allow_null=True, required=False, default=None)
    send_reminders    = serializers.BooleanField(required=False, default=False)
    send_final_email  = serializers.BooleanField(required=False, default=True)
    allow_printing    = serializers.BooleanField(required=False, default=True)

    email_otp_required = serializers.BooleanField(required=False, default=False)
    sms_otp_required = serializers.BooleanField(required=False, default=False)
    national_id_required = serializers.BooleanField(required=False, default=False)
    face_biometric_required = serializers.BooleanField(required=False, default=False)
    representative_match_required = serializers.BooleanField(required=False, default=False)
    terms_acceptance_required = serializers.BooleanField(required=False, default=False)

    additional_recipients = serializers.JSONField(required=False, default=list)
    fields            = serializers.JSONField(required=False, default=list)
    # When True: skip participant/signer/field validation and workflow activation.
    # Used for Save Draft — the envelope is persisted without starting the workflow.
    is_draft          = serializers.BooleanField(required=False, default=False)

    def validate_document_id(self, value):
        try:
            document = Document.objects.get(id=value)
        except Document.DoesNotExist:
            raise serializers.ValidationError("Document not found.")
        
        owner = self.context.get('owner')
        if owner and document.owner and document.owner != owner:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to use this document.")
        return value

    def validate_additional_recipients(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("additional_recipients must be a list of emails.")
        
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        
        seen = set()
        validated_emails = []
        for email in value:
            if not email:
                continue
            email_str = str(email).strip()
            if not email_str:
                continue
            try:
                validate_email(email_str)
            except DjangoValidationError:
                raise serializers.ValidationError(f"Enter a valid email address: '{email_str}'.")
            
            if email_str in seen:
                raise serializers.ValidationError(f"Duplicate recipient email: {email_str}")
            seen.add(email_str)
            validated_emails.append(email_str)
        return validated_emails

    def validate(self, attrs):
        is_draft = attrs.get('is_draft', False)
        signer = attrs.get('signer')
        participants = attrs.get('participants', [])

        if not is_draft:
            if not signer and not participants:
                raise serializers.ValidationError({
                    "participants": "At least one participant is required."
                })

            if participants:
                if len(participants) < 1:
                    raise serializers.ValidationError({
                        "participants": "At least one participant is required."
                    })

                has_signer = any(p.get('role') == 'signer' for p in participants)
                if not has_signer:
                    raise serializers.ValidationError({
                        "participants": "At least one participant must have the 'Signer' role."
                    })

            fields_data = attrs.get('fields', [])
            if fields_data:
                if not isinstance(fields_data, list):
                    raise serializers.ValidationError({"fields": "fields must be a list of field objects."})

                participant_emails = {p.get('email') for p in participants if p.get('email')}
                if signer and signer.get('email'):
                    participant_emails.add(signer.get('email'))

                from services.field_service import validate_field
                for field in fields_data:
                    if not isinstance(field, dict):
                        raise serializers.ValidationError({"fields": "Each field must be an object."})
                    validate_field(field, participant_emails)

        return attrs

    def create(self, validated_data):
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

            from .models import ParticipantToken
            from django.utils import timezone
            from datetime import timedelta

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
                from services.workflow_service import activate_workflow_step
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


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ['owner']





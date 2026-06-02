# pyrefly: ignore [missing-import]
from rest_framework import serializers
import hashlib
from .models import Document, Signer, Envelope, Participant, AuditLog

class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['file']

    def create(self, validated_data):
        file = validated_data['file']
        hasher = hashlib.sha256()
        for chunk in file.chunks():
            hasher.update(chunk)
        file_hash = hasher.hexdigest()
        document = Document.objects.create(file=file, file_hash=file_hash)
        return document
        
class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['name', 'email']

class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ['name', 'email', 'role', 'order', 'step_number', 'status', 'completed_at']

class EnvelopeCreateSerializer(serializers.Serializer):
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
    additional_recipients = serializers.JSONField(required=False, default=list)

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
                raise serializers.ValidationError(f"Invalid email address: {email_str}")
            
            if email_str in seen:
                raise serializers.ValidationError(f"Duplicate recipient email: {email_str}")
            seen.add(email_str)
            validated_emails.append(email_str)
        return validated_emails

    def validate(self, attrs):
        signer = attrs.get('signer')
        participants = attrs.get('participants', [])

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

        return attrs

    def create(self, validated_data):
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

        document = Document.objects.get(id=document_id)
        envelope = Envelope.objects.create(
            document=document,
            signature_page=signature_page,
            signature_x_ratio=signature_x_ratio,
            signature_y_ratio=signature_y_ratio,
            send_reminders=send_reminders,
            send_final_email=send_final_email,
            allow_printing=allow_printing,
            additional_recipients=additional_recipients,
        )

        # Determine the lowest step_number
        step_numbers = [p_data.get('step_number', 1) for p_data in participants_data]
        min_step = min(step_numbers) if step_numbers else 1

        for p_idx, p_data in enumerate(participants_data):
            p_data = p_data.copy()
            order = p_data.pop('order', p_idx + 1)
            
            Participant.objects.create(
                envelope=envelope,
                order=order,
                status='pending',
                **p_data
            )

        # Audit logging for sequential workflow initiation
        AuditLog.objects.create(envelope=envelope, event="Workflow Started")
        AuditLog.objects.create(envelope=envelope, event=f"Step {min_step} Activated")

        # Legacy compatibility helper:
        # When the first participant with role="signer" is added, create the legacy Signer record automatically
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
        from .views import activate_workflow_step
        activate_workflow_step(envelope, min_step)

        return envelope

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from services.upload_service import validate_pdf_upload
from django.utils import timezone
from datetime import timedelta
from rest_framework.generics import get_object_or_404  # pyright: ignore[reportMissingImports]
from django.urls import reverse
import hashlib
import logging
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Envelope, Signer, SigningToken, AuditLog, SignedDocument, Participant, ParticipantToken, Template
from .serializers import DocumentUploadSerializer, EnvelopeCreateSerializer, TemplateSerializer
from django.http import FileResponse, Http404
import os
from services.workflow_service import activate_workflow_step, check_and_advance_step

logger = logging.getLogger(__name__)

def get_token_signer_or_participant(token_str, allow_used=False):
    """
    Resolves token string to either a ParticipantToken or legacy SigningToken,
    validating expiration and use.
    Returns (token_obj, error_msg).
    """
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

def handle_token_error(error_msg):
    if error_msg == "Invalid token.":
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)


class DocumentUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        file = request.data.get('file')
        try:
            validate_pdf_upload(file)
        except ValidationError as e:
            return Response({"file": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DocumentUploadSerializer(data=request.data)
        if serializer.is_valid():
            document = serializer.save()
            return Response(
                {
                    "document_id": document.id,
                    "file_hash": document.file_hash
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EnvelopeCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        is_draft = request.data.get('is_draft', False)
        # ── Mandatory Placement Validation (skipped for drafts) ──────────────
        if not is_draft:
            sig_page = request.data.get('signature_page')
            sig_x = request.data.get('signature_x_ratio')
            sig_y = request.data.get('signature_y_ratio')
            fields = request.data.get('fields', [])

            if not fields and (sig_page is None or sig_x is None or sig_y is None):
                return Response(
                    {"detail": "Signature placement is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = EnvelopeCreateSerializer(data=request.data)
        if serializer.is_valid():
            envelope = serializer.save(owner=request.user)
            return Response(
                {
                    "envelope_id": envelope.id,
                    "status": envelope.status,
                    "send_reminders": envelope.send_reminders,
                    "send_final_email": envelope.send_final_email,
                    "allow_printing": envelope.allow_printing,
                    "additional_recipients": envelope.additional_recipients,
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SendEnvelopeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        expires_at = timezone.now() + timedelta(hours=24)

        # ── Modern participant-based path ──────────────────────────────────
        # Used when the envelope was created via the wizard (draft or direct send).
        participants = envelope.participants.all()
        if participants.exists():
            has_signer = participants.filter(role='signer').exists()
            if not has_signer:
                return Response(
                    {"detail": "At least one participant must have the 'Signer' role."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Activate the first workflow step
            step_numbers = sorted(set(participants.values_list('step_number', flat=True)))
            min_step = step_numbers[0]
            activate_workflow_step(envelope, min_step)

            # Ensure a legacy Signer record exists (required for token resolution)
            first_signer_p = (
                participants.filter(role='signer')
                .order_by('step_number', 'order', 'id')
                .first()
            )
            signer, _ = Signer.objects.get_or_create(
                envelope=envelope,
                defaults={'name': first_signer_p.name, 'email': first_signer_p.email},
            )

        else:
            # ── Legacy Signer path (unchanged) ────────────────────────────
            signer = get_object_or_404(Signer, envelope=envelope)

        # Issue / refresh the signing token (legacy compat, used in response URL)
        signing_token, created = SigningToken.objects.get_or_create(
            signer=signer,
            defaults={"expires_at": expires_at, "is_used": False},
        )
        if not created:
            signing_token.expires_at = expires_at
            signing_token.is_used = False
            signing_token.save()

        envelope.status = "sent"
        envelope.save()

        AuditLog.objects.create(
            envelope=envelope,
            event="sent",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        # Send email notification to first active participant / legacy signer.
        # A failure here must NOT roll back the envelope status change above.
        from services.notification_service import send_package_sent_notifications
        email_warning = None
        try:
            send_package_sent_notifications(envelope, request)
        except Exception:
            logger.exception(
                "Failed to send package notification email for envelope %s",
                envelope.id,
            )
            email_warning = (
                "Package sent successfully, but the notification email could not be delivered."
            )

        from django.conf import settings
        signing_url = f"{settings.FRONTEND_URL}/sign/{signing_token.token}"

        return Response(
            {
                "message": "Envelope sent to signer.",
                "signing_url": signing_url,
                "expires_at": expires_at.isoformat(),
                "email_warning": email_warning,
            },
            status=status.HTTP_200_OK,
        )


class EnvelopePatchView(APIView):
    """
    PATCH /api/envelopes/{id}/

    Updates a draft envelope's participants, fields, and settings in place.
    Only works on envelopes with status='draft' owned by the requesting user.
    Participants and fields are fully replaced on each call.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        if envelope.status != 'draft':
            return Response(
                {'detail': 'Only draft packages can be updated this way.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import Document, DocumentField
        from django.core.validators import validate_email as dj_validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError

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
        }
        for req_key, model_field in simple_map.items():
            if req_key in request.data:
                setattr(envelope, model_field, request.data[req_key])

        # ── additional_recipients ─────────────────────────────────────────
        if 'additional_recipients' in request.data:
            recipients = request.data['additional_recipients']
            if not isinstance(recipients, list):
                return Response(
                    {'additional_recipients': ['Must be a list of email strings.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            validated_recipients = []
            for email in recipients:
                email_str = str(email).strip()
                if not email_str:
                    continue
                try:
                    dj_validate_email(email_str)
                except DjangoValidationError:
                    return Response(
                        {'additional_recipients': [f"Enter a valid email address: '{email_str}'."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                validated_recipients.append(email_str)
            envelope.additional_recipients = validated_recipients

        # ── Optional document update ──────────────────────────────────────
        if 'document_id' in request.data:
            try:
                new_doc = Document.objects.get(id=request.data['document_id'])
                envelope.document = new_doc
            except Document.DoesNotExist:
                return Response(
                    {'document_id': ['Document not found.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        envelope.save()

        # ── Replace participants ───────────────────────────────────────────
        if 'participants' in request.data:
            participants_raw = request.data['participants']
            if not isinstance(participants_raw, list):
                return Response(
                    {'participants': ['Must be a list.']},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate emails before deleting existing records
            for p_data in participants_raw:
                email_str = str(p_data.get('email', '')).strip()
                if email_str:
                    try:
                        dj_validate_email(email_str)
                    except DjangoValidationError:
                        name_str = str(p_data.get('name', '')).strip() or email_str
                        return Response(
                            {'participants': [f"Enter a valid email address for '{name_str}'."]},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            # Replace atomically
            envelope.participants.all().delete()  # cascades ParticipantToken

            from .models import ParticipantToken
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
        if 'fields' in request.data:
            fields_raw = request.data['fields']
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
                        except Exception:
                            pass  # Skip malformed fields during draft saves

        return Response(
            {'envelope_id': envelope.id, 'status': envelope.status},
            status=status.HTTP_200_OK,
        )

class SigningDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return handle_token_error(error_msg)
        
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
            
        document = envelope.document
        if not document.file:
            raise Http404("Document file not found.")
            
        return FileResponse(document.file.open('rb'), content_type='application/pdf')

class SigningSignedDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return handle_token_error(error_msg)
            
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
        
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        return FileResponse(signed_doc.file.open('rb'), content_type='application/pdf')

class SigningDownloadView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return handle_token_error(error_msg)
            
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
        
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        original_name = os.path.basename(signed_doc.file.name) or "signed.pdf"
        
        return FileResponse(
            signed_doc.file.open('rb'),
            as_attachment=True,
            filename=original_name,
            content_type='application/pdf'
        )
   
class SigningView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token)
        if error_msg:
            return handle_token_error(error_msg)
        
        from django.db.models import Max
        is_participant = hasattr(token_obj, 'participant')
        if is_participant:
            participant = token_obj.participant
            envelope = participant.envelope
            role = participant.role
            name = participant.name
            email = participant.email
            p_status = participant.status
            step_num = participant.step_number
            total_steps = envelope.participants.aggregate(max_step=Max('step_number'))['max_step'] or 1
        else:
            signer = token_obj.signer
            envelope = signer.envelope
            role = "signer"
            name = signer.name
            email = signer.email
            step_num = 1
            total_steps = 1
            if envelope.status in ("signed", "completed"):
                p_status = "completed"
            elif envelope.status == "viewed":
                p_status = "viewed"
            else:
                p_status = "active"

        # Check if completed/signed
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" and signed_doc:
            if is_participant and participant.status == 'active':
                participant.status = 'viewed'
                participant.save(update_fields=['status'])
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Participant Viewed",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
                
            # Get fields for this participant
            from services.field_service import get_fields_for_participant
            if is_participant:
                fields_qs = get_fields_for_participant(participant)
            else:
                p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
                fields_qs = get_fields_for_participant(p_rec) if p_rec else []

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

            return Response({
                "signer_name": name,
                "signer_email": email,
                "participant_role": role,
                "participant_status": p_status if not is_participant else participant.status,
                "participant_step": step_num,
                "total_steps": total_steps,
                "document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "signed_document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "envelope_id": envelope.id,
                "status": "completed",
                "fields": fields_list
            })

        # Process viewing transition
        if is_participant:
            if participant.status == 'active':
                participant.status = 'viewed'
                participant.save(update_fields=["status"])
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Participant Viewed",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
        else:
            # Legacy signer viewed
            AuditLog.objects.create(
                envelope=envelope,
                event="viewed",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )
            if envelope.status != "viewed":
                envelope.status = "viewed"
                envelope.save(update_fields=["status"])
                
            # If a participant record exists for this legacy signer's email, mark it viewed too
            p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
            if p_rec and p_rec.status == 'active':
                p_rec.status = 'viewed'
                p_rec.save(update_fields=["status"])

        # Get fields for this participant
        from services.field_service import get_fields_for_participant
        if is_participant:
            fields_qs = get_fields_for_participant(participant)
        else:
            p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
            fields_qs = get_fields_for_participant(p_rec) if p_rec else []

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

        return Response({
            "signer_name": name,
            "signer_email": email,
            "participant_role": role,
            "participant_status": p_status if not is_participant else participant.status,
            "participant_step": step_num,
            "total_steps": total_steps,
            "document_url": request.build_absolute_uri(
                reverse('signing-document', kwargs={'token': token})
            ),
            "envelope_id": envelope.id,
            "status": envelope.status,
            "fields": fields_list
        })







    def post(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token)
        if error_msg:
            return handle_token_error(error_msg)

        is_participant = hasattr(token_obj, 'participant')
        if is_participant:
            participant = token_obj.participant
            envelope = participant.envelope
            role = participant.role
            name = participant.name
            email = participant.email
            p_status = participant.status
        else:
            signer   = token_obj.signer
            envelope = signer.envelope
            role     = "signer"
            name     = signer.name
            email    = signer.email
            p_status = "active"

        # Check if already completed/signed
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" or signed_doc or envelope.status == "declined":
            return Response(
                {
                    "detail": "Envelope already processed or declined.",
                    "status": envelope.status,
                    "signed_document_url": request.build_absolute_uri(
                        reverse('signing-download', kwargs={'token': token})
                    ) if signed_doc else None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce that only active/viewed participants can act
        if is_participant and p_status not in ('active', 'viewed'):
            return Response({"detail": "Workflow stage is not yet active for your role. Actions are restricted."}, status=status.HTTP_400_BAD_REQUEST)

        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")
        action = request.data.get("action")

        # ── Role Actions handling ───────────────────────────────────────────
        if role != "signer":
            allowed_actions = ("approve", "return", "reject")
            if role == "cc":
                allowed_actions = ("acknowledge",)
                
            if action not in allowed_actions:
                return Response({"detail": f"Invalid action '{action}' for role '{role}'."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                if role == "reviewer":
                    if action == "approve":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Reviewer Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                    elif action == "return":
                        participant.status = "returned"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        envelope.status = "declined"
                        envelope.save(update_fields=["status"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Reviewer Returned",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Returned",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                elif role == "approver":
                    if action == "approve":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Approver Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                    elif action == "reject":
                        participant.status = "declined"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        envelope.status = "declined"
                        envelope.save(update_fields=["status"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Approver Rejected",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Rejected",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                elif role == "cc":
                    if action == "acknowledge":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="CC Acknowledged",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                
                # Invalidate token
                token_obj.is_used = True
                token_obj.save(update_fields=["is_used"])

                # Check and advance step if not declined
                if envelope.status != "declined":
                    check_and_advance_step(envelope, participant.step_number, request)

            return Response(
                {
                    "message": f"Action {action} processed successfully.",
                    "envelope_id": envelope.id,
                    "status": envelope.status,
                },
                status=status.HTTP_200_OK,
            )

        # ── Signer Role logic (unchanged PDF embedding) ──────────────────────
        document = envelope.document
        if not document.file:
            return Response(
                {"detail": "Original document file is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sig_type = request.data.get("signature_type", "typed")

        if sig_type == "typed":
            signature_text = request.data.get("signature_text", "").strip()
            if not signature_text:
                return Response(
                    {"detail": "signature_text is required for typed signatures."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            signature_image_b64 = None

        elif sig_type in ("upload", "draw"):
            signature_image_b64 = request.data.get("signature_image", "").strip()
            if not signature_image_b64:
                return Response(
                    {"detail": "signature_image (base64) is required for upload/draw signatures."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            if sig_type == "upload":
                try:
                    b64_data = signature_image_b64
                    if "," in b64_data:
                        b64_data = b64_data.split(",", 1)[1]
                    
                    import base64
                    decoded_bytes = base64.b64decode(b64_data)
                    
                    if len(decoded_bytes) > 2 * 1024 * 1024:
                        return Response(
                            {"detail": "Signature image exceeds maximum allowed size (2MB)."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    
                    from PIL import Image
                    import io
                    try:
                        with Image.open(io.BytesIO(decoded_bytes)) as img:
                            img_format = img.format
                    except Exception:
                        return Response(
                            {"detail": "Unable to parse signature image format."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    
                    if not img_format or img_format.upper() not in ("PNG", "JPEG", "WEBP"):
                        return Response(
                            {"detail": "Unsupported image format. Allowed formats: PNG, JPG, JPEG, WEBP."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except Exception:
                    return Response(
                        {"detail": "Invalid base64 signature image data."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            signature_text = None

        else:
            return Response(
                {"detail": f"Unsupported signature_type: '{sig_type}'. Use 'typed', 'upload', or 'draw'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            document.file.open("rb")
            try:
                original_bytes = document.file.read()
            finally:
                document.file.close()

            final_hash    = hashlib.sha256(original_bytes).hexdigest()
            original_name = document.file.name.rsplit("/", 1)[-1] or "signed.pdf"

            from services.pdf_service import sign_document

            participant_rec = participant if is_participant else Participant.objects.filter(envelope=envelope, email=email).first()
            fields_payload = request.data.get('fields', {})

            try:
                pdf_bytes = sign_document(
                    envelope=envelope,
                    participant_rec=participant_rec,
                    name=name,
                    sig_type=sig_type,
                    signature_text=signature_text,
                    signature_image_b64=signature_image_b64,
                    fields_payload=fields_payload,
                    original_bytes=original_bytes,
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Image/PDF processing failed: {str(e)}", exc_info=True)
                return Response(
                    {"detail": "Unable to process uploaded signature image."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            signed_doc = SignedDocument(envelope=envelope, final_hash=final_hash)
            signed_doc.file.save(original_name, ContentFile(pdf_bytes), save=True)

            token_obj.is_used   = True
            token_obj.expires_at = timezone.now() + timedelta(minutes=15)
            token_obj.save(update_fields=["is_used", "expires_at"])

            if is_participant:
                participant.has_completed = True
                participant.status = 'completed'
                participant.completed_at = timezone.now()
                participant.save(update_fields=["has_completed", "status", "completed_at"])
                current_step = participant.step_number
            else:
                p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
                current_step = 1
                if p_rec:
                    p_rec.has_completed = True
                    p_rec.status = 'completed'
                    p_rec.completed_at = timezone.now()
                    p_rec.save(update_fields=["has_completed", "status", "completed_at"])
                    current_step = p_rec.step_number

            AuditLog.objects.create(
                envelope=envelope,
                event="signed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Signer Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Participant Signed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            p_name = participant.name if is_participant else (p_rec.name if p_rec else name)
            AuditLog.objects.create(
                envelope=envelope,
                event=f"Participant {p_name} Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            check_and_advance_step(envelope, current_step, request)

        return Response(
            {
                "message": "Document signed successfully.",
                "envelope_id": envelope.id,
                "status": envelope.status,
                "signed_document_id": signed_doc.id,
                "signed_document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "download_url": request.build_absolute_uri(
                    reverse('signing-download', kwargs={'token': token})
                ),
            },
            status=status.HTTP_201_CREATED,
        )

class PackageListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        import os
        recent_packages = []
        envelopes = Envelope.objects.filter(owner=request.user).select_related('document', 'signeddocument').prefetch_related('participants').order_by('-created_at')
        
        for env in envelopes:
            participants = env.participants.all().order_by('step_number', 'order', 'id')
            participants_list = []
            current_step = 1
            total_steps = 1
            active_participant = None

            if participants.exists():
                total_steps = max(p.step_number for p in participants)
                
                # Active step: find the step of the participant with status='active' or 'viewed'
                active_p_active = participants.filter(status='active').first()
                active_p_viewed = participants.filter(status='viewed').first()
                active_p = active_p_active or active_p_viewed
                
                if active_p:
                    current_step = active_p.step_number
                    active_participant = {
                        "name": active_p.name,
                        "email": active_p.email,
                        "role": active_p.role,
                        "status": active_p.status
                    }
                else:
                    if all(p.status == 'completed' for p in participants):
                        current_step = total_steps
                    else:
                        first_uncompleted = participants.exclude(status='completed').order_by('step_number').first()
                        if first_uncompleted:
                            current_step = first_uncompleted.step_number
                            active_participant = {
                                "name": first_uncompleted.name,
                                "email": first_uncompleted.email,
                                "role": first_uncompleted.role,
                                "status": first_uncompleted.status
                            }

                for p in participants:
                    participants_list.append({
                        "id": p.id,
                        "name": p.name,
                        "email": p.email,
                        "role": p.role,
                        "step_number": p.step_number,
                        "status": p.status,
                    })
            else:
                signer = Signer.objects.filter(envelope=env).first()
                if signer:
                    if env.status in ("signed", "completed"):
                        status_val = "completed"
                        current_step = 1
                    elif env.status == "viewed":
                        status_val = "viewed"
                        current_step = 1
                        active_participant = {
                            "name": signer.name,
                            "email": signer.email,
                            "role": "signer",
                            "status": "viewed"
                        }
                    else:
                        status_val = "active"
                        current_step = 1
                        active_participant = {
                            "name": signer.name,
                            "email": signer.email,
                            "role": "signer",
                            "status": "active"
                        }
                    participants_list.append({
                        "id": signer.id,
                        "name": signer.name,
                        "email": signer.email,
                        "role": "signer",
                        "step_number": 1,
                        "status": status_val,
                    })

            # Retrieve latest activity timestamp from audit logs
            latest_audit = AuditLog.objects.filter(envelope=env).order_by('-timestamp').first()
            last_activity = latest_audit.timestamp.isoformat() if latest_audit else env.created_at.isoformat()
            
            signed_doc = env.signeddocument if hasattr(env, 'signeddocument') else None
            signed_doc_data = None
            if env.status == 'completed' and signed_doc and signed_doc.file:
                signed_doc_data = {
                    "preview_url": request.build_absolute_uri(
                        reverse('package-signed-preview', kwargs={'pk': env.id})
                    ),
                    "download_url": request.build_absolute_uri(
                        reverse('package-signed-download', kwargs={'pk': env.id})
                    ),
                    "filename": os.path.basename(signed_doc.file.name),
                    "created_at": signed_doc.created_at.isoformat()
                }

            title = env.title or (os.path.basename(env.document.file.name) if env.document.file else f"Package #{env.id}")
            recent_packages.append({
                "id": env.id,
                "title": title,
                "status": env.status,
                "created_at": env.created_at.isoformat(),
                "last_activity": last_activity,
                "current_step": current_step,
                "total_steps": total_steps,
                "active_participant": active_participant,
                "participants": participants_list,
                "signed_document": signed_doc_data,
            })
            
        return Response(recent_packages, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from django.db.models import Count, Q
        import os

        stats = Envelope.objects.filter(owner=request.user).aggregate(
            total_packages=Count('id'),
            draft=Count('id', filter=Q(status='draft')),
            sent=Count('id', filter=Q(status='sent')),
            viewed=Count('id', filter=Q(status='viewed')),
            completed=Count('id', filter=Q(status='completed')),
        )

        awaiting_me = Envelope.objects.filter(
            owner=request.user,
            status__in=['sent', 'viewed'],
            participants__status__in=['active', 'viewed']
        ).distinct().count()

        in_progress = Envelope.objects.filter(
            owner=request.user,
            status__in=['sent', 'viewed']
        ).distinct().count()

        awaiting_others = in_progress

        stats['awaiting_me'] = awaiting_me
        stats['awaiting_others'] = awaiting_others
        stats['in_progress'] = in_progress

        recent_packages = []
        envelopes = Envelope.objects.filter(owner=request.user).select_related('document').annotate(
            p_count=Count('participants')
        ).order_by('-created_at')[:10]
        
        for env in envelopes:
            recent_packages.append({
                "id": env.id,
                "title": env.title or (os.path.basename(env.document.file.name) if env.document.file else f"Envelope #{env.id}"),
                "status": env.status,
                "participants_count": env.p_count,
                "created_at": env.created_at.isoformat(),
            })

        recent_activity = []
        logs = AuditLog.objects.filter(envelope__owner=request.user).select_related('envelope__document').order_by('-timestamp')[:10]
        for log in logs:
            title = log.envelope.title or (os.path.basename(log.envelope.document.file.name) if log.envelope.document.file else f"Envelope #{log.envelope.id}")
            event_desc = f"{log.event.capitalize()} - {title}"
            recent_activity.append({
                "event": event_desc,
                "timestamp": log.timestamp.isoformat(),
            })

        total_templates = Template.objects.filter(owner=request.user).count()
        recent_templates = []
        templates_qs = Template.objects.filter(owner=request.user).order_by('-updated_at')[:5]
        for t in templates_qs:
            recent_templates.append({
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "visibility": t.visibility,
                "updated_at": t.updated_at.isoformat()
            })

        return Response({
            "stats": stats,
            "recent_packages": recent_packages,
            "recent_activity": recent_activity,
            "total_templates": total_templates,
            "recent_templates": recent_templates,
        }, status=status.HTTP_200_OK)

class PackageDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        import os
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        
        doc_data = {
            "id": envelope.document.id,
            "filename": os.path.basename(envelope.document.file.name) if envelope.document.file else "document.pdf",
            "url": request.build_absolute_uri(envelope.document.file.url) if envelope.document.file else ""
        }
        
        participants_list = []
        participants = envelope.participants.all().order_by('step_number', 'order', 'id')
        if participants.exists():
            for p in participants:
                action_url = ""
                token_val = None
                try:
                    if p.token:
                        token_val = p.token.token
                except ParticipantToken.DoesNotExist:
                    pt = ParticipantToken.objects.create(
                        participant=p,
                        expires_at=timezone.now() + timedelta(hours=24),
                        is_used=False
                    )
                    token_val = pt.token
                
                if token_val:
                    from django.conf import settings
                    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
                    action_url = f"{frontend_base}/sign/{token_val}"

                participants_list.append({
                    "id": p.id,
                    "name": p.name,
                    "email": p.email,
                    "role": p.role,
                    "order": p.order,
                    "step_number": p.step_number,
                    "has_completed": p.has_completed,
                    "status": p.status,
                    "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                    "action_url": action_url,
                })
        else:
            signer = Signer.objects.filter(envelope=envelope).first()
            if signer:
                if envelope.status in ("signed", "completed"):
                    status_val = "completed"
                elif envelope.status == "viewed":
                    status_val = "viewed"
                else:
                    status_val = "pending"

                token_obj = SigningToken.objects.filter(signer=signer).first()
                if not token_obj:
                    token_obj = SigningToken.objects.create(
                        signer=signer,
                        expires_at=timezone.now() + timedelta(hours=24),
                        is_used=False
                    )
                token_val = token_obj.token

                action_url = ""
                if token_val:
                    from django.conf import settings
                    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
                    action_url = f"{frontend_base}/sign/{token_val}"

                participants_list.append({
                    "id": signer.id,
                    "name": signer.name,
                    "email": signer.email,
                    "role": "signer",
                    "step_number": 1,
                    "has_completed": envelope.status in ("signed", "completed"),
                    "status": status_val,
                    "completed_at": None,
                    "action_url": action_url,
                })

        audit_trail = []
        logs = AuditLog.objects.filter(envelope=envelope).order_by('-timestamp')
        for log in logs:
            audit_trail.append({
                "event": log.event.capitalize() if log.event else "Activity",
                "timestamp": log.timestamp.isoformat(),
            })
            
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        signed_doc_data = {
            "available": False,
            "preview_url": "",
            "download_url": "",
            "filename": "",
            "created_at": None,
        }
        if signed_doc and signed_doc.file:
            signed_doc_data = {
                "available": True,
                "preview_url": request.build_absolute_uri(
                    reverse('package-signed-preview', kwargs={'pk': envelope.id})
                ),
                "download_url": request.build_absolute_uri(
                    reverse('package-signed-download', kwargs={'pk': envelope.id})
                ),
                "filename": os.path.basename(signed_doc.file.name),
                "created_at": signed_doc.created_at.isoformat(),
            }

        fields_list = []
        for field in envelope.fields.all():
            fields_list.append({
                "id": field.id,
                "field_type": field.field_type,
                "page": field.page,
                "x_ratio": field.x_ratio,
                "y_ratio": field.y_ratio,
                "participant_email": field.participant.email if field.participant else "",
                "participant_name": field.participant.name if field.participant else "",
                "required": field.required,
            })

        title = envelope.title or (os.path.basename(envelope.document.file.name) if envelope.document.file else f"Package #{envelope.id}")

        return Response({
            "id": envelope.id,
            "title": title,
            "description": envelope.description or "",
            "status": envelope.status,
            "created_at": envelope.created_at.isoformat(),
            "document": doc_data,
            "participants": participants_list,
            "audit_trail": audit_trail,
            "signed_document": signed_doc_data,
            "send_reminders": envelope.send_reminders,
            "send_final_email": envelope.send_final_email,
            "allow_printing": envelope.allow_printing,
            "additional_recipients": envelope.additional_recipients,
            "fields": fields_list,
        }, status=status.HTTP_200_OK)
class PackageSignedPreviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
        return FileResponse(signed_doc.file.open('rb'), content_type='application/pdf')

class PackageSignedDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
        original_name = os.path.basename(signed_doc.file.name) or f"signed_package_{pk}.pdf"
        return FileResponse(
            signed_doc.file.open('rb'),
            as_attachment=True,
            filename=original_name,
            content_type='application/pdf'
        )


from rest_framework import generics

class TemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = TemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Template.objects.filter(owner=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Template.objects.filter(owner=self.request.user)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email', '')

        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        if email:
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_email(email)
            except DjangoValidationError:
                return Response({"email": ["Enter a valid email address."]}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, email=email, password=password)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        }, status=status.HTTP_200_OK)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        request.user.auth_token.delete()
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)

class UserMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email
        }, status=status.HTTP_200_OK)


class PackageCertificateDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from esign.models import CompletionCertificate
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        cert = get_object_or_404(CompletionCertificate, envelope=envelope)
        if not cert.file:
            raise Http404("Certificate file not found.")
        filename = os.path.basename(cert.file.name) or f"certificate_package_{pk}.pdf"
        return FileResponse(
            cert.file.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )


class SigningCertificateDownloadView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token, *args, **kwargs):
        from esign.models import CompletionCertificate
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return handle_token_error(error_msg)
            
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
            
        cert = get_object_or_404(CompletionCertificate, envelope=envelope)
        if not cert.file:
            raise Http404("Certificate file not found.")
        filename = os.path.basename(cert.file.name) or f"certificate_{envelope.id}.pdf"
        return FileResponse(
            cert.file.open('rb'),
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )

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
    Delegates to token_service.resolve_token.
    """
    from services.token_service import resolve_token
    return resolve_token(token_str, allow_used)

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
        from services.envelope_service import create_envelope
        result, error = create_envelope(request.data, request.user)
        if error:
            if isinstance(error, str):
                return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class SendEnvelopeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        from services.envelope_service import send_envelope
        result, error = send_envelope(envelope_id, request.user, request)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class EnvelopePatchView(APIView):
    """
    PATCH /api/envelopes/{id}/

    Updates a draft envelope's participants, fields, and settings in place.
    Only works on envelopes with status='draft' owned by the requesting user.
    Participants and fields are fully replaced on each call.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        from services.envelope_service import patch_envelope
        result, error = patch_envelope(pk, request.data, request.user)
        if error:
            if isinstance(error, str):
                return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)

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
        from services.signing_service import get_signing_session_data
        result, error_msg = get_signing_session_data(token, request)
        if error_msg:
            return handle_token_error(error_msg)
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request, token, *args, **kwargs):
        from services.signing_service import process_action
        result, error_msg = process_action(token, request.data, request)
        if error_msg:
            if error_msg == "ALREADY_PROCESSED":
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
            return handle_token_error(error_msg)
        
        # Determine success status code based on the action
        action = request.data.get("action")
        if action in ("view", "approve", "return", "reject", "acknowledge"):
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_201_CREATED)

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
                "email_otp_required": env.email_otp_required,
                "sms_otp_required": env.sms_otp_required,
                "national_id_required": env.national_id_required,
                "face_biometric_required": env.face_biometric_required,
                "representative_match_required": env.representative_match_required,
                "terms_acceptance_required": env.terms_acceptance_required,
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
            "email_otp_required": envelope.email_otp_required,
            "sms_otp_required": envelope.sms_otp_required,
            "national_id_required": envelope.national_id_required,
            "face_biometric_required": envelope.face_biometric_required,
            "representative_match_required": envelope.representative_match_required,
            "terms_acceptance_required": envelope.terms_acceptance_required,
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

        with transaction.atomic():
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


class ContractAnalyzeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        import time
        import fitz
        import logging
        from services.ocr_service import (
            extract_text_from_pdf,
            extract_text_from_image
        )
        from services.authority_extraction_service import analyze_contract_authority

        logger = logging.getLogger(__name__)
        start_time = time.perf_counter()

        file_obj = request.data.get('file')
        if not file_obj:
            return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        filename = (file_obj.name or "").lower()
        if not (filename.endswith('.pdf') or filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg')):
            return Response(
                {"detail": "Unsupported file format. Only PDF, PNG, JPG, and JPEG are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. File size validation (Resource protection: Max 20MB)
        MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
        if file_obj.size > MAX_FILE_SIZE_BYTES:
            return Response(
                {"detail": "File size exceeds the 20MB limit."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            file_bytes = file_obj.read()
            
            # Determine logic based on file type
            if filename.endswith('.pdf'):
                # 2. PDF Page count validation (Resource protection: Max 20 pages)
                try:
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    page_count = len(doc)
                    doc.close()
                except Exception as e:
                    return Response(
                        {"detail": f"Failed to parse PDF pages: {str(e)}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if page_count > 20:
                    return Response(
                        {"detail": f"PDF exceeds the maximum limit of 20 pages (found {page_count})."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                ocr_result = extract_text_from_pdf(file_bytes)
                raw_text = ocr_result["raw_text"]
                english_text = ocr_result.get("english_text", raw_text)
                arabic_text = ocr_result.get("arabic_text", raw_text)
                ocr_confidence = ocr_result["ocr_confidence"]
                source = ocr_result["extraction_source"]
                page_count = ocr_result.get("page_count", page_count)
                digital_extraction_ms = ocr_result.get("digital_extraction_ms", 0.0)
                ocr_ms = ocr_result.get("ocr_ms", 0.0)
                dominant_strategy = ocr_result.get("dominant_strategy", source)
                page_strategies = ocr_result.get("page_strategies", {1: source})
                page_quality_scores = ocr_result.get("page_quality_scores", {1: 1.0})
                dominant_arabic_region = ocr_result.get("dominant_arabic_region", "right")
                page_regions = ocr_result.get("page_regions", {1: "right"})
            else:
                # Image processing
                logger.info("Processing image upload using OCR")
                t_ocr_start = time.perf_counter()
                raw_text, ocr_confidence = extract_text_from_image(file_bytes)
                ocr_ms = (time.perf_counter() - t_ocr_start) * 1000
                digital_extraction_ms = 0.0
                english_text = raw_text
                arabic_text = raw_text
                source = "paddleocr"
                page_count = 1
                dominant_strategy = "full_page_ocr"
                page_strategies = {1: "full_page_ocr"}
                page_quality_scores = {1: 0.0}
                dominant_arabic_region = "right"
                page_regions = {1: "right"}
                ocr_result = {
                    "ocr_provider": "paddle",
                    "ocr_confidence": ocr_confidence,
                    "fallback_used": False,
                    "ocr_ms": ocr_ms
                }

            # Extract Authority Information
            print("\n========== RAW OCR TEXT ==========")
            print(raw_text.encode('ascii', errors='backslashreplace').decode('ascii'))
            print("==================================\n")
            
            t_auth_start = time.perf_counter()
            analysis = analyze_contract_authority(raw_text, english_text=english_text, arabic_text=arabic_text)
            authority_extraction_ms = (time.perf_counter() - t_auth_start) * 1000

            end_time = time.perf_counter()
            total_processing_ms = (end_time - start_time) * 1000

            extraction_result = ocr_result

            # ── Get or resolve envelope_id ────────────────────────────────────
            envelope_id = request.data.get('envelope_id') or request.query_params.get('envelope_id')
            envelope = None
            if envelope_id:
                try:
                    envelope = Envelope.objects.get(id=envelope_id)
                except Envelope.DoesNotExist:
                    return Response({"detail": f"Envelope with ID {envelope_id} not found."}, status=status.HTTP_404_NOT_FOUND)

            # ── Generate candidates ──────────────────────────────────────────
            candidates_data = []
            if envelope:
                from services.recipient_discovery_service import generate_candidates
                candidates = generate_candidates(envelope, analysis)
                for cand in candidates:
                    candidates_data.append({
                        "id": cand.id,
                        "name_en": cand.name_en,
                        "name_ar": cand.name_ar,
                        "title_en": cand.title_en,
                        "title_ar": cand.title_ar,
                        "status": cand.status,
                        "converted_at": cand.converted_at.isoformat() if cand.converted_at else None,
                        "ignored_at": cand.ignored_at.isoformat() if cand.ignored_at else None,
                        "authority_clause": cand.authority_clause
                    })
                
                # Create compliance audit log record
                from esign.models import ContractAnalysisAudit
                ContractAnalysisAudit.objects.update_or_create(
                    envelope=envelope,
                    defaults={
                        "representative_name": f"{analysis.get('representative_name_en', '')} / {analysis.get('representative_name_ar', '')}".strip(" /"),
                        "representative_title": f"{analysis.get('title_en', '')} / {analysis.get('title_ar', '')}".strip(" /"),
                        "authority_clause": f"{analysis.get('authority_clause_en', '')} / {analysis.get('authority_clause_ar', '')}".strip(" /"),
                        "authority_detected": bool(analysis.get("representative_name_en") or analysis.get("representative_name_ar")),
                        "ocr_provider": extraction_result.get("ocr_provider", ""),
                        "ocr_confidence": extraction_result.get("ocr_confidence"),
                    }
                )
            else:
                # In-memory candidate generation (e.g. for ContractAnalysisPage demo)
                name_en = analysis.get("representative_name_en", "").strip()
                name_ar = analysis.get("representative_name_ar", "").strip()
                title_en = analysis.get("title_en", "").strip()
                title_ar = analysis.get("title_ar", "").strip()
                clause_en = analysis.get("authority_clause_en", "").strip()
                clause_ar = analysis.get("authority_clause_ar", "").strip()

                from services.recipient_discovery_service import TITLE_MAP_EN_TO_AR
                is_same = False
                if name_en and name_ar:
                    mapped_ar_title = TITLE_MAP_EN_TO_AR.get(title_en)
                    if mapped_ar_title == title_ar or (title_en.lower() == "ceo" and title_ar == "الرئيس التنفيذي"):
                        is_same = True
                    else:
                        is_same = True

                if is_same:
                    candidates_data.append({
                        "id": "temp-1",
                        "name_en": name_en,
                        "name_ar": name_ar,
                        "title_en": title_en,
                        "title_ar": title_ar,
                        "status": "pending",
                        "converted_at": None,
                        "ignored_at": None,
                        "authority_clause": clause_en or clause_ar
                    })
                else:
                    if name_en:
                        candidates_data.append({
                            "id": "temp-1",
                            "name_en": name_en,
                            "name_ar": "",
                            "title_en": title_en,
                            "title_ar": "",
                            "status": "pending",
                            "converted_at": None,
                            "ignored_at": None,
                            "authority_clause": clause_en
                        })
                    if name_ar:
                        candidates_data.append({
                            "id": "temp-2",
                            "name_en": "",
                            "name_ar": name_ar,
                            "title_en": "",
                            "title_ar": title_ar,
                            "status": "pending",
                            "converted_at": None,
                            "ignored_at": None,
                            "authority_clause": clause_ar
                        })

            representatives_found = len(candidates_data) > 0
            response_data = {
                "representative_name_en": analysis.get("representative_name_en", ""),
                "representative_name_ar": analysis.get("representative_name_ar", ""),
                "title_en": analysis.get("title_en", ""),
                "title_ar": analysis.get("title_ar", ""),
                "authority_clause_en": analysis.get("authority_clause_en", ""),
                "authority_clause_ar": analysis.get("authority_clause_ar", ""),
                "representatives_found": representatives_found,
                "authority_detected": representatives_found,
                "count": len(candidates_data),
                "candidates": candidates_data
            }

            # BENCHMARK DEBUG ONLY
            # TEMPORARY INSTRUMENTATION
            # SAFE TO REMOVE AFTER OCR TUNING
            ENABLE_EXTRACTION_DEBUG = os.getenv("ENABLE_EXTRACTION_DEBUG", "false").lower() == "true"
            if ENABLE_EXTRACTION_DEBUG:
                try:
                    debug_dir = os.getenv("EXTRACTION_DEBUG_DIR", "./analysis/debug_responses/")
                    os.makedirs(debug_dir, exist_ok=True)
                    
                    # Extract representative contexts (±150 chars)
                    def get_context(text, keyword_or_name):
                        if not text or not keyword_or_name:
                            return ""
                        idx = text.lower().find(str(keyword_or_name).lower())
                        if idx == -1:
                            return ""
                        start = max(0, idx - 150)
                        end = min(len(text), idx + len(str(keyword_or_name)) + 150)
                        return text[start:end]
                    
                    target_name_en = analysis["representative_name_en"]
                    kw_en = target_name_en if target_name_en else "represented"
                    context_en = get_context(english_text, kw_en)
                    
                    target_name_ar = analysis["representative_name_ar"]
                    kw_ar = target_name_ar if target_name_ar else "ويمثلها"
                    context_ar = get_context(arabic_text, kw_ar)
                    
                    debug_filename = os.path.splitext(os.path.basename(file_obj.name))[0] + "_debug.json"
                    debug_filepath = os.path.join(debug_dir, debug_filename)
                    
                    debug_payload = {
                        "raw_text": raw_text,
                        "english_text": english_text,
                        "arabic_text": arabic_text,
                        "representative_name_en": analysis["representative_name_en"],
                        "representative_name_ar": analysis["representative_name_ar"],
                        "title_en": analysis["title_en"],
                        "title_ar": analysis["title_ar"],
                        "authority_phrase_en": analysis["authority_clause_en"],
                        "authority_phrase_ar": analysis["authority_clause_ar"],
                        "confidence_score": analysis["confidence_score"],
                        "name_similarity_score": analysis.get("name_similarity_score", 0.0),
                        "title_match_score_en": analysis.get("title_match_score_en", 0.0),
                        "title_match_score_ar": analysis.get("title_match_score_ar", 0.0),
                        "title_match_method_en": analysis.get("title_match_method_en", "none"),
                        "title_match_method_ar": analysis.get("title_match_method_ar", "none"),
                        "page_count": page_count,
                        "page_regions": page_regions if 'page_regions' in locals() else {},
                        "page_quality_scores": page_quality_scores if 'page_quality_scores' in locals() else {},
                        "page_strategies": page_strategies if 'page_strategies' in locals() else {},
                        "ocr_confidence": ocr_confidence,
                        "processing_time_ms": total_processing_ms,
                        "representative_context_en": context_en,
                        "representative_context_ar": context_ar,
                        "requested_provider": os.getenv("OCR_PROVIDER", "paddle").strip(),
                        "ocr_provider": extraction_result.get("ocr_provider"),
                        "fallback_used": extraction_result.get("fallback_used"),
                        "ocr_ms": extraction_result.get("ocr_ms"),
                        "api_response": response_data
                    }
                    
                    import json
                    with open(debug_filepath, "w", encoding="utf-8") as df:
                        json.dump(debug_payload, df, ensure_ascii=False, indent=2)
                        
                except Exception as ex:
                    logger.error(f"[Benchmark Debug] Failed to save debug JSON: {ex}")

            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Failed to analyze contract: {str(e)}", exc_info=True)
            return Response({"detail": f"Failed to analyze contract: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmCandidatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        from esign.models import Envelope, RepresentativeCandidate
        from services.recipient_discovery_service import convert_candidate_to_recipient
        from django.shortcuts import get_object_or_404
        
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        candidate_ids = request.data.get("candidate_ids", [])
        
        if not isinstance(candidate_ids, list):
            return Response({"detail": "candidate_ids must be a list of IDs."}, status=status.HTTP_400_BAD_REQUEST)
            
        participants_created = []
        for c_id in candidate_ids:
            try:
                candidate = RepresentativeCandidate.objects.get(id=c_id, envelope=envelope)
                participant = convert_candidate_to_recipient(candidate)
                if participant:
                    participants_created.append(participant)
            except RepresentativeCandidate.DoesNotExist:
                continue
                
        # Return updated list of participants for this envelope
        from esign.serializers import ParticipantSerializer
        participants = envelope.participants.all().order_by('step_number', 'order', 'id')
        serializer = ParticipantSerializer(participants, many=True)
        
        return Response({
            "message": f"Successfully confirmed {len(participants_created)} candidates.",
            "participants": serializer.data
        }, status=status.HTTP_200_OK)


class IgnoreCandidatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        from esign.models import Envelope, RepresentativeCandidate
        from services.recipient_discovery_service import ignore_candidate
        from django.shortcuts import get_object_or_404
        
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        candidate_ids = request.data.get("candidate_ids", [])
        
        if not isinstance(candidate_ids, list):
            return Response({"detail": "candidate_ids must be a list of IDs."}, status=status.HTTP_400_BAD_REQUEST)
            
        candidates_ignored = []
        for c_id in candidate_ids:
            try:
                candidate = RepresentativeCandidate.objects.get(id=c_id, envelope=envelope)
                ignored_cand = ignore_candidate(candidate)
                if ignored_cand:
                    candidates_ignored.append(ignored_cand.id)
            except RepresentativeCandidate.DoesNotExist:
                continue
                
        return Response({
            "message": f"Successfully ignored {len(candidates_ignored)} candidates.",
            "candidate_ids": candidates_ignored
        }, status=status.HTTP_200_OK)


def check_participant_authorization(request, participant_id):
    """
    Validates authorization for a participant.
    Returns (participant, token_obj, error_response) tuple.
    If authorized, error_response is None.
    """
    from esign.models import Participant
    from services.token_service import resolve_token
    
    try:
        participant = Participant.objects.get(id=participant_id)
    except Participant.DoesNotExist:
        return None, None, Response({"detail": "Participant not found."}, status=status.HTTP_404_NOT_FOUND)
        
    # Check owner access
    if request.user and request.user.is_authenticated:
        if participant.envelope.owner == request.user:
            return participant, None, None
            
    # Check token access
    token_str = request.headers.get('X-Participant-Token') or request.query_params.get('token')
    if not token_str:
        return None, None, Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_403_FORBIDDEN)
        
    token_obj, error_msg = resolve_token(token_str, allow_used=True)
    if error_msg:
        return None, None, Response({"detail": error_msg}, status=status.HTTP_403_FORBIDDEN)
        
    # Verify token matches this participant
    from esign.models import ParticipantToken, SigningToken
    if isinstance(token_obj, ParticipantToken):
        if token_obj.participant != participant:
            return None, None, Response({"detail": "Token does not match the requested participant."}, status=status.HTTP_403_FORBIDDEN)
    elif isinstance(token_obj, SigningToken):
        if token_obj.signer.email != participant.email or token_obj.signer.envelope != participant.envelope:
            return None, None, Response({"detail": "Token does not match the requested participant."}, status=status.HTTP_403_FORBIDDEN)
            
    return participant, token_obj, None


def validate_image_file(file_obj):
    """
    Validates file type and size under ASVS Level 2 guidelines.
    """
    if not file_obj:
        raise ValidationError("No file uploaded.")
        
    # 1. Size check: Max 5MB
    MAX_SIZE = 5 * 1024 * 1024
    if file_obj.size > MAX_SIZE:
        raise ValidationError("Image size exceeds the 5MB limit.")
        
    # 2. Extension check
    filename = (file_obj.name or "").lower()
    if not (filename.endswith('.jpg') or filename.endswith('.jpeg') or filename.endswith('.png')):
        raise ValidationError("Unsupported file format. Only JPG, JPEG, and PNG are supported.")
        
    # 3. Mime type check
    content_type = getattr(file_obj, 'content_type', None)
    if content_type and content_type not in ('image/jpeg', 'image/jpg', 'image/png'):
        raise ValidationError("Invalid image type. Only JPG, JPEG, and PNG are supported.")

    # 4. Integrity check via PIL
    from PIL import Image
    try:
        # Seek to beginning in case file has been read
        file_obj.seek(0)
        img = Image.open(file_obj)
        img.verify()
        file_obj.seek(0)
    except Exception:
        raise ValidationError("Invalid image format or corrupted image.")


class SignerVerificationIDView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        national_id_number = request.data.get('national_id_number')
        if not national_id_number or not str(national_id_number).strip():
            return Response({"detail": "national_id_number is required."}, status=status.HTTP_400_BAD_REQUEST)

        front_image = request.data.get('front_image')
        back_image = request.data.get('back_image')

        if not front_image or not back_image:
            return Response({"detail": "Both front_image and back_image are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_image_file(front_image)
            validate_image_file(back_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        from services.signer_verification_service import upload_national_id
        from esign.serializers import SignerVerificationSerializer

        verification = upload_national_id(participant, str(national_id_number).strip(), front_image, back_image)
        serializer = SignerVerificationSerializer(verification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignerVerificationSelfieView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        selfie_image = request.data.get('selfie_image')
        if not selfie_image:
            return Response({"detail": "selfie_image is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_image_file(selfie_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        from esign.models import SignerVerification
        verification_exists = SignerVerification.objects.filter(participant=participant).first()
        if not verification_exists or verification_exists.status == 'pending':
            return Response({"detail": "National ID must be uploaded before uploading selfie."}, status=status.HTTP_400_BAD_REQUEST)

        from services.signer_verification_service import upload_selfie
        from esign.serializers import SignerVerificationSerializer

        verification = upload_selfie(participant, selfie_image)
        serializer = SignerVerificationSerializer(verification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignerVerificationDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        from esign.models import SignerVerification
        from esign.serializers import SignerVerificationSerializer

        verification = SignerVerification.objects.filter(participant=participant).first()
        if not verification:
            return Response({
                "status": "pending",
                "verified_at": None,
                "masked_national_id": ""
            }, status=status.HTTP_200_OK)

        serializer = SignerVerificationSerializer(verification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignerVerificationIDExtractView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        from esign.models import SignerVerification
        verification = SignerVerification.objects.filter(participant=participant).first()
        if not verification or not verification.national_id_front:
            return Response(
                {"detail": "Front ID image is required. Please upload the National ID front image first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Log OCR started event
        from esign.constants import EVENT_ID_OCR_STARTED
        from esign.models import VerificationEvent
        VerificationEvent.objects.create(
            signer_verification=verification,
            event_type=EVENT_ID_OCR_STARTED,
            metadata={}
        )

        from services.national_identity_service import (
            extract_identity_data,
            parse_identity_document,
            save_identity_data
        )

        try:
            front_image = verification.national_id_front
            back_image = verification.national_id_back

            ocr_result = extract_identity_data(front_image, back_image)

            if not ocr_result or not ocr_result.get("raw_text", "").strip():
                save_identity_data(
                    verification,
                    ocr_result=ocr_result,
                    parsed_fields={},
                    extraction_status="failed",
                    failure_reason="no_text_detected"
                )
                return Response(
                    {"detail": "OCR extraction failed: No text detected on the identity document."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Parse fields
            parsed_fields = parse_identity_document(ocr_result["raw_text"])

            # Save extracted metadata
            national_identity = save_identity_data(
                verification,
                ocr_result=ocr_result,
                parsed_fields=parsed_fields,
                extraction_status="success"
            )

            return Response({
                "full_name": national_identity.full_name,
                "masked_national_id": national_identity.masked_national_id,
                "date_of_birth": national_identity.date_of_birth.isoformat() if national_identity.date_of_birth else None,
                "expiry_date": national_identity.expiry_date.isoformat() if national_identity.expiry_date else None,
                "document_type": national_identity.document_type
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Azure OCR extraction encountered an error.")

            save_identity_data(
                verification,
                ocr_result=None,
                parsed_fields={},
                extraction_status="failed",
                failure_reason="azure_error"
            )
            return Response(
                {"detail": f"OCR extraction failed due to Azure service error: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )



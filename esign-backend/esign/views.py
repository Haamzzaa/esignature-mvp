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
from esign.config import esign_config
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Envelope, Signer, SigningToken, AuditLog, SignedDocument, Participant, ParticipantToken, Template
from .serializers import DocumentUploadSerializer, EnvelopeCreateSerializer, TemplateSerializer
from django.http import FileResponse, Http404
import os
from services.workflow_service import activate_workflow_step, check_and_advance_step

logger = logging.getLogger(__name__)

from services.rate_limiting_service import (
    check_rate_limit,
    check_otp_lockout,
    register_otp_failed_attempt,
    reset_otp_failed_attempts,
    get_client_ip
)

def make_rate_limited_response(retry_after):
    response = Response(
        {
            "detail": f"Too many requests. Please try again in {retry_after} seconds.",
            "retry_after": retry_after
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS
    )
    response['Retry-After'] = str(retry_after)
    return response

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
            document = serializer.save(owner=request.user)
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
            if isinstance(error, list):
                return Response({"errors": error}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class EnvelopeReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, envelope_id, *args, **kwargs):
        import os
        from django.utils import timezone
        from datetime import timedelta
        from esign.config import esign_config
        
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        
        # 1. Document preview
        doc_data = {
            "id": envelope.document.id if envelope.document else None,
            "filename": os.path.basename(envelope.document.file.name) if (envelope.document and envelope.document.file) else "document.pdf",
            "url": request.build_absolute_uri(envelope.document.file.url) if (envelope.document and envelope.document.file) else ""
        }
        
        # 2. Expiration Date & Workflow type
        expires_at = timezone.now() + timedelta(hours=esign_config.signing_link_expiry)
        
        participants = envelope.participants.all().order_by('step_number', 'order', 'id')
        unique_steps = set(participants.values_list('step_number', flat=True))
        workflow_type = "Sequential" if len(unique_steps) > 1 else "Parallel"
        
        # 3. Build participant list with roles, signing order, verification methods, and fields summary
        participants_list = []
        for p in participants:
            verification_methods = []
            if p.role == 'signer':
                if envelope.email_otp_required:
                    verification_methods.append("Email OTP")
                if envelope.sms_otp_required:
                    verification_methods.append("SMS OTP")
                if envelope.national_id_required:
                    verification_methods.append("National ID Verification")
                if envelope.face_biometric_required:
                    verification_methods.append("Face Biometric Match")
                if envelope.representative_match_required:
                    verification_methods.append("Representative Match")
                if envelope.terms_acceptance_required:
                    verification_methods.append("Terms Acceptance")
            
            placed_fields_count = envelope.fields.filter(participant=p).count()
            
            participants_list.append({
                "id": p.id,
                "name": p.name,
                "email": p.email,
                "role": p.role,
                "order": p.order,
                "step_number": p.step_number,
                "verification_methods": verification_methods,
                "placed_fields_count": placed_fields_count,
            })
            
        # 4. Expiration date & reminder settings
        reminder_settings = {
            "send_reminders": envelope.send_reminders,
            "send_final_email": envelope.send_final_email,
            "allow_printing": envelope.allow_printing,
        }
        
        # 5. Run send validation
        from services.envelope_service import validate_envelope_for_send
        is_valid, validation_errors = validate_envelope_for_send(envelope)
        
        return Response({
            "envelope_id": envelope.id,
            "title": envelope.title or (os.path.basename(envelope.document.file.name) if (envelope.document and envelope.document.file) else f"Package #{envelope.id}"),
            "description": envelope.description or "",
            "sender": envelope.owner.email or envelope.owner.username if envelope.owner else "",
            "document": doc_data,
            "participants": participants_list,
            "workflow_type": workflow_type,
            "expiration_date": expires_at.isoformat(),
            "reminder_settings": reminder_settings,
            "is_valid": is_valid,
            "validation_errors": validation_errors,
        }, status=status.HTTP_200_OK)


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
        from services.media_auth_service import check_media_authorization
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
            
        authorized, auth_err, _ = check_media_authorization(
            request,
            document.file.name,
            token_str=str(token),
            expected_envelope=envelope
        )
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        return stream_protected_file(document.file.name)

class SigningSignedDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        from services.media_auth_service import check_media_authorization
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
            
        authorized, auth_err, _ = check_media_authorization(request, signed_doc.file.name, token_str=str(token))
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        return stream_protected_file(signed_doc.file.name)

class SigningDownloadView(APIView):
    def get(self, request, token, *args, **kwargs):
        from services.media_auth_service import check_media_authorization
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
            
        authorized, auth_err, _ = check_media_authorization(request, signed_doc.file.name, token_str=str(token))
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        original_name = os.path.basename(signed_doc.file.name) or "signed.pdf"
        return stream_protected_file(signed_doc.file.name, as_attachment=True, filename=original_name)
   
class SigningView(APIView):
    def get(self, request, token, *args, **kwargs):
        from services.signing_service import get_signing_session_data
        result, error_msg = get_signing_session_data(token, request)
        if error_msg:
            return handle_token_error(error_msg)
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request, token, *args, **kwargs):
        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("signing_ip", ip, esign_config.rate_limit_signing, "signing")
        if is_limited:
            return make_rate_limited_response(retry_after)
            
        is_limited, _, retry_after = check_rate_limit("signing_token", token, esign_config.rate_limit_signing, "signing")
        if is_limited:
            return make_rate_limited_response(retry_after)

        from services.signing_service import process_action
        result, error_msg = process_action(token, request.data, request)
        if error_msg:
            if error_msg == "ALREADY_PROCESSED":
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
            if error_msg in ("AUTHORIZATION_REQUIRED", "IDENTITY_OCR_FAILED", "BIOMETRIC_FAILED", "AUTHORIZATION_FAILED", "MANUAL_REVIEW_REQUIRED"):
                return Response(result, status=status.HTTP_403_FORBIDDEN)
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
                        expires_at=timezone.now() + timedelta(hours=esign_config.signing_link_expiry),
                        is_used=False
                    )
                    token_val = pt.token
                
                if token_val:
                    frontend_base = esign_config.frontend_url
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
                        expires_at=timezone.now() + timedelta(hours=esign_config.signing_link_expiry),
                        is_used=False
                    )
                token_val = token_obj.token

                action_url = ""
                if token_val:
                    frontend_base = esign_config.frontend_url
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
        from services.media_auth_service import check_media_authorization
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        authorized, auth_err, _ = check_media_authorization(request, signed_doc.file.name)
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        return stream_protected_file(signed_doc.file.name)

class PackageSignedDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from services.media_auth_service import check_media_authorization
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        authorized, auth_err, _ = check_media_authorization(request, signed_doc.file.name)
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        original_name = os.path.basename(signed_doc.file.name) or f"signed_package_{pk}.pdf"
        return stream_protected_file(signed_doc.file.name, as_attachment=True, filename=original_name)


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

        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("login_ip", ip, esign_config.rate_limit_login, "login")
        if is_limited:
            return make_rate_limited_response(retry_after)

        if username:
            is_limited, _, retry_after = check_rate_limit("login_username", username, esign_config.rate_limit_login, "login")
            if is_limited:
                return make_rate_limited_response(retry_after)

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
        from services.media_auth_service import check_media_authorization
        
        envelope = get_object_or_404(Envelope, id=pk, owner=request.user)
        cert = get_object_or_404(CompletionCertificate, envelope=envelope)
        if not cert.file:
            raise Http404("Certificate file not found.")
            
        authorized, auth_err, _ = check_media_authorization(request, cert.file.name)
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        filename = os.path.basename(cert.file.name) or f"certificate_package_{pk}.pdf"
        return stream_protected_file(cert.file.name, as_attachment=True, filename=filename)


class SigningCertificateDownloadView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token, *args, **kwargs):
        from esign.models import CompletionCertificate
        from services.media_auth_service import check_media_authorization
        
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
            
        authorized, auth_err, _ = check_media_authorization(request, cert.file.name, token_str=str(token))
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)
            
        filename = os.path.basename(cert.file.name) or f"certificate_{envelope.id}.pdf"
        return stream_protected_file(cert.file.name, as_attachment=True, filename=filename)


class ContractAnalyzeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("contract_analyze_ip", ip, esign_config.rate_limit_contract_analysis, "contract_analyze")
        if is_limited:
            return make_rate_limited_response(retry_after)

        import time
        import fitz
        import logging
        from services.ocr_service import extract_text_from_image
        from esign.providers.registry import esign_provider_registry
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

        MAX_FILE_SIZE_BYTES = esign_config.max_upload_size
        if file_obj.size > MAX_FILE_SIZE_BYTES:
            return Response(
                {"detail": f"File size exceeds the {esign_config.max_upload_size // (1024 * 1024)}MB limit."},
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

                ocr_result = esign_provider_registry.ocr_provider.extract_text(file_bytes)
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
            logger.debug("[ContractAnalyzeView] Raw OCR text (ASCII-safe): %s",
                         raw_text.encode('ascii', errors='backslashreplace').decode('ascii'))
            
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
                    logger.warning(f"Contract analysis failed: Envelope {envelope_id} not found.")
                    return Response({"detail": f"Envelope with ID {envelope_id} not found."}, status=status.HTTP_404_NOT_FOUND)
                
                # Check envelope ownership
                if not request.user or not request.user.is_authenticated or envelope.owner != request.user:
                    logger.warning(f"Unauthorized contract analysis attempt on envelope {envelope_id} by user {request.user}")
                    return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

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
            return Response({"detail": "An internal error occurred while processing the document."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    from django.utils import timezone
    import logging

    logger = logging.getLogger(__name__)

    try:
        participant = Participant.objects.get(id=participant_id)
    except Participant.DoesNotExist:
        logger.warning(f"Authorization denied: Participant {participant_id} not found.")
        return None, None, Response({"detail": "Participant not found."}, status=status.HTTP_404_NOT_FOUND)
        
    envelope = participant.envelope

    # Check owner access (GET only)
    is_owner = False
    if request.user and request.user.is_authenticated:
        if envelope.owner == request.user:
            is_owner = True

    if request.method == 'GET' and is_owner:
        # Owner can view verification detail/status without token
        return participant, None, None

    # Check token access
    token_str = request.headers.get('X-Participant-Token') or request.query_params.get('token')
    if not token_str:
        logger.warning(f"Authorization denied: Authentication credentials were not provided for participant {participant_id}.")
        return None, None, Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_403_FORBIDDEN)
        
    allow_used = (request.method == 'GET')
    token_obj, error_msg = resolve_token(token_str, allow_used=allow_used)
    if error_msg:
        logger.warning(f"Authorization denied: Token resolution failed for participant {participant_id}: {error_msg}")
        return None, None, Response({"detail": error_msg}, status=status.HTTP_403_FORBIDDEN)
        
    # Verify token matches this participant
    from esign.models import ParticipantToken, SigningToken
    if isinstance(token_obj, ParticipantToken):
        if token_obj.participant != participant:
            logger.warning(f"Authorization denied: Token does not match participant {participant_id}.")
            return None, None, Response({"detail": "Token does not match the requested participant."}, status=status.HTTP_403_FORBIDDEN)
    elif isinstance(token_obj, SigningToken):
        if token_obj.signer.email != participant.email or token_obj.signer.envelope != envelope:
            logger.warning(f"Authorization denied: Token does not match participant {participant_id}.")
            return None, None, Response({"detail": "Token does not match the requested participant."}, status=status.HTTP_403_FORBIDDEN)
    else:
        logger.warning(f"Authorization denied: Invalid token type for participant {participant_id}.")
        return None, None, Response({"detail": "Invalid token type."}, status=status.HTTP_403_FORBIDDEN)

    # For mutating requests (POST), perform strict checks on token/envelope/participant state
    if request.method != 'GET':
        # Check token expiration
        if token_obj.expires_at < timezone.now():
            logger.warning(f"Authorization denied: Token expired for participant {participant_id}.")
            return None, None, Response({"detail": "This signing link has expired."}, status=status.HTTP_403_FORBIDDEN)

        # Check token used
        if token_obj.is_used:
            logger.warning(f"Authorization denied: Token already used for participant {participant_id}.")
            return None, None, Response({"detail": "Your step has already been completed."}, status=status.HTTP_403_FORBIDDEN)

        # Check envelope status
        if envelope.status == "completed":
            logger.warning(f"Authorization denied: Envelope {envelope.id} already completed.")
            return None, None, Response({"detail": "This package has already been completed."}, status=status.HTTP_400_BAD_REQUEST)
        if envelope.status not in ("sent", "viewed"):
            logger.warning(f"Authorization denied: Envelope {envelope.id} has invalid status '{envelope.status}'.")
            return None, None, Response({"detail": f"Envelope status '{envelope.status}' does not allow this action."}, status=status.HTTP_400_BAD_REQUEST)

        # Check participant completion
        if participant.has_completed or participant.status in ('completed', 'declined', 'returned'):
            logger.warning(f"Authorization denied: Participant {participant_id} already completed/declined/returned.")
            return None, None, Response({"detail": "Your step has already been completed."}, status=status.HTTP_400_BAD_REQUEST)

        # Check workflow stage (active/viewed check)
        if participant.status not in ('active', 'viewed'):
            logger.warning(f"Authorization denied: Participant {participant_id} is in status '{participant.status}' (not active/viewed).")
            return None, None, Response({"detail": "Workflow stage is not yet active for your role. Actions are restricted."}, status=status.HTTP_400_BAD_REQUEST)
            
    return participant, token_obj, None


def validate_image_file(file_obj):
    """
    Validates file type and size under ASVS Level 2 guidelines.
    """
    if not file_obj:
        raise ValidationError("No file uploaded.")
        
    MAX_SIZE = esign_config.max_image_size
    if file_obj.size > MAX_SIZE:
        raise ValidationError(f"Image size exceeds the {esign_config.max_image_size // (1024 * 1024)}MB limit.")
        
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





class SignerAuthorizationStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp
        from services.security_policy_service import get_authorization_status
        status_data = get_authorization_status(participant)
        return Response(status_data, status=status.HTTP_200_OK)


class TermsAcceptanceView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        accepted = request.data.get("accepted")
        if accepted is not True:
            return Response(
                {"detail": "accepted must be true."},
                status=status.HTTP_400_BAD_REQUEST
            )

        terms_version = request.data.get("terms_version", "v1") or "v1"

        from services.terms_service import accept_terms
        state = accept_terms(participant, terms_version=str(terms_version))

        return Response(
            {
                "accepted_terms": state.accepted_terms,
                "accepted_terms_at": state.accepted_terms_at.isoformat() if state.accepted_terms_at else None,
                "terms_version": state.terms_version,
            },
            status=status.HTTP_200_OK
        )


class SendEmailOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("otp_send_ip", ip, esign_config.rate_limit_otp_send, "send_otp")
        if is_limited:
            return make_rate_limited_response(retry_after)
            
        is_limited, _, retry_after = check_rate_limit("otp_send_participant", participant.id, esign_config.rate_limit_otp_send, "send_otp")
        if is_limited:
            return make_rate_limited_response(retry_after)

        from services.email_otp_service import send_email_otp
        try:
            send_email_otp(participant)
        except Exception as exc:
            logger.error(f"Failed to send OTP: {exc}", exc_info=True)
            return Response(
                {"detail": "Unable to send the verification email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "OTP sent.", "email": participant.email},
            status=status.HTTP_200_OK,
        )


class VerifyEmailOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        is_locked, remaining_seconds = check_otp_lockout(participant.id)
        if is_locked:
            return Response(
                {
                    "verified": False,
                    "error": f"Too many failed attempts. Try again in {remaining_seconds} seconds.",
                    "retry_after": remaining_seconds
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        otp = request.data.get("otp")
        if not otp:
            return Response(
                {"verified": False, "error": "otp is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from services.email_otp_service import verify_email_otp
        result = verify_email_otp(participant, str(otp))

        if result["verified"]:
            reset_otp_failed_attempts(participant.id)
            return Response(result, status=status.HTTP_200_OK)

        register_otp_failed_attempt(participant.id)
        is_locked, remaining_seconds = check_otp_lockout(participant.id)
        if is_locked:
            return Response(
                {
                    "verified": False,
                    "error": f"Too many failed attempts. Try again in {remaining_seconds} seconds.",
                    "retry_after": remaining_seconds
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        return Response(result, status=status.HTTP_400_BAD_REQUEST)


class FaceVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("face_verify_ip", ip, esign_config.rate_limit_face_verification, "face_verification")
        if is_limited:
            return make_rate_limited_response(retry_after)
            
        is_limited, _, retry_after = check_rate_limit("face_verify_participant", participant.id, esign_config.rate_limit_face_verification, "face_verification")
        if is_limited:
            return make_rate_limited_response(retry_after)

        selfie_image = request.data.get('selfie_image') or request.FILES.get('selfie_image')

        if not selfie_image:
            return Response({"detail": "selfie_image is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_image_file(selfie_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if hasattr(selfie_image, 'read'):
                selfie_image_bytes = selfie_image.read()
            else:
                selfie_image_bytes = selfie_image
        except Exception:
            return Response({"detail": "Failed to read selfie_image."}, status=status.HTTP_400_BAD_REQUEST)

        from services.face_matching_service import perform_face_match

        logger.debug("[FaceVerificationView] BEFORE perform_face_match: participant_id=%s", participant.id)
        biometric = perform_face_match(participant, selfie_image_bytes)
        logger.debug("[FaceVerificationView] AFTER perform_face_match: status=%s", biometric.status)

        if biometric.status == "matched":
            return Response({
                "matched": True,
                "similarity_score": biometric.similarity_score,
                "provider": biometric.provider
            }, status=status.HTTP_200_OK)
        elif biometric.status == "failed":
            return Response({
                "matched": False,
                "similarity_score": biometric.similarity_score
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "matched": False,
                "status": biometric.status
            }, status=status.HTTP_200_OK)


class SignerIdentityVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, participant_id, *args, **kwargs):
        participant, token_obj, error_resp = check_participant_authorization(request, participant_id)
        if error_resp:
            return error_resp

        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("identity_verify_ip", ip, esign_config.rate_limit_ocr, "identity_verification")
        if is_limited:
            return make_rate_limited_response(retry_after)
            
        is_limited, _, retry_after = check_rate_limit("identity_verify_participant", participant.id, esign_config.rate_limit_ocr, "identity_verification")
        if is_limited:
            return make_rate_limited_response(retry_after)

        document_image = request.data.get('document_image') or request.FILES.get('document_image')
        if not document_image:
            return Response({"detail": "document_image is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_image_file(document_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if hasattr(document_image, 'read'):
                document_image_bytes = document_image.read()
            else:
                document_image_bytes = document_image
        except Exception:
            return Response({"detail": "Failed to read document_image."}, status=status.HTTP_400_BAD_REQUEST)

        from services.identity_verification_service import perform_identity_verification
        
        verification = perform_identity_verification(participant, document_image_bytes)

        return Response({
            "status": verification.status,
            "full_name": verification.full_name,
            "document_type": verification.document_type,
            "failure_reason": verification.failure_reason or "",
        }, status=status.HTTP_200_OK)


import mimetypes
from django.core.files.storage import default_storage

def stream_protected_file(path, as_attachment=False, filename=None):
    path = path.replace("\\", "/").lstrip("/")
    if not default_storage.exists(path):
        raise Http404("Requested file not found in storage.")
    
    try:
        file_obj = default_storage.open(path, 'rb')
    except Exception as e:
        logger.error(f"Failed to open protected file {path}: {str(e)}")
        raise Http404("Failed to access requested file.")

    content_type, _ = mimetypes.guess_type(path)
    if not content_type:
        content_type = 'application/octet-stream'

    if not filename:
        filename = os.path.basename(path)

    response = FileResponse(
        file_obj,
        as_attachment=as_attachment,
        filename=filename,
        content_type=content_type
    )
    response['Cache-Control'] = 'private, no-store'

    try:
        response['Content-Length'] = default_storage.size(path)
    except Exception:
        pass

    return response

class ProtectedMediaView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, path, *args, **kwargs):
        import urllib.parse
        from services.media_auth_service import check_media_authorization
        
        cleaned_path = urllib.parse.unquote(path).replace("\\", "/").lstrip("/")
        
        authorized, auth_err, envelope = check_media_authorization(request, cleaned_path)
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)

        as_attachment = request.GET.get('download', '').lower() == 'true'
        return stream_protected_file(cleaned_path, as_attachment=as_attachment)



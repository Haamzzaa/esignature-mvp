import logging
import os
from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from esign.config import esign_config
from esign.models import AuditLog, Envelope, ParticipantToken, SignedDocument, Signer, SigningToken, Template

logger = logging.getLogger(__name__)

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
        from datetime import timedelta

        from django.utils import timezone

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

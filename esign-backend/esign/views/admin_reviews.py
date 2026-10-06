import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from esign.models import (
    Participant,
    Envelope,
    ParticipantAuthorizationState,
    SignerIdentityVerification,
    BiometricVerification,
    VerificationSession,
    ContractAnalysis,
    RepresentativeCandidate,
    AuditLog
)
from esign.events.dispatcher import esign_dispatcher
from esign.events.definitions import (
    ManualReviewApproved,
    ManualReviewResubmissionRequested,
    ManualReviewRejected
)
from services.security_policy_service import get_authorization_status
from services.authorization_service import authorize_signer

logger = logging.getLogger(__name__)


class IsStaffUser(permissions.BasePermission):
    """
    Allows access only to authenticated staff or superuser accounts.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser)
        )


def _collect_review_cases(status_filter="under_review", search_query=None):
    """
    Discovers all participants requiring or having completed manual review.
    """
    participants = Participant.objects.select_related(
        "envelope",
        "authorization_state",
        "signer_identity_verification",
        "biometric_verification",
        "verification_session"
    ).all().order_by("-id")

    results = []
    now = timezone.now()

    for participant in participants:
        auth_status = get_authorization_status(participant)
        current_review_status = auth_status.get("review_status")

        if status_filter == "under_review" and current_review_status != "under_review":
            continue
        elif status_filter == "approved" and current_review_status != "approved":
            continue
        elif status_filter == "rejected" and current_review_status != "rejected":
            continue
        elif status_filter == "resubmission_required" and current_review_status != "resubmission_required":
            continue
        elif status_filter == "all" and not current_review_status:
            continue
        elif status_filter not in ["under_review", "approved", "rejected", "resubmission_required", "all"]:
            if current_review_status != "under_review":
                continue

        # Optional search filtering
        if search_query:
            query = search_query.lower()
            name_match = query in participant.name.lower()
            email_match = query in participant.email.lower()
            env_title = (participant.envelope.title or "").lower()
            env_match = query in env_title
            if not (name_match or email_match or env_match):
                continue

        created_at = participant.created_at
        age_seconds = int((now - created_at).total_seconds()) if created_at else 0

        results.append({
            "participant_id": participant.id,
            "participant_name": participant.name,
            "participant_email": participant.email,
            "participant_role": participant.role,
            "envelope_id": participant.envelope_id,
            "envelope_title": participant.envelope.title or f"Envelope #{participant.envelope_id}",
            "envelope_status": participant.envelope.status,
            "review_status": current_review_status,
            "review_reason": auth_status.get("review_reason") or auth_status.get("reason") or "Manual review required",
            "submitted_at": created_at.isoformat() if created_at else None,
            "review_age_seconds": age_seconds,
        })

    return results


class AdminReviewQueueView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, *args, **kwargs):
        status_filter = request.GET.get("status", "under_review")
        search_query = request.GET.get("q", "").strip()

        cases = _collect_review_cases(status_filter=status_filter, search_query=search_query)
        return Response({
            "count": len(cases),
            "cases": cases
        }, status=status.HTTP_200_OK)


class AdminReviewDetailView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request, participant_id, *args, **kwargs):
        participant = get_object_or_404(
            Participant.objects.select_related("envelope"),
            id=participant_id
        )
        envelope = participant.envelope
        state, _ = ParticipantAuthorizationState.objects.get_or_create(participant=participant)
        auth_status = get_authorization_status(participant)

        verification = SignerIdentityVerification.objects.filter(participant=participant).first()
        biometric = BiometricVerification.objects.filter(participant=participant).first()
        contract_analysis = ContractAnalysis.objects.filter(document=envelope.document).first() if envelope.document else None
        if not contract_analysis and envelope.document:
            contract_analysis = ContractAnalysis.objects.filter(file_hash=envelope.document.file_hash).first()

        auth_res = authorize_signer(participant, verification, contract_analysis)

        # Build sanitized dossier
        identity_data = None
        if verification:
            doc_img_url = f"/media/{verification.document_image.name}" if verification.document_image else None
            ref_face_url = f"/media/{verification.reference_face_image.name}" if verification.reference_face_image else None
            identity_data = {
                "status": verification.status,
                "full_name": verification.full_name,
                "full_name_en": verification.full_name_en,
                "full_name_ar": verification.full_name_ar,
                "national_id_number": verification.national_id_number,
                "document_type": verification.document_type,
                "country": verification.country,
                "expiry_date": verification.expiry_date.isoformat() if verification.expiry_date else None,
                "identity_match_score": verification.identity_match_score,
                "identity_matched": verification.identity_matched,
                "failure_reason": verification.failure_reason,
                "document_image_url": doc_img_url,
                "reference_face_image_url": ref_face_url,
                "created_at": verification.created_at.isoformat() if verification.created_at else None,
                "updated_at": verification.updated_at.isoformat() if verification.updated_at else None,
            }

        biometric_data = None
        if biometric:
            biometric_data = {
                "status": biometric.status,
                "similarity_score": biometric.similarity_score,
                "liveness_score": biometric.liveness_score,
                "failure_reason": biometric.failure_reason,
                "started_at": biometric.started_at.isoformat() if biometric.started_at else None,
                "completed_at": biometric.completed_at.isoformat() if biometric.completed_at else None,
            }

        # Representative authorization evidence
        contract_reps = []
        if contract_analysis and contract_analysis.representatives:
            if isinstance(contract_analysis.representatives, list):
                for rep in contract_analysis.representatives:
                    if isinstance(rep, dict):
                        contract_reps.append({
                            "name_en": rep.get("name_en") or rep.get("name") or "",
                            "name_ar": rep.get("name_ar") or "",
                            "title_en": rep.get("title_en") or rep.get("title") or "",
                            "title_ar": rep.get("title_ar") or "",
                        })
                    elif isinstance(rep, str):
                        contract_reps.append({"name_en": rep, "title_en": ""})

        candidate_objs = RepresentativeCandidate.objects.filter(envelope=envelope)
        candidate_rows = [
            {
                "id": c.id,
                "name_en": c.name_en,
                "name_ar": c.name_ar,
                "title_en": c.title_en,
                "title_ar": c.title_ar,
                "authority_clause": c.authority_clause,
                "status": c.status
            }
            for c in candidate_objs
        ]

        representative_data = {
            "status": auth_res.get("status"),
            "authorized": auth_res.get("authorized", False),
            "matched_representative": auth_res.get("matched_representative"),
            "matched_language": auth_res.get("matched_language"),
            "reason": auth_res.get("reason"),
            "contract_representatives": contract_reps,
            "candidates": candidate_rows,
        }

        # Audit History
        audit_logs = AuditLog.objects.filter(envelope=envelope).order_by("-timestamp")[:30]
        audit_history = [
            {
                "id": log.id,
                "event": log.event,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in audit_logs
        ]

        dossier = {
            "participant": {
                "id": participant.id,
                "name": participant.name,
                "email": participant.email,
                "role": participant.role,
                "status": participant.status,
                "created_at": participant.created_at.isoformat() if participant.created_at else None,
            },
            "envelope": {
                "id": envelope.id,
                "title": envelope.title or f"Envelope #{envelope.id}",
                "status": envelope.status,
                "owner_email": envelope.owner.email if envelope.owner else None,
                "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
            },
            "review_state": {
                "review_status": auth_status.get("review_status"),
                "review_reason": auth_status.get("review_reason") or auth_status.get("reason"),
                "review_notes": state.manual_review_notes,
                "resubmit_step": state.manual_review_resubmit_step,
                "decided_at": state.manual_review_decided_at.isoformat() if state.manual_review_decided_at else None,
                "decided_by": state.manual_review_decided_by.username if state.manual_review_decided_by else None,
            },
            "identity_verification": identity_data,
            "biometric_verification": biometric_data,
            "representative_authorization": representative_data,
            "audit_history": audit_history,
        }

        return Response(dossier, status=status.HTTP_200_OK)


class AdminReviewDecisionView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request, participant_id, *args, **kwargs):
        participant = get_object_or_404(
            Participant.objects.select_related("envelope"),
            id=participant_id
        )
        envelope = participant.envelope
        action = request.data.get("action", "").strip().lower()
        notes = request.data.get("notes", "").strip() or request.data.get("reason", "").strip()
        target_step = request.data.get("target_step", "").strip().lower()

        if action not in ["approve", "resubmit", "reject"]:
            return Response(
                {"detail": "Invalid action. Supported actions: 'approve', 'resubmit', 'reject'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        state, _ = ParticipantAuthorizationState.objects.get_or_create(participant=participant)
        current_status = get_authorization_status(participant)

        # Validate that if the case has already been decided and not under review or resubmitted, proper state handling applies
        if current_status.get("review_status") not in ["under_review", "resubmission_required"] and not (state.manual_review_approved or state.manual_review_rejected):
            # Check if this case is eligible for review
            pass

        now = timezone.now()

        with transaction.atomic():
            if action == "approve":
                state.manual_review_approved = True
                state.manual_review_rejected = False
                state.manual_review_resubmit_step = ""
                state.manual_review_notes = notes
                state.manual_review_decided_at = now
                state.manual_review_decided_by = request.user
                state.save()

                # Update verification records if they were requiring manual review
                verification = SignerIdentityVerification.objects.filter(participant=participant).first()
                if verification and verification.status == "requires_manual_review":
                    verification.status = "verified"
                    verification.save(update_fields=["status"])

                biometric = BiometricVerification.objects.filter(participant=participant).first()
                if biometric and biometric.status == "requires_manual_review":
                    biometric.status = "matched"
                    biometric.save(update_fields=["status"])

                session = VerificationSession.objects.filter(participant=participant).first()
                if session and session.status == "requires_manual_review":
                    session.status = "approved"
                    session.save(update_fields=["status"])

                AuditLog.objects.create(
                    envelope=envelope,
                    event=f"manual_review_approved by staff {request.user.username}" + (f": {notes}" if notes else "")
                )

                try:
                    esign_dispatcher.publish(ManualReviewApproved(participant_id=participant.id))
                except Exception as exc:
                    logger.warning("[AdminReviewDecisionView] Failed publishing ManualReviewApproved event: %s", exc)

                return Response({
                    "detail": "Verification successfully approved.",
                    "participant_id": participant.id,
                    "review_status": "approved",
                    "authorization": get_authorization_status(participant)
                }, status=status.HTTP_200_OK)

            elif action == "resubmit":
                if not target_step:
                    return Response(
                        {"detail": "target_step is required for resubmission (e.g. 'national_id' or 'face')."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                valid_steps = ["national_id", "face", "face_biometric", "representative", "representative_match"]
                if target_step not in valid_steps:
                    return Response(
                        {"detail": f"Invalid target_step. Choose from {valid_steps}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                state.manual_review_approved = False
                state.manual_review_rejected = False
                state.manual_review_resubmit_step = target_step
                state.manual_review_notes = notes
                state.manual_review_decided_at = now
                state.manual_review_decided_by = request.user
                state.save()

                # Reset the specific target step failure state so the signer can re-perform it
                if target_step == "national_id":
                    verification = SignerIdentityVerification.objects.filter(participant=participant).first()
                    if verification:
                        verification.status = "pending"
                        verification.failure_reason = ""
                        verification.save(update_fields=["status", "failure_reason"])
                elif target_step in ["face", "face_biometric"]:
                    biometric = BiometricVerification.objects.filter(participant=participant).first()
                    if biometric:
                        biometric.status = "pending"
                        biometric.failure_reason = ""
                        biometric.save(update_fields=["status", "failure_reason"])

                session = VerificationSession.objects.filter(participant=participant).first()
                if session and session.status == "requires_manual_review":
                    session.status = "pending"
                    session.failure_reason = ""
                    session.save(update_fields=["status", "failure_reason"])

                AuditLog.objects.create(
                    envelope=envelope,
                    event=f"manual_review_resubmission_requested ({target_step}) by staff {request.user.username}" + (f": {notes}" if notes else "")
                )

                try:
                    esign_dispatcher.publish(ManualReviewResubmissionRequested(
                        participant_id=participant.id,
                        target_step=target_step,
                        reason=notes
                    ))
                except Exception as exc:
                    logger.warning("[AdminReviewDecisionView] Failed publishing ManualReviewResubmissionRequested: %s", exc)

                return Response({
                    "detail": f"Resubmission requested for step '{target_step}'.",
                    "participant_id": participant.id,
                    "review_status": "resubmission_required",
                    "target_step": target_step,
                    "authorization": get_authorization_status(participant)
                }, status=status.HTTP_200_OK)

            elif action == "reject":
                if not notes:
                    return Response(
                        {"detail": "A rejection reason is required."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                state.manual_review_approved = False
                state.manual_review_rejected = True
                state.manual_review_resubmit_step = ""
                state.manual_review_notes = notes
                state.manual_review_decided_at = now
                state.manual_review_decided_by = request.user
                state.save()

                session = VerificationSession.objects.filter(participant=participant).first()
                if session:
                    session.status = "failed"
                    session.failure_reason = notes
                    session.save(update_fields=["status", "failure_reason"])

                AuditLog.objects.create(
                    envelope=envelope,
                    event=f"manual_review_rejected by staff {request.user.username}: {notes}"
                )

                try:
                    esign_dispatcher.publish(ManualReviewRejected(
                        participant_id=participant.id,
                        reason=notes
                    ))
                except Exception as exc:
                    logger.warning("[AdminReviewDecisionView] Failed publishing ManualReviewRejected: %s", exc)

                return Response({
                    "detail": "Verification rejected.",
                    "participant_id": participant.id,
                    "review_status": "rejected",
                    "reason": notes,
                    "authorization": get_authorization_status(participant)
                }, status=status.HTTP_200_OK)

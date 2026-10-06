import logging
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from esign.config import esign_config
from esign.views.utils import (check_participant_authorization,
                               make_rate_limited_response)
from esign import views
from services.rate_limiting_service import (check_otp_lockout,
                                            check_rate_limit, get_client_ip,
                                            register_otp_failed_attempt,
                                            reset_otp_failed_attempts)

logger = logging.getLogger(__name__)

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

        token_ident = str(token_obj.token) if token_obj else str(participant.id)
        is_limited, _, retry_after = check_rate_limit("otp_send_token", token_ident, esign_config.rate_limit_otp_send, "send_otp")
        if is_limited:
            return make_rate_limited_response(retry_after)
            
        is_limited, _, retry_after = check_rate_limit("otp_send_participant", participant.id, esign_config.rate_limit_otp_send, "send_otp")
        if is_limited:
            return make_rate_limited_response(retry_after)

        from services.email_otp_service import EmailDeliveryError, send_email_otp
        try:
            send_email_otp(participant)
        except EmailDeliveryError as exc:
            logger.error("[SendEmailOTPView] Email delivery failed for participant %s: %s", participant.id, exc)
            return Response(
                {"detail": "Unable to send the verification email. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("[SendEmailOTPView] Unexpected error sending OTP for participant %s", participant.id)
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
            views.validate_image_file(selfie_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if hasattr(selfie_image, 'read'):
                selfie_image_bytes = selfie_image.read()
            else:
                selfie_image_bytes = selfie_image
        except Exception:
            return Response({"detail": "Failed to read selfie_image."}, status=status.HTTP_400_BAD_REQUEST)

        # Early exit on face image quality check failure
        from services.image_quality_service import assess_face_quality
        quality_response = assess_face_quality(selfie_image_bytes)
        if quality_response.get("failure_code") == "image_quality_check_failed":
            return Response(quality_response, status=status.HTTP_400_BAD_REQUEST)

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
            views.validate_image_file(document_image)
        except ValidationError as e:
            return Response({"detail": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if hasattr(document_image, 'read'):
                document_image_bytes = document_image.read()
            else:
                document_image_bytes = document_image
        except Exception:
            return Response({"detail": "Failed to read document_image."}, status=status.HTTP_400_BAD_REQUEST)

        # Early exit on document image quality check failure
        from services.image_quality_service import assess_document_quality
        quality_response = assess_document_quality(document_image_bytes)
        if quality_response.get("failure_code") == "image_quality_check_failed":
            return Response(quality_response, status=status.HTTP_400_BAD_REQUEST)

        from services.identity_verification_service import \
            perform_identity_verification
        
        verification = perform_identity_verification(participant, document_image_bytes)

        return Response({
            "status": verification.status,
            "full_name": verification.full_name,
            "document_type": verification.document_type,
            "failure_reason": verification.failure_reason or "",
        }, status=status.HTTP_200_OK)

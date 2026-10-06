import logging
import os

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from esign.config import esign_config
from esign.models import SignedDocument
from esign.views.utils import (get_token_signer_or_participant,
                               handle_token_error, make_rate_limited_response,
                               stream_protected_file)
from services.rate_limiting_service import check_rate_limit, get_client_ip

logger = logging.getLogger(__name__)

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

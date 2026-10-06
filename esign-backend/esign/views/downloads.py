import logging
import os
import urllib.parse
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from esign.models import Envelope, SignedDocument
from esign.views.utils import get_token_signer_or_participant, handle_token_error, stream_protected_file

logger = logging.getLogger(__name__)

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


class ProtectedMediaView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, path, *args, **kwargs):
        from services.media_auth_service import check_media_authorization
        
        cleaned_path = urllib.parse.unquote(path).replace("\\", "/").lstrip("/")
        
        authorized, auth_err, envelope = check_media_authorization(request, cleaned_path)
        if not authorized:
            return Response({"detail": auth_err or "Access Denied."}, status=status.HTTP_403_FORBIDDEN)

        as_attachment = request.GET.get('download', '').lower() == 'true'
        return stream_protected_file(cleaned_path, as_attachment=as_attachment)

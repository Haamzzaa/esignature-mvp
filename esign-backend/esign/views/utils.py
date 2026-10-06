import logging
import os
import math
import mimetypes
from PIL import Image

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from esign.config import esign_config
from esign.request_context import get_request_id
from esign.models import Participant, ParticipantToken, SigningToken

logger = logging.getLogger(__name__)

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

def check_participant_authorization(request, participant_id):
    """
    Validates authorization for a participant.
    Returns (participant, token_obj, error_response) tuple.
    If authorized, error_response is None.
    """
    import logging
    from django.utils import timezone
    from esign.models import Participant
    from services.token_service import resolve_token

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
    try:
        # Seek to beginning in case file has been read
        file_obj.seek(0)
        img = Image.open(file_obj)
        img.verify()
        file_obj.seek(0)
    except Exception:
        raise ValidationError("Invalid image format or corrupted image.")

def stream_protected_file(path, as_attachment=False, filename=None):
    path = path.replace("\\", "/").lstrip("/")
    if not default_storage.exists(path):
        raise Http404("Requested file not found in storage.")
    
    try:
        file_obj = default_storage.open(path, 'rb')
    except Exception as e:
        logger.exception("Failed to open protected file %s", path)
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
        # Content-Length is optional; if storage size lookup fails, skip setting it
        pass

    return response

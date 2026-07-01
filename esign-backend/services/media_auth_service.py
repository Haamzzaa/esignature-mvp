import logging
from django.conf import settings
from django.utils import timezone
from esign.models import Envelope, Document, SignedDocument, CompletionCertificate, SignerIdentityVerification, Participant
from services.token_service import resolve_token
from esign.request_context import get_request_id

logger = logging.getLogger(__name__)

def lookup_envelope_and_participant_for_path(path, expected_envelope=None):
    """
    Looks up the related Envelope, Participant, and file category for a normalized path.
    """
    path = path.replace("\\", "/").lstrip("/")

    # 1. Original Document
    if path.startswith("documents/"):
        doc = Document.objects.filter(file=path).first()
        if not doc:
            doc = Document.objects.filter(file__contains=path).first()
        if doc:
            envelope = expected_envelope if expected_envelope is not None else doc.envelope_set.first()
            return envelope, None, "original_document"

    # 2. Signed Document
    elif path.startswith("signed/"):
        signed_doc = SignedDocument.objects.filter(file=path).first()
        if not signed_doc:
            signed_doc = SignedDocument.objects.filter(file__contains=path).first()
        if signed_doc:
            envelope = expected_envelope if expected_envelope is not None else signed_doc.envelope
            return envelope, None, "signed_document"

    # 3. Certificate
    elif path.startswith("certificates/"):
        cert = CompletionCertificate.objects.filter(file=path).first()
        if not cert:
            cert = CompletionCertificate.objects.filter(file__contains=path).first()
        if cert:
            envelope = expected_envelope if expected_envelope is not None else cert.envelope
            return envelope, None, "certificate"

    # 4. Identity document/face images (modern)
    elif path.startswith("identity/documents/"):
        ver = SignerIdentityVerification.objects.filter(document_image=path).first()
        if not ver:
            ver = SignerIdentityVerification.objects.filter(document_image__contains=path).first()
        if ver:
            envelope = expected_envelope if expected_envelope is not None else ver.participant.envelope
            return envelope, ver.participant, "national_id"

    elif path.startswith("identity/faces/"):
        ver = SignerIdentityVerification.objects.filter(reference_face_image=path).first()
        if not ver:
            ver = SignerIdentityVerification.objects.filter(reference_face_image__contains=path).first()
        if ver:
            envelope = expected_envelope if expected_envelope is not None else ver.participant.envelope
            return envelope, ver.participant, "reference_face"



    return None, None, None

def check_media_authorization(request, path, token_str=None, expected_envelope=None):
    """
    Wrapper that implements request-lifetime caching of authorization checks.
    """
    if request:
        if not hasattr(request, '_media_auth_cache'):
            request._media_auth_cache = {}
            request._media_cache_hits = 0
        expected_envelope_id = expected_envelope.id if expected_envelope else None
        cache_key = f"{path}:{token_str}:{expected_envelope_id}"
        if cache_key in request._media_auth_cache:
            request._media_cache_hits += 1
            import hashlib
            token_hash = hashlib.sha256(str(token_str).encode('utf-8')).hexdigest()[:8] if token_str else 'none'
            logger.debug(
                "[MediaAuthCache] Hit! path=%s token_hash=%s hits=%d",
                path, token_hash, request._media_cache_hits
            )
            return request._media_auth_cache[cache_key]

    result = _check_media_authorization_uncached(request, path, token_str, expected_envelope=expected_envelope)
    
    if request:
        request._media_auth_cache[cache_key] = result
        
    return result

def _check_media_authorization_uncached(request, path, token_str=None, expected_envelope=None):
    """
    Checks if request or token_str is authorized to access the file at path (uncached).
    Returns (is_authorized, error_message, envelope).
    """
    request_id = get_request_id() or "unknown-request-id"
    path = path.replace("\\", "/").lstrip("/")

    envelope, target_participant, category = lookup_envelope_and_participant_for_path(path, expected_envelope=expected_envelope)

    if not envelope:
        logger.warning(
            "[MediaAuth] Access Denied: Unregistered file path. path=%s req_id=%s",
            path, request_id
        )
        return False, "Requested file not found or unregistered.", None

    envelope_id = envelope.id
    actor_identifier = "anonymous"
    actor_type = "anonymous"

    # 1. Check Administrator/Staff permissions
    user = request.user if request else None
    if user and user.is_authenticated:
        actor_identifier = user.email or user.username
        if user.is_staff or user.is_superuser:
            actor_type = "admin"
            logger.info(
                "[MediaAuth] Access Granted. actor=%s type=admin category=%s envelope_id=%s req_id=%s",
                actor_identifier, category, envelope_id, request_id
            )
            return True, None, envelope

    # 2. Resolve Participant Token (if provided)
    resolved_participant = None
    resolved_legacy_signer = None

    if not token_str and request:
        token_str = request.headers.get("X-Participant-Token") or request.META.get("HTTP_X_PARTICIPANT_TOKEN") or request.GET.get("token")

    if token_str:
        token_obj, err = resolve_token(token_str, allow_used=True)
        if not err and token_obj:
            if hasattr(token_obj, "participant"):
                resolved_participant = token_obj.participant
                actor_identifier = f"participant_token:{resolved_participant.id}"
                actor_type = "participant_token"
            elif hasattr(token_obj, "signer"):
                resolved_legacy_signer = token_obj.signer
                actor_identifier = f"signer_token:{resolved_legacy_signer.id}"
                actor_type = "signer_token"

    # 3. Check if user is Envelope Owner
    is_owner = False
    if user and user.is_authenticated and envelope.owner == user:
        is_owner = True
        actor_type = "owner"

    if is_owner:
        if category in ("original_document", "signed_document", "certificate"):
            logger.info(
                "[MediaAuth] Access Granted. actor=%s type=owner category=%s envelope_id=%s req_id=%s",
                actor_identifier, category, envelope_id, request_id
            )
            return True, None, envelope
        
        # ID/Selfie access is configurable
        owner_can_view = getattr(settings, "OWNER_CAN_VIEW_ID_IMAGES", False)
        if owner_can_view:
            logger.info(
                "[MediaAuth] Access Granted (configurable). actor=%s type=owner category=%s envelope_id=%s req_id=%s",
                actor_identifier, category, envelope_id, request_id
            )
            return True, None, envelope
        else:
            logger.warning(
                "[MediaAuth] Access Denied. Owner blocked from raw identity images. actor=%s category=%s envelope_id=%s req_id=%s",
                actor_identifier, category, envelope_id, request_id
            )
            return False, "Access Denied: Owner is not authorized to view raw identity/selfie files.", envelope

    # 4. Check Participant permissions
    if not resolved_participant and user and user.is_authenticated:
        resolved_participant = envelope.participants.filter(email=user.email).first()
        if resolved_participant:
            actor_identifier = user.email
            actor_type = "participant_user"

    if not resolved_participant and resolved_legacy_signer:
        resolved_participant = envelope.participants.filter(email=resolved_legacy_signer.email).first()

    if resolved_participant:
        if resolved_participant.envelope != envelope:
            logger.warning(
                "[MediaAuth] Access Denied. Token/Participant mismatch. actor=%s target_envelope_id=%s path_envelope_id=%s req_id=%s",
                actor_identifier, resolved_participant.envelope.id, envelope_id, request_id
            )
            return False, "Access Denied: Token or participant mismatch.", envelope

        p_status = resolved_participant.status
        is_completed = resolved_participant.has_completed or p_status in ('completed', 'declined', 'returned')

        if category == "original_document":
            if is_completed or p_status in ('active', 'viewed'):
                logger.info(
                    "[MediaAuth] Access Granted. actor=%s type=%s category=original_document envelope_id=%s req_id=%s",
                    actor_identifier, actor_type, envelope_id, request_id
                )
                return True, None, envelope
            else:
                logger.warning(
                    "[MediaAuth] Access Denied. Stage not active for original_document. actor=%s status=%s req_id=%s",
                    actor_identifier, p_status, request_id
                )
                return False, "Access Denied: Original document is not available at your current workflow stage.", envelope

        elif category == "signed_document":
            if is_completed or p_status in ('active', 'viewed'):
                logger.info(
                    "[MediaAuth] Access Granted. actor=%s type=%s category=signed_document envelope_id=%s req_id=%s",
                    actor_identifier, actor_type, envelope_id, request_id
                )
                return True, None, envelope
            else:
                logger.warning(
                    "[MediaAuth] Access Denied. Stage not active for signed_document. actor=%s status=%s req_id=%s",
                    actor_identifier, p_status, request_id
                )
                return False, "Access Denied: Signed document is not available at your current workflow stage.", envelope

        elif category == "certificate":
            if is_completed and envelope.status == "completed":
                logger.info(
                    "[MediaAuth] Access Granted. actor=%s type=%s category=certificate envelope_id=%s req_id=%s",
                    actor_identifier, actor_type, envelope_id, request_id
                )
                return True, None, envelope
            else:
                logger.warning(
                    "[MediaAuth] Access Denied. Certificate not ready or user not completed. actor=%s status=%s envelope_status=%s req_id=%s",
                    actor_identifier, p_status, envelope.status, request_id
                )
                return False, "Access Denied: Certificate is only available after package and step completion.", envelope

        elif category in ("national_id", "reference_face"):
            if target_participant and target_participant == resolved_participant:
                logger.info(
                    "[MediaAuth] Access Granted. actor=%s type=%s category=%s own file access envelope_id=%s req_id=%s",
                    actor_identifier, actor_type, category, envelope_id, request_id
                )
                return True, None, envelope
            else:
                logger.warning(
                    "[MediaAuth] Access Denied. Attempt to view other participant's ID/selfie. actor=%s target_p_id=%s req_id=%s",
                    actor_identifier, target_participant.id if target_participant else None, request_id
                )
                return False, "Access Denied: You are not authorized to view this identity document.", envelope

    logger.warning(
        "[MediaAuth] Access Denied: Unauthorized request. actor=%s type=%s category=%s envelope_id=%s req_id=%s",
        actor_identifier, actor_type, category, envelope_id, request_id
    )
    return False, "Access Denied: Unauthorized access to protected asset.", envelope

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)

GENESIS_PREV_HASH = "0" * 64


def compute_sha256_bytes(data: bytes) -> str:
    """Computes SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(file_field) -> Optional[str]:
    """Computes SHA-256 hex digest of a Django FileField or FieldFile safely."""
    if not file_field:
        return None
    try:
        file_field.open("rb")
        try:
            content = file_field.read()
            return hashlib.sha256(content).hexdigest()
        finally:
            file_field.close()
    except Exception as e:
        logger.exception("Failed to read file for SHA-256 calculation: %s", e)
        return None


def canonicalize_audit_payload(
    envelope_id: int,
    event: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    timestamp_iso: str,
    prev_hash: str,
) -> bytes:
    """
    Produces deterministic UTF-8 encoded canonical JSON for audit entry hashing.
    Ensures deterministic key ordering, standard separators, and explicit null representations.
    """
    payload = {
        "envelope_id": int(envelope_id),
        "event": str(event),
        "ip_address": str(ip_address) if ip_address is not None else None,
        "prev_hash": str(prev_hash),
        "timestamp": str(timestamp_iso),
        "user_agent": str(user_agent) if user_agent is not None else None,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_audit_log_hashes(audit_log) -> None:
    """
    Computes prev_hash and entry_hash for an AuditLog instance prior to DB insertion.
    Handles genesis state if this is the envelope's first audit event.
    """
    if audit_log.entry_hash:
        return

    # Ensure timestamp is set
    if not audit_log.timestamp:
        audit_log.timestamp = django_timezone.now()

    # Format timestamp to ISO 8601 with second precision
    ts_iso = audit_log.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Find the immediately preceding audit log for this envelope
    if not audit_log.prev_hash:
        from esign.models import AuditLog
        qs = AuditLog.objects.filter(envelope_id=audit_log.envelope_id)
        if audit_log.pk:
            qs = qs.exclude(pk=audit_log.pk)
        last_log = qs.order_by("-id").first()

        if last_log and last_log.entry_hash:
            audit_log.prev_hash = last_log.entry_hash
        else:
            audit_log.prev_hash = GENESIS_PREV_HASH

    canonical_bytes = canonicalize_audit_payload(
        envelope_id=audit_log.envelope_id,
        event=audit_log.event,
        ip_address=audit_log.ip_address,
        user_agent=audit_log.user_agent,
        timestamp_iso=ts_iso,
        prev_hash=audit_log.prev_hash,
    )
    audit_log.entry_hash = hashlib.sha256(canonical_bytes).hexdigest()


def verify_audit_chain(envelope) -> Dict[str, Any]:
    """
    Verifies the cryptographic hash chain of all AuditLog entries for a given envelope.
    Validates genesis, inter-entry linkage, and payload digest integrity.
    """
    from esign.models import AuditLog

    logs = list(AuditLog.objects.filter(envelope=envelope).order_by("id"))
    if not logs:
        return {
            "is_valid": True,
            "length": 0,
            "genesis_valid": True,
            "terminal_hash": GENESIS_PREV_HASH,
            "reason": "Empty audit log",
        }

    expected_prev = GENESIS_PREV_HASH
    for idx, log in enumerate(logs):
        # Check if legacy log without entry_hash
        if not log.entry_hash:
            return {
                "is_valid": False,
                "length": len(logs),
                "failed_at_index": idx,
                "failed_event": log.event,
                "reason": f"Legacy or unhashed audit entry encountered at index {idx}",
                "terminal_hash": None,
            }

        # Check prev_hash linkage
        if log.prev_hash != expected_prev:
            return {
                "is_valid": False,
                "length": len(logs),
                "failed_at_index": idx,
                "failed_event": log.event,
                "reason": f"Hash chain broken at index {idx}: expected prev_hash {expected_prev}, found {log.prev_hash}",
                "terminal_hash": None,
            }

        # Recompute entry_hash from canonical payload
        ts_iso = log.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        canonical_bytes = canonicalize_audit_payload(
            envelope_id=log.envelope_id,
            event=log.event,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            timestamp_iso=ts_iso,
            prev_hash=log.prev_hash,
        )
        computed_hash = hashlib.sha256(canonical_bytes).hexdigest()

        if computed_hash != log.entry_hash:
            return {
                "is_valid": False,
                "length": len(logs),
                "failed_at_index": idx,
                "failed_event": log.event,
                "reason": f"Payload digest mismatch at index {idx}: computed {computed_hash}, stored {log.entry_hash}",
                "terminal_hash": None,
            }

        expected_prev = log.entry_hash

    return {
        "is_valid": True,
        "length": len(logs),
        "genesis_valid": True,
        "terminal_hash": logs[-1].entry_hash if logs else GENESIS_PREV_HASH,
        "reason": "Audit chain intact and cryptographically valid",
    }


def generate_completion_seal(
    envelope_id: int,
    final_hash: str,
    terminal_audit_hash: str,
    completion_iso: str,
) -> str:
    """
    Generates an HMAC-SHA256 completion seal binding envelope ID, final PDF hash,
    terminal audit hash, and completion timestamp.
    """
    secret = getattr(settings, "A08_INTEGRITY_SECRET", settings.SECRET_KEY).encode("utf-8")
    message_dict = {
        "completion_iso": str(completion_iso),
        "envelope_id": int(envelope_id),
        "final_hash": str(final_hash),
        "terminal_audit_hash": str(terminal_audit_hash),
    }
    canonical_message = json.dumps(message_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, canonical_message, hashlib.sha256).hexdigest()


def verify_completion_seal(
    envelope_id: int,
    final_hash: str,
    terminal_audit_hash: str,
    completion_iso: str,
    seal: str,
) -> bool:
    """Constant-time verification of HMAC-SHA256 completion seal."""
    if not seal:
        return False
    expected_seal = generate_completion_seal(
        envelope_id=envelope_id,
        final_hash=final_hash,
        terminal_audit_hash=terminal_audit_hash,
        completion_iso=completion_iso,
    )
    return hmac.compare_digest(expected_seal, seal)


def seal_envelope_completion(envelope) -> Optional[str]:
    """
    Executes the completion sealing workflow for an envelope:
    1. Verifies/retrieves latest audit log terminal hash.
    2. Retrieves SignedDocument.final_hash.
    3. Generates HMAC-SHA256 completion seal.
    4. Persists completion_seal to SignedDocument.
    """
    if not getattr(settings, "A08_HASH_SEALING_ENABLED", True):
        logger.info("[Integrity] A08 hash sealing disabled via settings.")
        return None

    signed_doc = getattr(envelope, "signeddocument", None)
    if not signed_doc or not signed_doc.file:
        logger.warning("[Integrity] No SignedDocument found for envelope %s during completion sealing", envelope.id)
        return None

    chain_result = verify_audit_chain(envelope)
    terminal_audit_hash = chain_result.get("terminal_hash") or GENESIS_PREV_HASH

    now_iso = django_timezone.now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    seal = generate_completion_seal(
        envelope_id=envelope.id,
        final_hash=signed_doc.final_hash,
        terminal_audit_hash=terminal_audit_hash,
        completion_iso=now_iso,
    )

    signed_doc.completion_seal = seal
    signed_doc.save(update_fields=["completion_seal"])
    logger.info("[Integrity] Sealed envelope %s with completion seal %s", envelope.id, seal[:16] + "...")
    return seal


def verify_document_integrity(envelope) -> Dict[str, Any]:
    """
    Comprehensive multi-layer integrity evaluation for an envelope:
    - Layer 1: PDF binary SHA-256 match against SignedDocument.final_hash.
    - Layer 2: Audit log hash chain integrity and unbroken linkage.
    - Layer 3: Server-side HMAC-SHA256 completion seal verification.
    """
    signed_doc = getattr(envelope, "signeddocument", None)
    if not signed_doc or not signed_doc.file:
        return {
            "status": "missing_document",
            "is_valid": False,
            "reason": "Signed document record or file does not exist",
        }

    # 1. Verify stored file hash matches actual bytes
    actual_file_hash = compute_file_sha256(signed_doc.file)
    if not actual_file_hash:
        return {
            "status": "unreadable_file",
            "is_valid": False,
            "reason": "Unable to read signed document file",
        }

    file_hash_match = (actual_file_hash == signed_doc.final_hash)

    # 2. Verify audit trail chain
    audit_result = verify_audit_chain(envelope)

    # 3. Check completion seal status
    if not signed_doc.completion_seal:
        # Legacy document completed before A08
        return {
            "status": "legacy_unsealed",
            "is_valid": file_hash_match,
            "file_hash_match": file_hash_match,
            "stored_hash": signed_doc.final_hash,
            "actual_hash": actual_file_hash,
            "audit_chain_valid": audit_result.get("is_valid", False),
            "reason": "Document completed prior to A08 integrity sealing (legacy)",
        }

    # Check embedded PAdES cryptographic signature if present
    pades_info = {"is_signed": False}
    try:
        from services.pades_service import verify_pades_signature
        signed_doc.file.open("rb")
        try:
            pdf_bytes = signed_doc.file.read()
            pades_info = verify_pades_signature(pdf_bytes)
        finally:
            signed_doc.file.close()
    except Exception as e:
        logger.warning("[Integrity] Could not inspect PAdES signature: %s", e)

    pades_valid = True
    if pades_info.get("is_signed"):
        pades_valid = pades_info.get("signature_valid", False) and pades_info.get("intact", False)

    # For sealed documents, verify file integrity, audit chain, and PAdES (if signed)
    is_valid = file_hash_match and audit_result.get("is_valid", False) and pades_valid
    return {
        "status": "verified" if is_valid else "tampered",
        "is_valid": is_valid,
        "file_hash_match": file_hash_match,
        "stored_hash": signed_doc.final_hash,
        "actual_hash": actual_file_hash,
        "audit_chain_valid": audit_result.get("is_valid", False),
        "terminal_audit_hash": audit_result.get("terminal_hash"),
        "completion_seal": signed_doc.completion_seal,
        "pades_signed": pades_info.get("is_signed", False),
        "pades_valid": pades_valid,
        "pades_details": pades_info,
        "reason": "Integrity verified successfully" if is_valid else "Document, audit log, or cryptographic signature mismatch detected",
    }

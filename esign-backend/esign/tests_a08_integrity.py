import hashlib
import io
import os
import json
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from esign.models import AuditLog, Document, Envelope, Participant, ParticipantToken, SignedDocument, CompletionCertificate
from services.integrity_service import (
    GENESIS_PREV_HASH,
    canonicalize_audit_payload,
    compute_sha256_bytes,
    compute_file_sha256,
    compute_audit_log_hashes,
    verify_audit_chain,
    generate_completion_seal,
    verify_completion_seal,
    seal_envelope_completion,
    verify_document_integrity,
)


class A08IntegrityFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a08_user", email="a08@example.com", password="password123")
        
        # Create sample PDF content
        self.sample_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Title (A08 Test Document) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        self.document = Document.objects.create(
            owner=self.user,
            file_hash=hashlib.sha256(self.sample_pdf_bytes).hexdigest(),
        )
        self.document.file.save("test.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        self.envelope = Envelope.objects.create(
            document=self.document,
            owner=self.user,
            title="A08 Integrity Envelope",
            status="draft",
        )

    def test_canonical_audit_serialization(self):
        """Validates that audit payload serialization is strictly deterministic."""
        payload1 = canonicalize_audit_payload(
            envelope_id=1,
            event="signed",
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            timestamp_iso="2026-10-07T10:00:00Z",
            prev_hash=GENESIS_PREV_HASH,
        )
        payload2 = canonicalize_audit_payload(
            envelope_id=1,
            event="signed",
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            timestamp_iso="2026-10-07T10:00:00Z",
            prev_hash=GENESIS_PREV_HASH,
        )
        self.assertEqual(payload1, payload2)
        
        # Test null handling
        payload_null = canonicalize_audit_payload(
            envelope_id=1,
            event="created",
            ip_address=None,
            user_agent=None,
            timestamp_iso="2026-10-07T10:00:00Z",
            prev_hash=GENESIS_PREV_HASH,
        )
        parsed = json.loads(payload_null.decode("utf-8"))
        self.assertIsNone(parsed["ip_address"])
        self.assertIsNone(parsed["user_agent"])
        self.assertEqual(parsed["prev_hash"], GENESIS_PREV_HASH)

    def test_audit_log_genesis_and_chaining(self):
        """Verifies genesis hash initialization and sequential hash chaining."""
        log1 = AuditLog.objects.create(
            envelope=self.envelope,
            event="Envelope Created",
            ip_address="192.168.1.1",
            user_agent="Agent-1",
        )
        self.assertEqual(log1.prev_hash, GENESIS_PREV_HASH)
        self.assertTrue(len(log1.entry_hash) == 64)

        log2 = AuditLog.objects.create(
            envelope=self.envelope,
            event="Envelope Sent",
            ip_address="192.168.1.1",
            user_agent="Agent-1",
        )
        self.assertEqual(log2.prev_hash, log1.entry_hash)
        self.assertTrue(len(log2.entry_hash) == 64)

        log3 = AuditLog.objects.create(
            envelope=self.envelope,
            event="Signer Completed",
            ip_address="192.168.1.2",
            user_agent="Agent-2",
        )
        self.assertEqual(log3.prev_hash, log2.entry_hash)

        # Verify full chain
        res = verify_audit_chain(self.envelope)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["length"], 3)
        self.assertEqual(res["terminal_hash"], log3.entry_hash)

    def test_tampered_audit_event_detected(self):
        """Verifies that altering an audit log entry invalidates the chain."""
        log1 = AuditLog.objects.create(envelope=self.envelope, event="Created")
        log2 = AuditLog.objects.create(envelope=self.envelope, event="Signed")
        log3 = AuditLog.objects.create(envelope=self.envelope, event="Completed")

        # Directly tamper with log2 event in database
        AuditLog.objects.filter(pk=log2.pk).update(event="Tampered Event Text")

        res = verify_audit_chain(self.envelope)
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["failed_at_index"], 1)
        self.assertIn("Payload digest mismatch", res["reason"])

    def test_deleted_intermediate_audit_event_detected(self):
        """Verifies that deleting an intermediate log entry breaks the chain."""
        log1 = AuditLog.objects.create(envelope=self.envelope, event="Created")
        log2 = AuditLog.objects.create(envelope=self.envelope, event="Signed")
        log3 = AuditLog.objects.create(envelope=self.envelope, event="Completed")

        # Delete log2
        AuditLog.objects.filter(pk=log2.pk).delete()

        res = verify_audit_chain(self.envelope)
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["failed_at_index"], 1)
        self.assertIn("Hash chain broken", res["reason"])

    def test_completion_seal_generation_and_verification(self):
        """Verifies HMAC-SHA256 completion seal generation and verification."""
        final_hash = hashlib.sha256(b"final_signed_pdf_bytes").hexdigest()
        terminal_audit_hash = hashlib.sha256(b"terminal_audit").hexdigest()
        ts_iso = "2026-10-07T11:00:00Z"

        seal = generate_completion_seal(
            envelope_id=self.envelope.id,
            final_hash=final_hash,
            terminal_audit_hash=terminal_audit_hash,
            completion_iso=ts_iso,
        )
        self.assertTrue(len(seal) == 64)

        # Verification success
        self.assertTrue(verify_completion_seal(
            envelope_id=self.envelope.id,
            final_hash=final_hash,
            terminal_audit_hash=terminal_audit_hash,
            completion_iso=ts_iso,
            seal=seal,
        ))

        # Tampered final hash
        self.assertFalse(verify_completion_seal(
            envelope_id=self.envelope.id,
            final_hash=hashlib.sha256(b"tampered").hexdigest(),
            terminal_audit_hash=terminal_audit_hash,
            completion_iso=ts_iso,
            seal=seal,
        ))

        # Tampered envelope ID
        self.assertFalse(verify_completion_seal(
            envelope_id=9999,
            final_hash=final_hash,
            terminal_audit_hash=terminal_audit_hash,
            completion_iso=ts_iso,
            seal=seal,
        ))

    def test_document_integrity_verification_full_cycle(self):
        """Verifies complete document integrity lifecycle and tamper detection."""
        signed_pdf_bytes = b"%PDF-1.4\nFinal Stamped PDF Content\n%%EOF"
        final_hash = hashlib.sha256(signed_pdf_bytes).hexdigest()

        # Create audit logs
        AuditLog.objects.create(envelope=self.envelope, event="Created")
        AuditLog.objects.create(envelope=self.envelope, event="Signed")
        AuditLog.objects.create(envelope=self.envelope, event="Completed")

        # Create SignedDocument with aligned final_hash
        signed_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            visual_document_hash=final_hash,
            final_hash=final_hash,
        )
        signed_doc.file.save("final_signed.pdf", ContentFile(signed_pdf_bytes), save=True)

        # Seal envelope
        seal = seal_envelope_completion(self.envelope)
        self.assertIsNotNone(seal)
        signed_doc.refresh_from_db()
        self.assertEqual(signed_doc.completion_seal, seal)

        # Check document integrity
        integrity = verify_document_integrity(self.envelope)
        self.assertTrue(integrity["is_valid"])
        self.assertEqual(integrity["status"], "verified")
        self.assertTrue(integrity["file_hash_match"])
        self.assertTrue(integrity["audit_chain_valid"])

        # Tamper test: modify stored file bytes
        tampered_bytes = b"%PDF-1.4\nMALICIOUS MODIFICATION\n%%EOF"
        signed_doc.file.save("final_signed.pdf", ContentFile(tampered_bytes), save=True)

        tampered_integrity = verify_document_integrity(self.envelope)
        self.assertFalse(tampered_integrity["is_valid"])
        self.assertEqual(tampered_integrity["status"], "tampered")
        self.assertFalse(tampered_integrity["file_hash_match"])

    def test_legacy_unsealed_document_handling(self):
        """Verifies that legacy unsealed documents are classified as legacy_unsealed without errors."""
        legacy_pdf_bytes = b"%PDF-1.4\nLegacy PDF\n%%EOF"
        legacy_hash = hashlib.sha256(legacy_pdf_bytes).hexdigest()

        legacy_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            final_hash=legacy_hash,
            completion_seal="",  # Unsealed
        )
        legacy_doc.file.save("legacy.pdf", ContentFile(legacy_pdf_bytes), save=True)

        integrity = verify_document_integrity(self.envelope)
        self.assertEqual(integrity["status"], "legacy_unsealed")
        self.assertTrue(integrity["file_hash_match"])
        self.assertIn("legacy", integrity["reason"])

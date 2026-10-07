import hashlib
import io
import os
import fitz
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from esign.models import AuditLog, Document, Envelope, Participant, SignedDocument, CompletionCertificate
from services.pades_service import (
    PAdESError,
    PAdESConfigurationError,
    generate_test_credentials,
    sign_pdf_pades,
    verify_pades_signature,
)
from services.integrity_service import (
    verify_document_integrity,
    seal_envelope_completion,
)
from services.workflow_service import check_and_advance_step


class A08PAdESFinalizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pades_user", email="pades@example.com", password="password123")

        # Create a valid minimal PDF with PyMuPDF
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "A08 PAdES Base Document")
        self.sample_pdf_bytes = doc.tobytes()
        doc.close()

        self.document = Document.objects.create(
            owner=self.user,
            file_hash=hashlib.sha256(self.sample_pdf_bytes).hexdigest(),
        )
        self.document.file.save("pades_test.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        self.envelope = Envelope.objects.create(
            document=self.document,
            owner=self.user,
            title="A08 PAdES Envelope",
            status="sent",
        )

    def test_pades_direct_signing_and_verification(self):
        """Tests that sign_pdf_pades creates a valid ETSI PAdES cryptographic signature."""
        cert_pem, key_pem = generate_test_credentials()
        signed_bytes = sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=key_pem)

        self.assertTrue(len(signed_bytes) > len(self.sample_pdf_bytes))
        self.assertTrue(signed_bytes.startswith(b"%PDF"))

        # Verify signature
        res = verify_pades_signature(signed_bytes)
        self.assertTrue(res["is_signed"])
        self.assertTrue(res["signature_valid"])
        self.assertTrue(res["intact"])
        self.assertEqual(res["signature_count"], 1)

    def test_pades_tampered_pdf_detection(self):
        """Verifies that tampering with a PAdES signed PDF invalidates the signature."""
        cert_pem, key_pem = generate_test_credentials()
        signed_bytes = sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=key_pem)

        # Tamper single byte in middle
        tampered_bytes = signed_bytes[:500] + b"Z" + signed_bytes[501:]
        res = verify_pades_signature(tampered_bytes)
        self.assertFalse(res["signature_valid"])

    def test_malformed_pdf_fails_safely(self):
        """Verifies that non-PDF bytes raise PAdESError cleanly."""
        with self.assertRaises(PAdESError):
            sign_pdf_pades(b"NOT A PDF DOCUMENT")

    def test_invalid_key_fails_closed(self):
        """Verifies that an invalid key raises PAdESConfigurationError."""
        cert_pem, _ = generate_test_credentials()
        with self.assertRaises(PAdESConfigurationError):
            sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=b"INVALID KEY DATA")

    @override_settings(A08_PADES_ENABLED=False)
    def test_pades_disabled_preserves_visual_hash_behavior(self):
        """When PAdES is disabled, workflow completes with visual PDF and no PAdES signature."""
        # Create participant and signed doc
        p = Participant.objects.create(envelope=self.envelope, name="Alice", email="alice@test.com", step_number=1, status="completed")
        
        visual_hash = hashlib.sha256(self.sample_pdf_bytes).hexdigest()
        signed_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            visual_document_hash=visual_hash,
            final_hash=visual_hash,
        )
        signed_doc.file.save("doc.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        check_and_advance_step(self.envelope, current_step=1)

        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, "completed")

        signed_doc.refresh_from_db()
        self.assertEqual(signed_doc.final_hash, visual_hash)
        self.assertTrue(bool(signed_doc.completion_seal))

        # Integrity verification
        integrity = verify_document_integrity(self.envelope)
        self.assertTrue(integrity["is_valid"])
        self.assertFalse(integrity["pades_signed"])

    @override_settings(A08_PADES_ENABLED=True)
    def test_pades_enabled_one_signer_full_lifecycle(self):
        """When PAdES is enabled, completing envelope seals document with PAdES."""
        p = Participant.objects.create(envelope=self.envelope, name="Alice", email="alice@test.com", step_number=1, status="completed")
        
        visual_hash = hashlib.sha256(self.sample_pdf_bytes).hexdigest()
        signed_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            visual_document_hash=visual_hash,
            final_hash=visual_hash,
        )
        signed_doc.file.save("doc.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        check_and_advance_step(self.envelope, current_step=1)

        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, "completed")

        signed_doc.refresh_from_db()
        # Final hash must now match the PAdES signed PDF
        signed_doc.file.open("rb")
        pades_bytes = signed_doc.file.read()
        signed_doc.file.close()

        expected_pades_hash = hashlib.sha256(pades_bytes).hexdigest()
        self.assertEqual(signed_doc.final_hash, expected_pades_hash)
        self.assertNotEqual(signed_doc.visual_document_hash, signed_doc.final_hash)
        self.assertTrue(bool(signed_doc.completion_seal))

        # Integrity verification checks PAdES signature validity
        integrity = verify_document_integrity(self.envelope)
        self.assertTrue(integrity["is_valid"])
        self.assertTrue(integrity["pades_signed"])
        self.assertTrue(integrity["pades_valid"])
        self.assertEqual(integrity["status"], "verified")

    @override_settings(A08_PADES_ENABLED=True)
    def test_pades_enabled_multi_signer_sequential_workflow(self):
        """Verifies multi-signer sequential workflow applies visual stamps and one final PAdES seal."""
        p1 = Participant.objects.create(envelope=self.envelope, name="Signer 1", email="s1@test.com", step_number=1, status="completed")
        p2 = Participant.objects.create(envelope=self.envelope, name="Signer 2", email="s2@test.com", step_number=2, status="pending")

        # Step 1: Signer 1 completes
        visual_hash_1 = hashlib.sha256(self.sample_pdf_bytes).hexdigest()
        signed_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            visual_document_hash=visual_hash_1,
            final_hash=visual_hash_1,
        )
        signed_doc.file.save("doc.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        check_and_advance_step(self.envelope, current_step=1)

        self.envelope.refresh_from_db()
        # Envelope remains sent for Step 2
        self.assertEqual(self.envelope.status, "sent")
        p2.refresh_from_db()
        self.assertEqual(p2.status, "active")

        # Step 2: Signer 2 applies visual signature
        doc2 = fitz.open(stream=self.sample_pdf_bytes, filetype="pdf")
        doc2[0].insert_text((72, 200), "Signer 2 Visual Signature")
        visual_bytes_2 = doc2.tobytes()
        doc2.close()

        visual_hash_2 = hashlib.sha256(visual_bytes_2).hexdigest()
        signed_doc.visual_document_hash = visual_hash_2
        signed_doc.final_hash = visual_hash_2
        signed_doc.file.save("doc.pdf", ContentFile(visual_bytes_2), save=True)

        p2.status = "completed"
        p2.save()

        # Step 2 finishes -> Envelope completes and seals
        check_and_advance_step(self.envelope, current_step=2)

        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, "completed")

        signed_doc.refresh_from_db()
        signed_doc.file.open("rb")
        final_pdf_bytes = signed_doc.file.read()
        signed_doc.file.close()

        final_pades_hash = hashlib.sha256(final_pdf_bytes).hexdigest()
        self.assertEqual(signed_doc.final_hash, final_pades_hash)

        # Integrity verification
        integrity = verify_document_integrity(self.envelope)
        self.assertTrue(integrity["is_valid"])
        self.assertTrue(integrity["pades_signed"])
        self.assertTrue(integrity["pades_valid"])
        self.assertTrue(integrity["audit_chain_valid"])
        self.assertEqual(integrity["status"], "verified")

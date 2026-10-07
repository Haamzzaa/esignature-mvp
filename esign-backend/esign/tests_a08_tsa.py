import hashlib
import io
import fitz
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from esign.models import AuditLog, Document, Envelope, Participant, SignedDocument
from services.pades_service import (
    PAdESError,
    PAdESConfigurationError,
    generate_test_credentials,
    sign_pdf_pades,
    verify_pades_signature,
)
from services.timestamp_service import (
    TSAError,
    TSAConfigurationError,
    TSARequestError,
    RetryingHTTPTimeStamper,
    generate_test_tsa_credentials,
    get_test_timestamper,
)
from services.integrity_service import (
    verify_document_integrity,
    seal_envelope_completion,
)
from services.workflow_service import check_and_advance_step


class A08RFC3161TimestampingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tsa_user", email="tsa@example.com", password="password123")

        # Create valid PDF
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "A08 RFC-3161 TSA Document")
        self.sample_pdf_bytes = doc.tobytes()
        doc.close()

        self.document = Document.objects.create(
            owner=self.user,
            file_hash=hashlib.sha256(self.sample_pdf_bytes).hexdigest(),
        )
        self.document.file.save("tsa_test.pdf", ContentFile(self.sample_pdf_bytes), save=True)

        self.envelope = Envelope.objects.create(
            document=self.document,
            owner=self.user,
            title="A08 TSA Envelope",
            status="sent",
        )

    @override_settings(A08_PADES_ENABLED=True, A08_TSA_ENABLED=False)
    def test_tsa_disabled_produces_pades_bb(self):
        """When TSA is disabled, finalization produces PAdES-B-B without timestamp token."""
        cert_pem, key_pem = generate_test_credentials()
        signed_bytes = sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=key_pem)

        res = verify_pades_signature(signed_bytes)
        self.assertTrue(res["is_signed"])
        self.assertTrue(res["signature_valid"])
        sig_0 = res["signatures"][0]
        self.assertFalse(sig_0["is_timestamped"])
        self.assertEqual(sig_0["pades_type"], "PAdES-B-B")

    @override_settings(A08_PADES_ENABLED=True, A08_TSA_ENABLED=True)
    def test_tsa_enabled_produces_pades_bt(self):
        """When TSA is enabled, finalization embeds RFC-3161 token producing PAdES-B-T."""
        cert_pem, key_pem = generate_test_credentials()
        signed_bytes = sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=key_pem)

        res = verify_pades_signature(signed_bytes)
        self.assertTrue(res["is_signed"])
        self.assertTrue(res["signature_valid"])
        sig_0 = res["signatures"][0]
        self.assertTrue(sig_0["is_timestamped"])
        self.assertTrue(sig_0["timestamp_valid"])
        self.assertEqual(sig_0["pades_type"], "PAdES-B-T")
        self.assertIsNotNone(sig_0["timestamp_time"])

    @override_settings(A08_PADES_ENABLED=False, A08_TSA_ENABLED=True)
    def test_invalid_config_tsa_without_pades_fails_closed(self):
        """Enabling TSA without PAdES is an invalid configuration and must raise an error."""
        with self.assertRaises(PAdESConfigurationError):
            sign_pdf_pades(self.sample_pdf_bytes)

    @override_settings(A08_PADES_ENABLED=True, A08_TSA_ENABLED=True)
    def test_tsa_enabled_full_envelope_completion_lifecycle(self):
        """Verifies full envelope completion with PAdES-B-T and hash seal alignment."""
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
        signed_doc.file.open("rb")
        final_bytes = signed_doc.file.read()
        signed_doc.file.close()

        # final_hash must match exact post-timestamped PAdES-B-T bytes
        expected_hash = hashlib.sha256(final_bytes).hexdigest()
        self.assertEqual(signed_doc.final_hash, expected_hash)
        self.assertTrue(bool(signed_doc.completion_seal))

        # Integrity check confirms PAdES-B-T
        integrity = verify_document_integrity(self.envelope)
        self.assertTrue(integrity["is_valid"])
        self.assertTrue(integrity["pades_signed"])
        self.assertEqual(integrity["pades_type"], "PAdES-B-T")
        self.assertIsNotNone(integrity["timestamp_info"])
        self.assertTrue(integrity["timestamp_info"]["valid"])

    def test_tampered_timestamped_pdf_fails_verification(self):
        """Modifying a PAdES-B-T timestamped PDF is detected and invalidates the document."""
        cert_pem, key_pem = generate_test_credentials()
        timestamper = get_test_timestamper()
        signed_bytes = sign_pdf_pades(self.sample_pdf_bytes, cert_pem=cert_pem, key_pem=key_pem, timestamper=timestamper)

        tampered_bytes = signed_bytes[:1000] + b"BAD" + signed_bytes[1003:]
        res = verify_pades_signature(tampered_bytes)
        self.assertFalse(res["signature_valid"])

    def test_retrying_http_timestamper_retry_and_exhaustion(self):
        """Verifies RetryingHTTPTimeStamper enforces max 1 retry with bounded backoff and fails closed."""
        stamper = RetryingHTTPTimeStamper(
            url="http://invalid-tsa-test-domain-999.local/tsa",
            timeout=1,
            max_retries=1,
            retry_delay=0.01,
        )

        import asyncio
        with self.assertRaises(TSARequestError):
            asyncio.run(stamper.async_request_tsa_response(b"dummy_req"))

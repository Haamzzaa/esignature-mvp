import os
import sys
import django
from django.test import RequestFactory
from django.utils import timezone
from datetime import timedelta

# Setup django environment
BASE_DIR = r"c:\Users\Mohammed Hamza\esign_Module\esign-backend"
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ['*']

from esign.models import Envelope, Participant, Document, SignerIdentityVerification, BiometricVerification, ContractAnalysis, VerificationSession, ParticipantToken, AuditLog, SignedDocument
from services.signing_service import process_action
from django.db import transaction

def run_tests():
    print("=" * 50)
    print("Testing Signing Integration & Audit Log...")
    print("=" * 50)

    rf = RequestFactory()
    request = rf.post('/signing/test-token/', data={"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"})
    request.META['REMOTE_ADDR'] = '127.0.0.1'
    request.META['HTTP_USER_AGENT'] = 'TestClient'

    with transaction.atomic():
        # Setup dummy envelope & participant
        from django.contrib.auth.models import User
        user = User.objects.first() or User.objects.create(username="auth_test_user")
        
        # Load a real/dummy PDF file for Document model to avoid file validation error.
        pdf_path = os.path.join(BASE_DIR, "tools", "contract_001_transport_contract.pdf")
        from django.core.files.base import ContentFile
        with open(pdf_path, 'rb') as f:
            django_file = ContentFile(f.read(), name="contract_001_transport_contract.pdf")
            doc = Document.objects.create(file=django_file, file_hash="auth_test_hash", owner=user)
        
        envelope = Envelope.objects.create(document=doc, owner=user)
        envelope.email_otp_required = False
        envelope.sms_otp_required = False
        envelope.terms_acceptance_required = False
        envelope.national_id_required = True
        envelope.face_biometric_required = True
        envelope.representative_match_required = True
        envelope.status = "sent"
        envelope.save()
        
        participant = Participant.objects.create(
            envelope=envelope,
            name="Alice Tester",
            email="alice@example.com",
            role="signer",
            status="active"
        )

        token_obj = ParticipantToken.objects.create(
            participant=participant,
            token="12345678-1234-5678-1234-567812345678",
            is_used=False,
            expires_at=timezone.now() + timedelta(days=1)
        )

        verification = SignerIdentityVerification.objects.create(
            participant=participant,
            status="verified",
            full_name_en="Alice Tester",
            full_name_ar="اليس تيستر",
            full_name="Alice Tester"
        )

        session = VerificationSession.objects.create(
            participant=participant,
            status="completed"
        )
        
        biometric = BiometricVerification.objects.create(
            participant=participant,
            verification_session=session,
            status="matched"
        )

        analysis = ContractAnalysis.objects.create(
            document=doc,
            file_hash="auth_test_hash",
            representatives=[
                {
                    "name_en": "Alice Tester",
                    "name_ar": "اليس تيستر",
                    "role": "CEO",
                    "signature_label": "Signer A",
                    "authority_text": "Clause 1"
                }
            ]
        )

        # Pre-clean any audit logs created
        AuditLog.objects.filter(envelope=envelope).delete()

        # Test Case 1: Authorized signer -> Expected AUTHORIZED
        print("\n--- Test Case 1: Authorized signer ---")
        res, err = process_action("12345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err is None
        assert res["status"] == "completed" or res["status"] == "sent"
        
        # Verify Audit Log events
        events = list(AuditLog.objects.filter(envelope=envelope).values_list('event', flat=True))
        print("Audit events recorded:", events)
        assert "Authorization passed" in events

        # Cleanup for next tests
        token_obj.is_used = False
        token_obj.save()
        envelope.status = "sent"
        envelope.save()
        participant.status = "active"
        participant.save()
        SignedDocument.objects.filter(envelope=envelope).delete()
        AuditLog.objects.filter(envelope=envelope).delete()

        # Test Case 2: Mismatching signer name -> Expected NOT_AUTHORIZED (AUTHORIZATION_FAILED)
        print("\n--- Test Case 2: Unauthorized signer ---")
        verification.full_name_en = "Bob Tester"
        verification.full_name_ar = "بوب تيستر"
        verification.save()
        
        res, err = process_action("12345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Bob Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "AUTHORIZATION_FAILED"
        assert res["status"] == "NOT_AUTHORIZED"
        
        events = list(AuditLog.objects.filter(envelope=envelope).values_list('event', flat=True))
        print("Audit events recorded:", events)
        assert "Authorization failed" in events

        # Restore name, reset token & audit
        verification.full_name_en = "Alice Tester"
        verification.full_name_ar = "اليس تيستر"
        verification.save()
        token_obj.is_used = False
        token_obj.save()
        envelope.status = "sent"
        envelope.save()
        participant.status = "active"
        participant.save()
        SignedDocument.objects.filter(envelope=envelope).delete()
        AuditLog.objects.filter(envelope=envelope).delete()

        # Test Case 3: Failed biometric -> Expected NOT_AUTHORIZED (BIOMETRIC_FAILED)
        print("\n--- Test Case 3: Failed biometric ---")
        biometric.status = "failed"
        biometric.save()
        
        res, err = process_action("12345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "BIOMETRIC_FAILED"
        assert res["status"] == "NOT_AUTHORIZED"
        
        events = list(AuditLog.objects.filter(envelope=envelope).values_list('event', flat=True))
        print("Audit events recorded:", events)
        assert "Authorization failed" in events

        # Restore biometric, reset token & audit
        biometric.status = "matched"
        biometric.save()
        token_obj.is_used = False
        token_obj.save()
        envelope.status = "sent"
        envelope.save()
        participant.status = "active"
        participant.save()
        SignedDocument.objects.filter(envelope=envelope).delete()
        AuditLog.objects.filter(envelope=envelope).delete()
        token_obj.save()
        AuditLog.objects.filter(envelope=envelope).delete()

        # Test Case 4: Manual review required -> Expected MANUAL_REVIEW_REQUIRED
        print("\n--- Test Case 4: Manual review required ---")
        analysis.representatives = []
        analysis.save()
        
        res, err = process_action("12345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "MANUAL_REVIEW_REQUIRED"
        assert res["status"] == "MANUAL_REVIEW_REQUIRED"
        
        events = list(AuditLog.objects.filter(envelope=envelope).values_list('event', flat=True))
        print("Audit events recorded:", events)
        assert "Manual review required" in events

        print("\nAll 4 signing integration tests passed successfully!")
        raise Exception("Rollback transaction")

try:
    run_tests()
except Exception as e:
    if str(e) == "Rollback transaction":
        print("\nDatabase transaction rolled back successfully.")
    else:
        raise

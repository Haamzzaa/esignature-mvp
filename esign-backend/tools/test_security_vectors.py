import os
import sys
import django
from django.test import RequestFactory

# Setup django environment
BASE_DIR = r"c:\Users\Mohammed Hamza\esign_Module\esign-backend"
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS = ['*']

from esign.models import Envelope, Participant, Document, SignerIdentityVerification, BiometricVerification, ContractAnalysis, VerificationSession, ParticipantToken, AuditLog
from services.signing_service import process_action
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

def run_security_tests():
    print("=" * 50)
    print("Running Security Vectors Validation...")
    print("=" * 50)

    rf = RequestFactory()
    request = rf.post('/signing/test-token/', data={"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"})
    request.META['REMOTE_ADDR'] = '127.0.0.1'
    request.META['HTTP_USER_AGENT'] = 'TestClient'

    with transaction.atomic():
        from django.contrib.auth.models import User
        user = User.objects.first() or User.objects.create(username="security_test_user")
        
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
            token="22345678-1234-5678-1234-567812345678",
            is_used=False,
            expires_at=timezone.now() + timedelta(days=1)
        )

        # Vector 1: Workflow bypass attempt (No ID OCR, no biometrics completed yet)
        print("\n--- Vector 1: Workflow bypass check ---")
        res, err = process_action("22345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "IDENTITY_OCR_FAILED", f"Expected IDENTITY_OCR_FAILED, got {err}"
        print("Bypass successfully prevented: identity verification incomplete.")

        # Complete identity verification but no biometric verification
        verification = SignerIdentityVerification.objects.create(
            participant=participant,
            status="verified",
            full_name_en="Alice Tester",
            full_name_ar="اليس تيستر",
            full_name="Alice Tester"
        )

        # Vector 2: Biometric verification bypass attempt
        print("\n--- Vector 2: Biometric bypass check ---")
        res, err = process_action("22345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "BIOMETRIC_FAILED", f"Expected BIOMETRIC_FAILED, got {err}"
        print("Bypass successfully prevented: face biometric verification failed.")

        # Complete biometrics but no contract analysis
        session = VerificationSession.objects.create(
            participant=participant,
            status="completed"
        )
        biometric = BiometricVerification.objects.create(
            participant=participant,
            verification_session=session,
            status="matched"
        )

        # Vector 3: Expired Token attempt
        print("\n--- Vector 3: Expired token check ---")
        token_obj.expires_at = timezone.now() - timedelta(minutes=5)
        token_obj.save()
        res, err = process_action("22345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "This signing link has expired.", f"Expected 'This signing link has expired.', got '{err}'"
        print("Expired token successfully blocked.")

        # Restore token expiration for used check
        token_obj.expires_at = timezone.now() + timedelta(days=1)
        token_obj.is_used = True
        token_obj.save()

        # Vector 4: Replay Used Token attempt
        print("\n--- Vector 4: Replay used token check ---")
        res, err = process_action("22345678-1234-5678-1234-567812345678", {"action": "sign", "signature_type": "typed", "signature_text": "Alice Tester"}, request)
        print("Result:", res, "Err:", err)
        assert err == "Your step has already been completed.", f"Expected 'Your step has already been completed.', got '{err}'"
        print("Used token replay successfully blocked.")

        print("\nAll programmatic security checks verified successfully!")
        raise Exception("Rollback transaction")

try:
    run_security_tests()
except Exception as e:
    if str(e) == "Rollback transaction":
        print("\nDatabase transaction rolled back successfully.")
    else:
        raise

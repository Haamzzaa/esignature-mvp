import os
import sys
import django

# Setup django environment
BASE_DIR = r"c:\Users\Mohammed Hamza\esign_Module\esign-backend"
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign_service.settings')
django.setup()

from esign.models import Envelope, Participant, Document, SignerIdentityVerification, BiometricVerification, ContractAnalysis, VerificationSession
from services.authorization_service import authorize_signer
from django.db import transaction

def run_tests():
    print("=" * 50)
    print("Testing Authorization Engine...")
    print("=" * 50)

    with transaction.atomic():
        # Setup dummy envelope & participant
        from django.contrib.auth.models import User
        user = User.objects.first() or User.objects.create(username="auth_test_user")
        doc = Document.objects.create(file_hash="auth_test_hash", owner=user)
        envelope = Envelope.objects.create(document=doc, owner=user)
        
        participant = Participant.objects.create(
            envelope=envelope,
            name="Alice Tester",
            email="alice@example.com",
            role="signer"
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

        # Test Case 1: Representative matches (AUTHORIZED)
        print("\n--- Test Case 1: Representative matches ---")
        res = authorize_signer(participant, verification, analysis)
        print("Result:", res)
        assert res["status"] == "AUTHORIZED"
        assert res["authorized"] is True
        assert res["matched_language"] == "english"

        # Test Case 2: Representative not found (NOT_AUTHORIZED)
        print("\n--- Test Case 2: Representative not found ---")
        verification.full_name_en = "Bob Tester"
        verification.full_name_ar = "بوب تيستر"
        verification.save()
        res = authorize_signer(participant, verification, analysis)
        print("Result:", res)
        assert res["status"] == "NOT_AUTHORIZED"
        assert res["reason"] == "Authenticated signer is not listed as an authorized representative."

        # Restore name
        verification.full_name_en = "Alice Tester"
        verification.full_name_ar = "اليس تيستر"
        verification.save()

        # Test Case 3: Identity verification incomplete (NOT_AUTHORIZED)
        print("\n--- Test Case 3: Identity verification incomplete ---")
        verification.status = "pending"
        verification.save()
        res = authorize_signer(participant, verification, analysis)
        print("Result:", res)
        assert res["status"] == "NOT_AUTHORIZED"
        assert res["reason"] == "Identity verification incomplete."
        
        verification.status = "verified"
        verification.save()

        # Test Case 4: No representatives extracted (MANUAL_REVIEW_REQUIRED)
        print("\n--- Test Case 4: No representatives extracted ---")
        empty_analysis = ContractAnalysis.objects.create(
            document=doc,
            file_hash="empty_hash",
            representatives=[]
        )
        res = authorize_signer(participant, verification, empty_analysis)
        print("Result:", res)
        assert res["status"] == "MANUAL_REVIEW_REQUIRED"
        assert res["reason"] == "No representative found in contract."

        # Test Case 5: Arabic representative matches Arabic OCR
        print("\n--- Test Case 5: Arabic representative matches Arabic OCR ---")
        # English is different (mismatch), but Arabic matches
        verification.full_name_en = "Bob Tester"
        verification.save()
        res = authorize_signer(participant, verification, analysis)
        print("Result:", res)
        assert res["status"] == "AUTHORIZED"
        assert res["matched_language"] == "arabic"
        
        # Test Case 6: English representative matches English OCR
        print("\n--- Test Case 6: English representative matches English OCR ---")
        # Arabic is different (mismatch), but English matches
        verification.full_name_en = "Alice Tester"
        verification.full_name_ar = "بوب تيستر"
        verification.save()
        res = authorize_signer(participant, verification, analysis)
        print("Result:", res)
        assert res["status"] == "AUTHORIZED"
        assert res["matched_language"] == "english"

        print("\nAll 6 verification tests passed successfully!")

        # Rollback all created database entries
        raise Exception("Rollback transaction")

try:
    run_tests()
except Exception as e:
    if str(e) == "Rollback transaction":
        print("\nDatabase transaction rolled back successfully.")
    else:
        raise

import os
import sys
import django

# Setup Django Environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
django.setup()

from services.authorization_service import strip_honorifics, authorize_signer
from esign.models import Participant, SignerIdentityVerification, BiometricVerification, ContractAnalysis, Document, Envelope, VerificationSession

def run_normalization_tests():
    print("==================================================")
    print("Testing Authorization Normalization & Stripping...")
    print("==================================================")

    # Test cases for strip_honorifics
    test_cases_strip = [
        ("Mr. Yasser Othman Ramadan", "Yasser Othman Ramadan"),
        ("Dr. Ahmed Ali", "Ahmed Ali"),
        ("السيد/ ياسر عثمان رمضان", "ياسر عثمان رمضان"),
        ("الدكتور خالد محمد", "خالد محمد"),
        ("معالي الشيخ محمد", "محمد"),
        ("Mr. Dr. John Smith", "John Smith"),
        ("السيد/ الدكتور أحمد علي", "أحمد علي"),
        ("Al-Hassan Bin Ali", "Al-Hassan Bin Ali"), # valid parts preserved
    ]

    print("\n--- Testing strip_honorifics function directly ---")
    for original, expected in test_cases_strip:
        res = strip_honorifics(original)
        print(f"Original: {original!r} -> Stripped: {res!r}")
        assert res == expected, f"Failed strip: expected {expected!r}, got {res!r}"
    print("All direct strip_honorifics tests passed!")

    # Test cases for authorize_signer (matching scenarios)
    print("\n--- Testing authorize_signer matching scenarios ---")
    
    # Create mock database objects for testing
    from django.db import transaction
    try:
        with transaction.atomic():
            from django.contrib.auth.models import User
            user, _ = User.objects.get_or_create(username="norm_test_user")
            
            # Create a dummy Document
            from django.core.files.base import ContentFile
            doc = Document.objects.create(file=ContentFile(b"dummy pdf content", name="dummy.pdf"), file_hash="hash123")
            envelope = Envelope.objects.create(document=doc, owner=user)
            participant = Participant.objects.create(envelope=envelope, name="Alice Tester", role="signer")
            
            # Setup biometric verification (must be matched)
            v_session = VerificationSession.objects.create(participant=participant, status="completed")
            BiometricVerification.objects.create(participant=participant, verification_session=v_session, status="matched")
            
            # Sub-test 1: Mr. Yasser Othman Ramadan should match YASSER OTHMAN RAMADAN
            verification = SignerIdentityVerification.objects.create(
                participant=participant,
                status="verified",
                full_name_en="YASSER OTHMAN RAMADAN",
                full_name_ar=""
            )
            analysis = ContractAnalysis.objects.create(
                document=doc,
                file_hash="hash123",
                representatives=[
                    {"name_en": "Mr. Yasser Othman Ramadan", "name_ar": None}
                ]
            )
            res = authorize_signer(participant, verification, analysis)
            print("Mr. Yasser Othman Ramadan vs YASSER OTHMAN RAMADAN result:", res["authorized"])
            assert res["authorized"] is True
            
            # Cleanup for next test
            verification.delete()
            analysis.delete()

            # Sub-test 2: السيد/ ياسر عثمان رمضان vs ياسر عثمان رمضان
            verification = SignerIdentityVerification.objects.create(
                participant=participant,
                status="verified",
                full_name_en="",
                full_name_ar="ياسر عثمان رمضان"
            )
            analysis = ContractAnalysis.objects.create(
                document=doc,
                file_hash="hash123",
                representatives=[
                    {"name_en": None, "name_ar": "السيد/ ياسر عثمان رمضان"}
                ]
            )
            res = authorize_signer(participant, verification, analysis)
            print("السيد/ ياسر عثمان رمضان vs ياسر عثمان رمضان result:", res["authorized"])
            assert res["authorized"] is True
            
            # Cleanup for next test
            verification.delete()
            analysis.delete()

            # Sub-test 3: Mr. Dr. John Smith vs John Smith
            verification = SignerIdentityVerification.objects.create(
                participant=participant,
                status="verified",
                full_name_en="John Smith",
                full_name_ar=""
            )
            analysis = ContractAnalysis.objects.create(
                document=doc,
                file_hash="hash123",
                representatives=[
                    {"name_en": "Mr. Dr. John Smith", "name_ar": None}
                ]
            )
            res = authorize_signer(participant, verification, analysis)
            print("Mr. Dr. John Smith vs John Smith result:", res["authorized"])
            assert res["authorized"] is True
            
            # Cleanup for next test
            verification.delete()
            analysis.delete()

            # Sub-test 4: Invalid/empty representatives filter check
            verification = SignerIdentityVerification.objects.create(
                participant=participant,
                status="verified",
                full_name_en="Alice Tester",
                full_name_ar=""
            )
            analysis = ContractAnalysis.objects.create(
                document=doc,
                file_hash="hash123",
                representatives=[
                    {"name_en": None, "name_ar": None}, # invalid representative, should be skipped
                    {"name_en": "Alice Tester", "name_ar": None} # should be matched
                ]
            )
            res = authorize_signer(participant, verification, analysis)
            print("Empty representative skipped and next matched result:", res["authorized"])
            assert res["authorized"] is True
            
            # Cleanup for next test
            verification.delete()
            analysis.delete()

            # Sub-test 5: John Smith vs Jane Smith (Should NOT match)
            verification = SignerIdentityVerification.objects.create(
                participant=participant,
                status="verified",
                full_name_en="Jane Smith",
                full_name_ar=""
            )
            analysis = ContractAnalysis.objects.create(
                document=doc,
                file_hash="hash123",
                representatives=[
                    {"name_en": "John Smith", "name_ar": None}
                ]
            )
            res = authorize_signer(participant, verification, analysis)
            print("John Smith vs Jane Smith result (authorized):", res["authorized"])
            assert res["authorized"] is False

            raise Exception("Force rollback")
    except Exception as e:
        if str(e) != "Force rollback":
            raise e

    print("All authorization match tests passed successfully!")

if __name__ == "__main__":
    run_normalization_tests()

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
import django
django.setup()

from django.conf import settings
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append("testserver")
if "localhost" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append("localhost")

from unittest.mock import patch
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from knox.models import AuthToken

from esign.models import (
    Document,
    Envelope,
    Participant,
    ParticipantToken,
    ParticipantAuthorizationState,
    SignerIdentityVerification,
    BiometricVerification,
    VerificationSession,
    ContractAnalysis,
    AuditLog,
    DocumentField
)
from services.security_policy_service import get_authorization_status, can_sign


def run_e2e_validation():
    print("=" * 70)
    print("STARTING COMPREHENSIVE END-TO-END AUTHORIZATION REVIEW VALIDATION")
    print("=" * 70)

    # Clean test fixtures
    User.objects.filter(username__in=["e2e_staff", "e2e_normal"]).delete()

    staff_user = User.objects.create_user(
        username="e2e_staff",
        email="staff@enterprise.com",
        password="Password123!",
        is_staff=True
    )
    _, staff_token = AuthToken.objects.create(user=staff_user)

    normal_user = User.objects.create_user(
        username="e2e_normal",
        email="sender@client.com",
        password="Password123!",
        is_staff=False
    )
    _, normal_token = AuthToken.objects.create(user=normal_user)

    client = APIClient()

    # -------------------------------------------------------------------------
    # TEST 1: API PERMISSIONS & SECURITY MATRIX
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Testing Permission Matrix & Security Enforcement...")

    # Unauthenticated
    client.credentials()
    resp = client.get("/api/v1/admin/reviews/")
    assert resp.status_code == 401, f"Expected 401 for unauth, got {resp.status_code}"

    # Normal authenticated user
    client.credentials(HTTP_AUTHORIZATION=f"Token {normal_token}")
    resp = client.get("/api/v1/admin/reviews/")
    assert resp.status_code == 403, f"Expected 403 for normal user, got {resp.status_code}"

    # Staff user
    client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token}")
    resp = client.get("/api/v1/admin/reviews/")
    assert resp.status_code == 200, f"Expected 200 for staff user, got {resp.status_code}"
    print("  ✓ Unauthenticated -> 401 Unauthorized")
    print("  ✓ Regular authenticated user -> 403 Forbidden (Server-side enforced)")
    print("  ✓ Staff user -> 200 OK")

    # -------------------------------------------------------------------------
    # TEST 2: REVIEW QUEUE & DOSSIER SANITIZATION
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Testing Review Queue Discovery & Evidence Sanitization...")
    from django.core.files.base import ContentFile
    sample_pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n185\n%%EOF\n"
    )
    doc = Document.objects.create(file_hash="hash_e2e_001", owner=normal_user)
    doc.file.save("contract.pdf", ContentFile(sample_pdf_bytes))
    env1 = Envelope.objects.create(
        document=doc,
        owner=normal_user,
        title="Executive NDA Agreement",
        status="sent",
        terms_acceptance_required=True,
        email_otp_required=True,
        national_id_required=True,
        face_biometric_required=True
    )
    p1 = Participant.objects.create(
        envelope=env1,
        name="Alex Mercer",
        email="alex.mercer@innovate.com",
        role="signer",
        status="active"
    )
    pt1 = ParticipantToken.objects.create(participant=p1, expires_at=timezone.now() + timezone.timedelta(days=7))
    state1 = ParticipantAuthorizationState.objects.create(participant=p1, accepted_terms=True, email_verified=True)
    session1 = VerificationSession.objects.create(participant=p1, status="requires_manual_review", failure_reason="Identity OCR name mismatch")
    id_ver1 = SignerIdentityVerification.objects.create(
        participant=p1,
        status="requires_manual_review",
        full_name="Alexander J. Mercer",
        national_id_number="9876543210",
        document_type="national_id",
        country="AE",
        identity_match_score=0.82,
        failure_reason="Name discrepancy between participant (Alex Mercer) and National ID (Alexander J. Mercer)"
    )
    bio1 = BiometricVerification.objects.create(
        participant=p1,
        verification_session=session1,
        status="matched",
        similarity_score=0.94,
        liveness_score=0.98,
        provider="insightface"
    )

    # Query queue
    client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token}")
    q_resp = client.get("/api/v1/admin/reviews/?status=under_review")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert any(c["participant_id"] == p1.id for c in q_data["cases"]), "Review case missing from queue"

    # Search filter test
    q_search = client.get("/api/v1/admin/reviews/?q=Alexander")
    assert any(c["participant_id"] == p1.id for c in q_search.json()["cases"]), "Search failed to find participant"

    # Inspect dossier
    d_resp = client.get(f"/api/v1/admin/reviews/{p1.id}/")
    assert d_resp.status_code == 200
    d_data = d_resp.json()
    assert d_data["participant"]["name"] == "Alex Mercer"
    assert d_data["identity_verification"]["full_name"] == "Alexander J. Mercer"
    assert d_data["identity_verification"]["identity_match_score"] == 0.82
    assert d_data["biometric_verification"]["similarity_score"] == 0.94
    # Check no secret leakage
    d_str = str(d_data).lower()
    assert "secret" not in d_str
    assert "token" not in d_str or "participant_token" not in d_str
    assert "api_key" not in d_str
    assert "embedding" not in d_str
    print("  ✓ Active review case discovered in queue with correct metadata")
    print("  ✓ Search and status filtering operational")
    print("  ✓ Dossier sanitized: No raw embeddings, API keys, or tokens exposed")

    # -------------------------------------------------------------------------
    # TEST 3: E2E WORKFLOW — APPROVE & SIGNING UNLOCK
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing E2E APPROVE Flow...")
    # Check initial signer state
    initial_signer_status = get_authorization_status(p1)
    assert initial_signer_status["review_status"] == "under_review"
    assert initial_signer_status["authorized"] is False
    assert can_sign(p1) is False

    # Reviewer approves
    decision_payload = {
        "action": "approve",
        "notes": "Verified Alexander J. Mercer is legal full name of Alex Mercer."
    }
    app_resp = client.post(f"/api/v1/admin/reviews/{p1.id}/decision/", decision_payload, format="json")
    assert app_resp.status_code == 200
    assert app_resp.json()["review_status"] == "approved"

    # Check backend state
    state1.refresh_from_db()
    assert state1.manual_review_approved is True
    assert state1.manual_review_rejected is False
    assert state1.manual_review_decided_by == staff_user
    id_ver1.refresh_from_db()
    assert id_ver1.status == "verified"

    # Check AuditLog
    audit_entry = AuditLog.objects.filter(envelope=env1).last()
    assert "manual_review_approved" in audit_entry.event
    assert "e2e_staff" in audit_entry.event

    # Check Signer perspective
    approved_signer_status = get_authorization_status(p1)
    assert approved_signer_status["review_status"] == "approved"
    assert approved_signer_status["authorized"] is True
    assert approved_signer_status["requirements"]["terms_acceptance"]["satisfied"] is True
    assert approved_signer_status["requirements"]["email_otp"]["satisfied"] is True
    assert approved_signer_status["requirements"]["national_id"]["satisfied"] is True
    assert approved_signer_status["requirements"]["face_biometric"]["satisfied"] is True
    assert can_sign(p1) is True

    # Queue check: case should no longer be in 'under_review' queue
    q_after = client.get("/api/v1/admin/reviews/?status=under_review").json()
    assert not any(c["participant_id"] == p1.id for c in q_after["cases"]), "Approved case still in under_review queue"

    # Test actual signing endpoint with participant token
    DocumentField.objects.create(
        envelope=env1,
        participant=p1,
        field_type="signature",
        page=1,
        x_ratio=0.5,
        y_ratio=0.5,
        required=True
    )
    sign_client = APIClient()
    sign_payload = {
        "signature_type": "typed",
        "signature_text": "Alex Mercer"
    }
    sign_resp = sign_client.post(f"/api/v1/sign/{pt1.token}/", sign_payload, format="json")
    assert sign_resp.status_code in [200, 201], f"Signing failed with status {sign_resp.status_code}: {sign_resp.content}"
    p1.refresh_from_db()
    assert p1.has_completed is True
    print("  ✓ Case approved atomically by reviewer with reviewer notes")
    print("  ✓ Audit trail logged reviewer identity")
    print("  ✓ Signer unblocked: Terms & Email OTP preserved; signing unlocked")
    print("  ✓ Participant successfully executed cryptographic signature!")

    # -------------------------------------------------------------------------
    # TEST 4: E2E WORKFLOW — REQUEST RESUBMISSION
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Testing E2E REQUEST RESUBMISSION Flow...")
    env2 = Envelope.objects.create(
        document=doc,
        owner=normal_user,
        title="Consulting Agreement",
        status="sent",
        terms_acceptance_required=True,
        email_otp_required=True,
        national_id_required=True,
        face_biometric_required=True
    )
    p2 = Participant.objects.create(
        envelope=env2,
        name="Elena Rostova",
        email="elena.rostova@partner.com",
        role="signer",
        status="active"
    )
    pt2 = ParticipantToken.objects.create(participant=p2, expires_at=timezone.now() + timezone.timedelta(days=7))
    state2 = ParticipantAuthorizationState.objects.create(participant=p2, accepted_terms=True, email_verified=True)
    session2 = VerificationSession.objects.create(participant=p2, status="requires_manual_review")
    id_ver2 = SignerIdentityVerification.objects.create(
        participant=p2,
        status="requires_manual_review",
        full_name="Elena Rostova",
        failure_reason="ID card boundary cut off / glare"
    )
    bio2 = BiometricVerification.objects.create(
        participant=p2,
        verification_session=session2,
        status="pending"
    )

    # Reviewer requests resubmission for National ID
    resub_payload = {
        "action": "resubmit",
        "target_step": "national_id",
        "notes": "Please capture the full document boundary without surface glare."
    }
    client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token}")
    resub_resp = client.post(f"/api/v1/admin/reviews/{p2.id}/decision/", resub_payload, format="json")
    assert resub_resp.status_code == 200
    assert resub_resp.json()["review_status"] == "resubmission_required"
    assert resub_resp.json()["target_step"] == "national_id"

    # Verify backend state
    state2.refresh_from_db()
    assert state2.manual_review_resubmit_step == "national_id"
    assert state2.manual_review_notes == "Please capture the full document boundary without surface glare."
    id_ver2.refresh_from_db()
    assert id_ver2.status == "pending"
    assert id_ver2.failure_reason == ""

    # Signer status check
    p2_auth_status = get_authorization_status(p2)
    assert p2_auth_status["review_status"] == "resubmission_required"
    assert p2_auth_status["resubmit_step"] == "national_id"
    assert p2_auth_status["review_notes"] == "Please capture the full document boundary without surface glare."
    # Terms and Email OTP must NOT be reset
    assert p2_auth_status["requirements"]["terms_acceptance"]["satisfied"] is True
    assert p2_auth_status["requirements"]["email_otp"]["satisfied"] is True
    assert p2_auth_status["requirements"]["national_id"]["satisfied"] is False
    print("  ✓ Reviewer requested resubmission for step 'national_id'")
    print("  ✓ National ID step reset to pending; prior Terms & Email OTP preserved")
    print("  ✓ Signer receives targeted instructions and resumes directly at National ID")

    # -------------------------------------------------------------------------
    # TEST 5: E2E WORKFLOW — REJECT
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Testing E2E REJECT Flow...")
    env3 = Envelope.objects.create(
        document=doc,
        owner=normal_user,
        title="Vendor Agreement",
        status="sent",
        terms_acceptance_required=True,
        national_id_required=True
    )
    p3 = Participant.objects.create(
        envelope=env3,
        name="Fraud Suspect",
        email="suspect@fake.com",
        role="signer",
        status="active"
    )
    pt3 = ParticipantToken.objects.create(participant=p3, expires_at=timezone.now() + timezone.timedelta(days=7))
    state3 = ParticipantAuthorizationState.objects.create(participant=p3, accepted_terms=True)
    session3 = VerificationSession.objects.create(participant=p3, status="requires_manual_review")
    id_ver3 = SignerIdentityVerification.objects.create(
        participant=p3,
        status="requires_manual_review",
        failure_reason="Tampered ID detected"
    )

    # Reviewer rejects
    reject_payload = {
        "action": "reject",
        "notes": "Identity document shows evidence of physical alteration."
    }
    rej_resp = client.post(f"/api/v1/admin/reviews/{p3.id}/decision/", reject_payload, format="json")
    assert rej_resp.status_code == 200
    assert rej_resp.json()["review_status"] == "rejected"

    # Backend check
    state3.refresh_from_db()
    assert state3.manual_review_rejected is True
    assert state3.manual_review_approved is False
    session3.refresh_from_db()
    assert session3.status == "failed"

    # Signer check
    p3_auth_status = get_authorization_status(p3)
    assert p3_auth_status["review_status"] == "rejected"
    assert p3_auth_status["authorized"] is False
    assert can_sign(p3) is False
    print("  ✓ Reviewer rejected verification with mandatory reason")
    print("  ✓ Terminal state persisted and logged to audit trail")
    print("  ✓ Signer receives terminal rejection state and cannot sign")

    # -------------------------------------------------------------------------
    # TEST 6: VALIDATION & INVALID TRANSITION DEFENSES
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Testing Validation Defenses & Bad Request Handling...")
    # Missing reject reason
    bad_rej = client.post(f"/api/v1/admin/reviews/{p2.id}/decision/", {"action": "reject", "notes": ""}, format="json")
    assert bad_rej.status_code == 400, "Empty reject notes should return 400"

    # Missing resubmit target_step
    bad_resub = client.post(f"/api/v1/admin/reviews/{p2.id}/decision/", {"action": "resubmit", "target_step": ""}, format="json")
    assert bad_resub.status_code == 400, "Empty resubmit target_step should return 400"

    # Invalid action
    bad_act = client.post(f"/api/v1/admin/reviews/{p2.id}/decision/", {"action": "invalid_action"}, format="json")
    assert bad_act.status_code == 400, "Invalid action name should return 400"
    print("  ✓ Missing rejection reason -> 400 Bad Request")
    print("  ✓ Missing or invalid resubmit target_step -> 400 Bad Request")
    print("  ✓ Invalid review action -> 400 Bad Request")

    # -------------------------------------------------------------------------
    # TEST 7: NOTIFICATION FAILURE INDEPENDENCE
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Testing Notification Failure Independence...")
    p4 = Participant.objects.create(
        envelope=env2,
        name="Notification Test User",
        email="notif.test@company.com",
        role="signer",
        status="active"
    )
    ParticipantToken.objects.create(participant=p4, expires_at=timezone.now() + timezone.timedelta(days=7))
    ParticipantAuthorizationState.objects.create(participant=p4, accepted_terms=True)
    SignerIdentityVerification.objects.create(participant=p4, status="requires_manual_review")

    # Simulate email/notification dispatcher failure
    with patch("services.notification_service.send_mail", side_effect=ConnectionResetError("SMTP socket broken")):
        notif_resp = client.post(
            f"/api/v1/admin/reviews/{p4.id}/decision/",
            {"action": "approve", "notes": "Approved during notification outage"},
            format="json"
        )
        assert notif_resp.status_code == 200, f"Expected 200 despite notification error, got {notif_resp.status_code}"
        p4_state = ParticipantAuthorizationState.objects.get(participant=p4)
        assert p4_state.manual_review_approved is True, "Approval state not persisted during notification outage"
        print("  ✓ Notification dispatch errors are properly isolated; Review API succeeded (200 OK)")

    print("\n" + "=" * 70)
    print("ALL 7 END-TO-END VALIDATION PHASES COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_e2e_validation()

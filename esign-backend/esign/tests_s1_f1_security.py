import hashlib
import json
import logging
import re
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from esign.models import (
    Document,
    Envelope,
    Participant,
    ParticipantToken,
    ParticipantAuthorizationState,
    SigningToken,
    Signer,
    User
)
from services.email_otp_service import (
    send_email_otp,
    verify_email_otp,
    EmailDeliveryError,
    OTP_EXPIRY_MINUTES
)
from services.rate_limiting_service import reset_otp_failed_attempts


class S1SignerTokenBindingAndOTPSecurityTests(TestCase):
    """
    Tests for S1 Security Remediation:
    - Signer token-to-participant binding
    - Enumeration prevention
    - Rate limiting and lockout protections
    - Replay prevention and OTP expiry
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner_user",
            email="owner@test.com",
            password="Password@123"
        )
        self.doc = Document.objects.create(
            file="documents/test_contract.pdf",
            file_hash="s1_test_file_hash_12345"
        )
        self.envelope = Envelope.objects.create(
            title="S1 Test Contract",
            owner=self.owner,
            document=self.doc,
            status="sent",
            terms_acceptance_required=True,
            email_otp_required=True
        )

        # Participant 1 (Signer 1)
        self.p1 = Participant.objects.create(
            envelope=self.envelope,
            name="Alice Signer",
            email="alice@test.com",
            role="signer",
            status="active",
            step_number=1
        )
        self.token1 = ParticipantToken.objects.create(
            participant=self.p1,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )

        # Participant 2 (Signer 2)
        self.p2 = Participant.objects.create(
            envelope=self.envelope,
            name="Bob Signer",
            email="bob@test.com",
            role="signer",
            status="active",
            step_number=1
        )
        self.token2 = ParticipantToken.objects.create(
            participant=self.p2,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )

    def tearDown(self):
        cache.clear()

    def test_01_valid_signer_uuid_token_allowed(self):
        """1. Valid signer UUID token allows access to signer endpoint."""
        response = self.client.get(
            f"/api/v1/participants/{self.p1.id}/authorization-status/",
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("status", response.data)

    def test_02_invalid_signer_uuid_token_denied(self):
        """2. Invalid signer UUID token is denied with 403."""
        fake_uuid = str(uuid.uuid4())
        response = self.client.get(
            f"/api/v1/participants/{self.p1.id}/authorization-status/",
            HTTP_X_PARTICIPANT_TOKEN=fake_uuid
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_token_a_plus_participant_b_denied(self):
        """3. Token A used for participant B is denied with 403."""
        response = self.client.post(
            f"/api/v1/participants/{self.p2.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_arbitrary_participant_integer_id_cannot_authorize_signer_action(self):
        """4. Arbitrary participant integer ID cannot perform signer actions."""
        response = self.client.post(f"/api/v1/participants/{self.p1.id}/send-email-otp/", {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_nonexistent_participant_cannot_be_used_for_enumeration(self):
        """5. Nonexistent participant ID returns uniform 403 on missing or mismatched token, preventing enumeration."""
        nonexistent_id = 999999
        # Without token
        r1 = self.client.post(f"/api/v1/participants/{nonexistent_id}/send-email-otp/", {})
        self.assertEqual(r1.status_code, status.HTTP_403_FORBIDDEN)

        # With random token
        fake_token = str(uuid.uuid4())
        r2 = self.client.post(
            f"/api/v1/participants/{nonexistent_id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=fake_token
        )
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)

        # With valid token for p1, but nonexistent ID in URL
        r3 = self.client.post(
            f"/api/v1/participants/{nonexistent_id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r3.status_code, status.HTTP_403_FORBIDDEN)

    def test_06_anonymous_signer_request_without_valid_token_denied(self):
        """6. Anonymous signer request without valid token is denied."""
        endpoints = [
            f"/api/v1/participants/{self.p1.id}/authorization-status/",
            f"/api/v1/participants/{self.p1.id}/accept-terms/",
            f"/api/v1/participants/{self.p1.id}/send-email-otp/",
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            f"/api/v1/participants/{self.p1.id}/face-verification/",
            f"/api/v1/participants/{self.p1.id}/identity-verification/",
        ]
        for url in endpoints:
            r = self.client.get(url) if "authorization-status" in url else self.client.post(url, {})
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, f"Failed on endpoint: {url}")

    def test_07_valid_signer_can_send_otp(self):
        """7. Valid signer can send OTP."""
        response = self.client.post(
            f"/api/v1/participants/{self.p1.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("detail"), "OTP sent.")
        self.assertEqual(response.data.get("email"), self.p1.email)

    def test_08_valid_signer_can_verify_otp(self):
        """8. Valid signer can verify correctly issued OTP."""
        state = send_email_otp(self.p1)
        self.assertEqual(len(mail.outbox), 1)
        sent_message = mail.outbox[0].body
        otp_match = re.search(r'\b\d{6}\b', sent_message)
        self.assertIsNotNone(otp_match)
        otp = otp_match.group(0)

        response = self.client.post(
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            {"otp": otp},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("verified"))

        state.refresh_from_db()
        self.assertTrue(state.email_verified)

    def test_09_otp_expires_correctly(self):
        """9. Expired OTP fails verification and is invalidated."""
        send_email_otp(self.p1)
        sent_message = mail.outbox[0].body
        otp = re.search(r'\b\d{6}\b', sent_message).group(0)

        state = ParticipantAuthorizationState.objects.get(participant=self.p1)
        state.email_otp_expires_at = timezone.now() - timedelta(minutes=1)
        state.save(update_fields=["email_otp_expires_at"])

        response = self.client.post(
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            {"otp": otp},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get("error"), "OTP expired")

        state.refresh_from_db()
        self.assertEqual(state.email_otp_code, "")

    @override_settings(ENABLE_TEST_RATE_LIMITING=True)
    def test_10_repeated_otp_sends_are_rate_limited(self):
        """10. Repeated OTP sends exceed rate limit and return 429."""
        cache.clear()
        for i in range(3):
            r = self.client.post(
                f"/api/v1/participants/{self.p1.id}/send-email-otp/",
                {},
                HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
            )
            self.assertEqual(r.status_code, status.HTTP_200_OK)

        r_limited = self.client.post(
            f"/api/v1/participants/{self.p1.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r_limited.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", r_limited.headers)

    @override_settings(ENABLE_TEST_RATE_LIMITING=True)
    def test_11_repeated_invalid_otp_attempts_trigger_lockout(self):
        """11. Repeated failed OTP verification attempts trigger lockout (429)."""
        cache.clear()
        send_email_otp(self.p1)

        for i in range(5):
            r = self.client.post(
                f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
                {"otp": "000000"},
                HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
            )
            if i < 4:
                self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
            else:
                self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        r_blocked = self.client.post(
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            {"otp": "000000"},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r_blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_12_otp_cannot_be_replayed(self):
        """12. Verified OTP is immediately cleared and cannot be replayed."""
        send_email_otp(self.p1)
        otp = re.search(r'\b\d{6}\b', mail.outbox[0].body).group(0)

        r1 = self.client.post(
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            {"otp": otp},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        r2 = self.client.post(
            f"/api/v1/participants/{self.p1.id}/verify-email-otp/",
            {"otp": otp},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r2.data.get("error"), "No OTP sent")

    def test_13_other_signer_verification_actions_remain_functional(self):
        """13. Terms acceptance works with valid token and rejects unauthorized."""
        r_terms = self.client.post(
            f"/api/v1/participants/{self.p1.id}/accept-terms/",
            {"accepted": True},
            format="json",
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r_terms.status_code, status.HTTP_200_OK)
        self.assertTrue(r_terms.data.get("accepted_terms"))

        r_mismatch = self.client.post(
            f"/api/v1/participants/{self.p2.id}/accept-terms/",
            {"accepted": True},
            format="json",
            HTTP_X_PARTICIPANT_TOKEN=str(self.token1.token)
        )
        self.assertEqual(r_mismatch.status_code, status.HTTP_403_FORBIDDEN)


    def test_14_reviewer_admin_endpoints_remain_unchanged(self):
        """14. Admin review endpoints remain functional for staff and reject non-staff."""
        from knox.models import AuthToken
        staff_user = User.objects.create_user(
            username="staff_rev",
            email="staff@test.com",
            password="Password@123",
            is_staff=True
        )
        _, staff_token = AuthToken.objects.create(user=staff_user)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {staff_token}")
        r_queue = self.client.get("/api/v1/admin/reviews/")
        self.assertEqual(r_queue.status_code, status.HTTP_200_OK)

        # Normal non-staff user receives 403
        normal_user = User.objects.create_user(
            username="normal_user",
            email="normal@test.com",
            password="Password@123",
            is_staff=False
        )
        _, normal_token = AuthToken.objects.create(user=normal_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {normal_token}")
        r_denied = self.client.get("/api/v1/admin/reviews/")
        self.assertEqual(r_denied.status_code, status.HTTP_403_FORBIDDEN)


class F1ReliableEmailOTPDeliveryTests(TestCase):
    """
    Tests for F1 Email Delivery Remediation:
    - Transport to configured email backend
    - Retry on transient transport failure
    - Clean error handling on permanent failure
    - No OTP or credentials logged or exposed
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="f1_owner",
            email="f1_owner@test.com",
            password="Password@123"
        )
        self.doc = Document.objects.create(
            file="documents/f1_test.pdf",
            file_hash="f1_test_file_hash_67890"
        )
        self.envelope = Envelope.objects.create(
            title="F1 Test Package",
            owner=self.owner,
            document=self.doc,
            status="sent",
            email_otp_required=True
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Charlie Signer",
            email="charlie@test.com",
            role="signer",
            status="active"
        )
        self.token = ParticipantToken.objects.create(
            participant=self.participant,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )

    def tearDown(self):
        cache.clear()

    def test_01_otp_request_with_valid_signer_token(self):
        """1. OTP request with valid signer token dispatches successfully."""
        response = self.client.post(
            f"/api/v1/participants/{self.participant.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token.token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["charlie@test.com"])

    def test_02_email_is_actually_handed_to_django_email_backend(self):
        """2. Email is handed to backend with correct subject, recipient, and message."""
        send_email_otp(self.participant)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Your verification code")
        self.assertIn("Charlie Signer", msg.body)
        self.assertIn("Your one-time verification code is:", msg.body)

    @patch("services.email_otp_service.send_mail")
    def test_03_transient_provider_failure_retries_and_succeeds(self, mock_send_mail):
        """3. Transient provider error retries and succeeds on subsequent attempt."""
        mock_send_mail.side_effect = [ConnectionResetError("Transient network drop"), True]

        state = send_email_otp(self.participant)
        self.assertIsNotNone(state)
        self.assertEqual(mock_send_mail.call_count, 2)

    @patch("services.email_otp_service.send_mail")
    def test_04_permanent_provider_failure_handled_safely(self, mock_send_mail):
        """4. Permanent provider failure returns HTTP 503 without exposing stack trace or secrets."""
        mock_send_mail.side_effect = ConnectionRefusedError("SMTP server down")

        response = self.client.post(
            f"/api/v1/participants/{self.participant.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token.token)
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data.get("detail"),
            "Unable to send the verification email. Please try again later."
        )

    def test_05_otp_value_never_exposed_in_api_response(self):
        """5. OTP value is never present in the API response payload."""
        response = self.client.post(
            f"/api/v1/participants/{self.participant.id}/send-email-otp/",
            {},
            HTTP_X_PARTICIPANT_TOKEN=str(self.token.token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resp_json = json.dumps(response.data)
        self.assertIsNone(re.search(r'\b\d{6}\b', resp_json))

    def test_06_otp_value_never_logged(self):
        """6. OTP plaintext is never logged to logger."""
        with self.assertLogs("services.email_otp_service", level="INFO") as log_ctx:
            send_email_otp(self.participant)
            otp = re.search(r'\b\d{6}\b', mail.outbox[0].body).group(0)

            for log_msg in log_ctx.output:
                self.assertNotIn(otp, log_msg, "Security failure: OTP was leaked into log messages!")

    def test_07_notification_emails_and_templates_render(self):
        """7. Existing notification email functions render without errors."""
        from services.notification_service import send_participant_email
        send_participant_email(self.participant, self.envelope)
        self.assertGreaterEqual(len(mail.outbox), 1)
        last_email = mail.outbox[-1]
        self.assertIn("Document waiting for your signature", last_email.subject)
        self.assertIn("F1 Test Package", last_email.body)

    def test_08_signing_workflow_progresses_after_successful_otp(self):
        """8. Authorization status reflects satisfied email_otp after verification."""
        from services.security_policy_service import get_authorization_status
        # Pre-verification status: missing requirements includes email_otp
        auth_pre = get_authorization_status(self.participant)
        self.assertIn("email_otp", auth_pre["missing_requirements"])

        # Send and verify OTP
        send_email_otp(self.participant)
        otp = re.search(r'\b\d{6}\b', mail.outbox[0].body).group(0)
        verify_email_otp(self.participant, otp)

        # Post-verification status: email_otp is satisfied
        auth_post = get_authorization_status(self.participant)
        self.assertTrue(auth_post["requirements"]["email_otp"]["satisfied"])
        self.assertNotIn("email_otp", auth_post["missing_requirements"])


class S2KnoxAuthenticationSecurityTests(TestCase):
    """
    Tests for S2 Security Remediation:
    - Knox token generation on login & registration
    - Header-based Knox authentication
    - Token expiration enforcement
    - Server-side logout token revocation
    - Multi-session coexistence
    - Rejection of invalid / revoked tokens
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="knox_test_user",
            email="knox@test.com",
            password="Password@123"
        )

    def test_01_login_returns_knox_token(self):
        """1. Login returns a valid 64-character Knox token."""
        response = self.client.post(
            "/api/auth/login/",
            {"username": "knox_test_user", "password": "Password@123"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(len(response.data["token"]), 64)
        self.assertEqual(response.data["user"]["username"], "knox_test_user")

    def test_02_register_returns_knox_token(self):
        """2. Registration creates a user and returns a Knox token."""
        response = self.client.post(
            "/api/auth/register/",
            {"username": "new_user", "email": "new@test.com", "password": "Password@123"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertEqual(len(response.data["token"]), 64)

    def test_03_knox_token_authenticates_protected_endpoints(self):
        """3. Authorization: Token <knox_token> authenticates successfully."""
        from knox.models import AuthToken
        _, token = AuthToken.objects.create(user=self.user)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "knox_test_user")

    def test_04_invalid_token_rejected_401(self):
        """4. Invalid Knox tokens are rejected with 401 Unauthorized."""
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid_token_1234567890abcdef")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_05_expired_token_rejected_401(self):
        """5. Expired Knox tokens are rejected with 401 Unauthorized."""
        from knox.models import AuthToken
        instance, token = AuthToken.objects.create(
            user=self.user,
            expiry=timedelta(seconds=-1)
        )

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_06_logout_revokes_token_server_side(self):
        """6. Logout deletes the active Knox token from the database."""
        from knox.models import AuthToken
        instance, token = AuthToken.objects.create(user=self.user)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        r_logout = self.client.post("/api/auth/logout/")
        self.assertEqual(r_logout.status_code, status.HTTP_200_OK)

        # Confirm token is revoked and cannot be reused
        r_after = self.client.get("/api/auth/me/")
        self.assertEqual(r_after.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_07_multiple_knox_sessions_coexist(self):
        """7. Multiple logins generate distinct tokens that both authenticate independently."""
        from knox.models import AuthToken
        _, token1 = AuthToken.objects.create(user=self.user)
        _, token2 = AuthToken.objects.create(user=self.user)

        # Token 1 works
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token1}")
        r1 = self.client.get("/api/auth/me/")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)

        # Token 2 works
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token2}")
        r2 = self.client.get("/api/auth/me/")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        # Logging out session 1 does not invalidate session 2
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token1}")
        self.client.post("/api/auth/logout/")

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token2}")
        r2_still_valid = self.client.get("/api/auth/me/")
        self.assertEqual(r2_still_valid.status_code, status.HTTP_200_OK)


class S3SecurityHeadersTests(TestCase):
    """
    Tests for S3 Security Headers:
    - Content-Security-Policy
    - X-Frame-Options: DENY
    - X-Content-Type-Options: nosniff
    - Referrer-Policy
    - Permissions-Policy
    """

    def setUp(self):
        self.client = APIClient()

    def test_01_backend_middleware_emits_security_headers(self):
        """1. Backend responses include full security headers."""
        response = self.client.get("/live")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("Content-Security-Policy", response.headers)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("frame-src 'self' blob:", csp)

        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=(self)", response.headers.get("Permissions-Policy", ""))


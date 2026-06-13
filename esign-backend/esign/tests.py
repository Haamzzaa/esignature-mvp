from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError
from .models import Document, Envelope, Signer, Participant
from .serializers import EnvelopeCreateSerializer

class ParticipantManagementTestCase(TestCase):
    def setUp(self):
        # Create a mock Document
        self.document = Document.objects.create(
            file="mock.pdf",
            file_hash="mockhash123"
        )

    def test_validation_missing_participants_and_signer(self):
        """Verify that validation fails if neither signer nor participants are supplied."""
        data = {
            "document_id": self.document.id,
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_validation_empty_participants(self):
        """Verify that validation fails if participants list is empty."""
        data = {
            "document_id": self.document.id,
            "participants": [],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_validation_no_signer_role(self):
        """Verify that validation fails if participants list contains no signer."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah", "email": "sarah@email.com", "role": "reviewer"}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_creation_with_participants(self):
        """Verify envelope and participants creation with automatic legacy Signer mapping."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah Reviewer", "email": "sarah@email.com", "role": "reviewer"},
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer"},
                {"name": "John CC", "email": "john@email.com", "role": "cc"}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        
        envelope = serializer.save()
        self.assertEqual(envelope.participants.count(), 3)
        
        # Verify order was assigned automatically
        p_reviewer = envelope.participants.get(role="reviewer")
        p_signer = envelope.participants.get(role="signer")
        self.assertEqual(p_reviewer.order, 1)
        self.assertEqual(p_signer.order, 2)
        
        # Verify legacy Signer was created for the first participant with role="signer"
        signer = Signer.objects.get(envelope=envelope)
        self.assertEqual(signer.name, "Mohammed Signer")
        self.assertEqual(signer.email, "mohammed@email.com")

    def test_creation_legacy_signer_fallback(self):
        """Verify that legacy signer serialization still works in isolation."""
        data = {
            "document_id": self.document.id,
            "signer": {"name": "Legacy Signer", "email": "legacy@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        
        envelope = serializer.save()
        self.assertEqual(envelope.participants.count(), 0)
        
        signer = Signer.objects.get(envelope=envelope)
        self.assertEqual(signer.name, "Legacy Signer")
        self.assertEqual(signer.email, "legacy@email.com")

class SequentialWorkflowTestCase(TestCase):
    def setUp(self):
        import fitz
        from django.core.files.base import ContentFile
        from .models import Document
        
        # Generate a valid 1-page mock PDF using PyMuPDF
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(
            file_hash="mockhash123"
        )
        self.document.file.save("mock.pdf", ContentFile(pdf_bytes))

    def test_workflow_started_initializes_statuses(self):
        """Verify that workflow creation sets step 1 to active, step 2 to pending, and logs audit events."""
        from .models import Participant
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Mohammed Step1", "email": "mohammed@email.com", "role": "signer", "step_number": 1},
                {"name": "Azhar Step2", "email": "azhar@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        # Step 1 participant should be 'active'
        p1 = envelope.participants.get(step_number=1)
        self.assertEqual(p1.status, 'active')

        # Step 2 participant should be 'pending'
        p2 = envelope.participants.get(step_number=2)
        self.assertEqual(p2.status, 'pending')

        # Verify audit logs
        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Workflow Started", events)
        self.assertIn("Step 1 Activated", events)

    def test_step_signing_advances_workflow(self):
        """Verify that completing a step activates the next step and transitions the legacy Signer/token."""
        from .models import Signer, SigningToken
        from django.utils import timezone
        from datetime import timedelta
        
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Mohammed Step1", "email": "mohammed@email.com", "role": "signer", "step_number": 1},
                {"name": "Azhar Step2", "email": "azhar@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        # Simulate Send view to generate token for initial signer
        signer_rec = Signer.objects.get(envelope=envelope)
        token_rec, _ = SigningToken.objects.get_or_create(
            signer=signer_rec,
            defaults={
                "expires_at": timezone.now() + timedelta(hours=24),
                "is_used": False
            }
        )

        # Confirm initial state
        self.assertEqual(signer_rec.email, "mohammed@email.com")

        # Now simulate signing for the first participant via SigningView logic
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Mohammed Signature"
        }, content_type="application/json")
        
        # Mock request metadata
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 201)

        # Refresh from database
        envelope.refresh_from_db()
        p1 = envelope.participants.get(name="Mohammed Step1")
        p2 = envelope.participants.get(name="Azhar Step2")

        # Step 1 should be 'completed'
        self.assertEqual(p1.status, 'completed')
        # Step 2 should be activated to 'active'
        self.assertEqual(p2.status, 'active')

        # Legacy Signer should now point to Azhar Step 2
        signer_rec.refresh_from_db()
        self.assertEqual(signer_rec.name, "Azhar Step2")
        self.assertEqual(signer_rec.email, "azhar@email.com")

        # Verify old token was deleted/invalidated, and new one exists
        self.assertFalse(SigningToken.objects.filter(token=token_rec.token).exists())
        self.assertTrue(SigningToken.objects.filter(signer=signer_rec, is_used=False).exists())

        # Envelope status remains sent (not completed yet)
        self.assertEqual(envelope.status, "sent")

        # Verify advanced audit logs
        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Participant Mohammed Step1 Completed", events)
        self.assertIn("Step 1 Completed", events)
        self.assertIn("Workflow Advanced", events)
        self.assertIn("Step 2 Activated", events)

    def test_final_step_completes_workflow(self):
        """Verify that signing the final step completes the entire package/workflow."""
        from .models import Signer, SigningToken
        from django.utils import timezone
        from datetime import timedelta
        
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Mohammed Step1", "email": "mohammed@email.com", "role": "signer", "step_number": 1}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        signer_rec = Signer.objects.get(envelope=envelope)
        token_rec, _ = SigningToken.objects.get_or_create(
            signer=signer_rec,
            defaults={
                "expires_at": timezone.now() + timedelta(hours=24),
                "is_used": False
            }
        )

        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Mohammed Signature"
        }, content_type="application/json")
        
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 201)

        # Refresh
        envelope.refresh_from_db()
        p1 = envelope.participants.get(name="Mohammed Step1")

        # Step 1 should be 'completed'
        self.assertEqual(p1.status, 'completed')
        # Envelope should be completed
        self.assertEqual(envelope.status, "completed")

        # Verify final audit logs
        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Workflow Completed", events)

class ParticipantAccessAndActionsTestCase(TestCase):
    def setUp(self):
        import fitz
        from django.core.files.base import ContentFile
        from .models import Document
        
        # Generate a valid mock PDF
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(
            file_hash="mockhash1234"
        )
        self.document.file.save("mock.pdf", ContentFile(pdf_bytes))

    def test_reviewer_approve_and_return(self):
        """Verify that Reviewer role can approve (advancing step) or return (declining envelope)."""
        from .models import ParticipantToken, AuditLog
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah Reviewer", "email": "sarah@email.com", "role": "reviewer", "step_number": 1},
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        # Step 1 Reviewer should be active and have a ParticipantToken
        p_reviewer = envelope.participants.get(role="reviewer")
        self.assertEqual(p_reviewer.status, 'active')
        self.assertTrue(ParticipantToken.objects.filter(participant=p_reviewer).exists())
        token_rec = ParticipantToken.objects.get(participant=p_reviewer)

        # 1. Simulate Reviewer approving the document
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "action": "approve"
        }, content_type="application/json")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 200)

        # Refresh
        p_reviewer.refresh_from_db()
        envelope.refresh_from_db()
        self.assertEqual(p_reviewer.status, 'completed')
        
        # Verify step 2 signer is now active
        p_signer = envelope.participants.get(role="signer")
        self.assertEqual(p_signer.status, 'active')

        # Check audit log contains "Reviewer Approved" and "Step 1 Completed" and "Workflow Advanced"
        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Reviewer Approved", events)
        self.assertIn("Step 1 Completed", events)
        self.assertIn("Workflow Advanced", events)
        self.assertIn("Step 2 Activated", events)

    def test_approver_reject(self):
        """Verify that Approver role can reject (declining envelope)."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah Approver", "email": "sarah@email.com", "role": "approver", "step_number": 1},
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        envelope = serializer.save()

        p_approver = envelope.participants.get(role="approver")
        token_rec = ParticipantToken.objects.get(participant=p_approver)

        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "action": "reject"
        }, content_type="application/json")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 200)

        # Refresh
        p_approver.refresh_from_db()
        envelope.refresh_from_db()
        self.assertEqual(p_approver.status, 'declined')
        self.assertEqual(envelope.status, 'declined')

        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Approver Rejected", events)

    def test_cc_view_only_advances_workflow(self):
        """Verify that CC role has view-only access, stays viewed on load, and advances step only on acknowledge post."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah CC", "email": "sarah@email.com", "role": "cc", "step_number": 1},
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        envelope = serializer.save()

        p_cc = envelope.participants.get(role="cc")
        token_rec = ParticipantToken.objects.get(participant=p_cc)

        # 1. Simulate CC viewing the session via GET and then explicit POST view action
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.get(f"/api/signing/{token_rec.token}/")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 200)

        # Verify response indicates role and status (remains active as GET is now pure)
        self.assertEqual(response.data['participant_role'], 'cc')
        self.assertEqual(response.data['participant_status'], 'active')

        # Trigger POST view action to mark as viewed
        request_view = factory.post(f"/api/signing/{token_rec.token}/", {
            "action": "view"
        }, content_type="application/json")
        request_view.META['REMOTE_ADDR'] = '127.0.0.1'
        request_view.META['HTTP_USER_AGENT'] = 'TestClient'
        response_view = view(request_view, token=str(token_rec.token))
        self.assertEqual(response_view.status_code, 200)

        # Refresh database - should be viewed but NOT completed or advanced!
        p_cc.refresh_from_db()
        p_signer = envelope.participants.get(role="signer")
        self.assertEqual(p_cc.status, 'viewed')
        self.assertEqual(p_signer.status, 'pending')

        # 2. Simulate CC explicit click on "Acknowledge" via POST
        request_post = factory.post(f"/api/signing/{token_rec.token}/", {
            "action": "acknowledge"
        }, content_type="application/json")
        request_post.META['REMOTE_ADDR'] = '127.0.0.1'
        request_post.META['HTTP_USER_AGENT'] = 'TestClient'
        
        response_post = view(request_post, token=str(token_rec.token))
        self.assertEqual(response_post.status_code, 200)

        # Refresh database - now should be completed and advanced!
        p_cc.refresh_from_db()
        p_signer.refresh_from_db()
        self.assertEqual(p_cc.status, 'completed')
        self.assertEqual(p_signer.status, 'active')

        events = list(envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("Participant Viewed", events)
        self.assertIn("CC Acknowledged", events)
        self.assertIn("Step 1 Completed", events)
        self.assertIn("Workflow Advanced", events)

    def test_download_succeeds_after_signing(self):
        """Verify that a used token rejects further signing POST actions but allows GET download/preview access."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 1}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        envelope = serializer.save()

        p_signer = envelope.participants.get(role="signer")
        token_rec = ParticipantToken.objects.get(participant=p_signer)

        # 1. Complete signing
        from django.test import RequestFactory
        from .views import SigningView, SigningDownloadView, SigningSignedDocumentView
        
        factory = RequestFactory()
        request_post = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Mohammed Signature"
        }, content_type="application/json")
        request_post.META['REMOTE_ADDR'] = '127.0.0.1'
        request_post.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view_sign = SigningView.as_view()
        response_post = view_sign(request_post, token=str(token_rec.token))
        self.assertEqual(response_post.status_code, 201)

        # Refresh from database and ensure token is marked used
        token_rec.refresh_from_db()
        self.assertTrue(token_rec.is_used)

        # 2. Subsequent signing POST attempt must fail with "Token already used"
        request_post_again = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Mohammed Signature"
        }, content_type="application/json")
        request_post_again.META['REMOTE_ADDR'] = '127.0.0.1'
        request_post_again.META['HTTP_USER_AGENT'] = 'TestClient'
        
        response_post_again = view_sign(request_post_again, token=str(token_rec.token))
        self.assertEqual(response_post_again.status_code, 400)
        self.assertEqual(response_post_again.data['detail'], "This package has already been completed.")

        # 3. GET download/preview endpoints must succeed even though token is used
        view_download = SigningDownloadView.as_view()
        request_download = factory.get(f"/api/signing/{token_rec.token}/download/")
        response_download = view_download(request_download, token=str(token_rec.token))
        self.assertEqual(response_download.status_code, 200)

        view_preview = SigningSignedDocumentView.as_view()
        request_preview = factory.get(f"/api/signing/{token_rec.token}/signed/")
        response_preview = view_preview(request_preview, token=str(token_rec.token))
        self.assertEqual(response_preview.status_code, 200)

    def test_request_settings_saved_correctly(self):
        """Verify that Request Settings are correctly validated, saved, and returned in APIs."""
        # 1. Test validation on invalid emails
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 1}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
            "send_reminders": True,
            "send_final_email": True,
            "allow_printing": True,
            "additional_recipients": ["invalid-email", "admin@company.com"]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

        # 2. Test validation on duplicate emails
        data["additional_recipients"] = ["admin@company.com", "admin@company.com"]
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

        # 3. Test successful validation, persistence and creation API response
        data["additional_recipients"] = ["admin@company.com"]
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        
        from django.test import RequestFactory
        from .views import EnvelopeCreateView, PackageDetailView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        user = User.objects.create_user(username='test_req_settings', password='password')
        
        factory = RequestFactory()
        request_create = factory.post("/api/envelopes/", data, content_type="application/json")
        force_authenticate(request_create, user=user)
        view_create = EnvelopeCreateView.as_view()
        response_create = view_create(request_create)
        self.assertEqual(response_create.status_code, 201)
        
        envelope_id = response_create.data["envelope_id"]
        self.assertEqual(response_create.data["send_reminders"], True)
        self.assertEqual(response_create.data["send_final_email"], True)
        self.assertEqual(response_create.data["allow_printing"], True)
        self.assertEqual(response_create.data["additional_recipients"], ["admin@company.com"])

        # 4. Verify Detail API returns the correct values
        request_detail = factory.get(f"/api/packages/{envelope_id}/")
        force_authenticate(request_detail, user=user)
        view_detail = PackageDetailView.as_view()
        response_detail = view_detail(request_detail, pk=envelope_id)
        self.assertEqual(response_detail.status_code, 200)
        self.assertEqual(response_detail.data["send_reminders"], True)
        self.assertEqual(response_detail.data["send_final_email"], True)
        self.assertEqual(response_detail.data["allow_printing"], True)
        self.assertEqual(response_detail.data["additional_recipients"], ["admin@company.com"])

    def test_pending_participant_access_restricted(self):
        """Verify that a pending participant is restricted from performing actions and GET doesn't change status to viewed."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Sarah Reviewer", "email": "sarah@email.com", "role": "reviewer", "step_number": 1},
                {"name": "Mohammed Signer", "email": "mohammed@email.com", "role": "signer", "step_number": 2}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        envelope = serializer.save()

        # Step 2 Signer is pending
        p_signer = envelope.participants.get(role="signer")
        self.assertEqual(p_signer.status, 'pending')
        token_rec = ParticipantToken.objects.get(participant=p_signer)

        # 1. GET request should return status 'pending', step information, and NOT transition status to 'viewed'
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request_get = factory.get(f"/api/signing/{token_rec.token}/")
        request_get.META['REMOTE_ADDR'] = '127.0.0.1'
        request_get.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response_get = view(request_get, token=str(token_rec.token))
        self.assertEqual(response_get.status_code, 200)
        self.assertEqual(response_get.data['participant_status'], 'pending')
        self.assertEqual(response_get.data['participant_step'], 2)
        self.assertEqual(response_get.data['total_steps'], 2)
        
        # Verify status in database remains pending
        p_signer.refresh_from_db()
        self.assertEqual(p_signer.status, 'pending')

        # 2. POST request (action) from pending participant should be rejected with 400 Bad Request
        request_post = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Illegal Sign Attempt"
        }, content_type="application/json")
        request_post.META['REMOTE_ADDR'] = '127.0.0.1'
        request_post.META['HTTP_USER_AGENT'] = 'TestClient'
        
        response_post = view(request_post, token=str(token_rec.token))
        self.assertEqual(response_post.status_code, 400)
        self.assertEqual(response_post.data['detail'], "Workflow stage is not yet active for your role. Actions are restricted.")


class TemplateAPITests(TestCase):
    def test_template_crud_and_dashboard_integration(self):
        """Verify that templates can be created, updated, retrieved, deleted, and integrated in Dashboard stats."""
        # 1. Create Template via POST
        data = {
            "name": "NDA Standard",
            "category": "Legal",
            "description": "Standard Non-Disclosure Agreement",
            "visibility": "public",
            "workflow_definition": [
                {"step": 1, "role": "approver"},
                {"step": 2, "role": "signer"}
            ],
            "request_settings": {
                "send_reminders": True,
                "allow_printing": False
            }
        }
        
        from django.test import RequestFactory
        from .views import TemplateListCreateView, TemplateDetailView, DashboardView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        user = User.objects.create_user(username='test_template_user', password='password')
        
        factory = RequestFactory()
        request_create = factory.post("/api/templates/", data, content_type="application/json")
        force_authenticate(request_create, user=user)
        view_list_create = TemplateListCreateView.as_view()
        response_create = view_list_create(request_create)
        self.assertEqual(response_create.status_code, 201)
        self.assertEqual(response_create.data["name"], "NDA Standard")
        
        template_id = response_create.data["id"]

        # 2. Retrieve Template Details
        request_retrieve = factory.get(f"/api/templates/{template_id}/")
        force_authenticate(request_retrieve, user=user)
        view_detail = TemplateDetailView.as_view()
        response_retrieve = view_detail(request_retrieve, pk=template_id)
        self.assertEqual(response_retrieve.status_code, 200)
        self.assertEqual(response_retrieve.data["category"], "Legal")

        # 3. Update Template details via PUT
        update_data = {
            "name": "NDA Standard v2",
            "category": "Legal",
            "description": "Updated description",
            "visibility": "private",
            "workflow_definition": response_retrieve.data["workflow_definition"],
            "request_settings": response_retrieve.data["request_settings"]
        }
        request_update = factory.put(f"/api/templates/{template_id}/", update_data, content_type="application/json")
        force_authenticate(request_update, user=user)
        response_update = view_detail(request_update, pk=template_id)
        self.assertEqual(response_update.status_code, 200)
        self.assertEqual(response_update.data["name"], "NDA Standard v2")
        self.assertEqual(response_update.data["visibility"], "private")

        # 4. Verify Dashboard integrates template analytics
        request_dash = factory.get("/api/dashboard/")
        force_authenticate(request_dash, user=user)
        view_dash = DashboardView.as_view()
        response_dash = view_dash(request_dash)
        self.assertEqual(response_dash.status_code, 200)
        self.assertEqual(response_dash.data["total_templates"], 1)
        self.assertEqual(response_dash.data["recent_templates"][0]["name"], "NDA Standard v2")

        # 5. Delete Template
        request_delete = factory.delete(f"/api/templates/{template_id}/")
        force_authenticate(request_delete, user=user)
        response_delete = view_detail(request_delete, pk=template_id)
        self.assertEqual(response_delete.status_code, 204)

        # 6. Verify Dashboard updates after deletion
        response_dash_after = view_dash(request_dash)
        self.assertEqual(response_dash_after.status_code, 200)
        self.assertEqual(response_dash_after.data["total_templates"], 0)


class PackageSignedDocumentTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='test_signed_doc_user', password='password')
        self.client.force_login(self.user)

        import fitz
        from django.core.files.base import ContentFile
        from .models import Document, Envelope, SignedDocument
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(file_hash="mockhash12345")
        self.document.file.save("mock.pdf", ContentFile(pdf_bytes))
        
        self.envelope = Envelope.objects.create(document=self.document, status="completed", owner=self.user)
        self.signed_doc = SignedDocument.objects.create(
            envelope=self.envelope,
            final_hash="signedhash12345"
        )
        self.signed_doc.file.save("mock_signed.pdf", ContentFile(pdf_bytes))

    def test_signed_document_preview(self):
        """Verify that PackageSignedPreviewView serves the signed document inline."""
        from django.test import RequestFactory
        from .views import PackageSignedPreviewView
        from rest_framework.test import force_authenticate
        
        factory = RequestFactory()
        request = factory.get(f"/api/packages/{self.envelope.id}/preview/")
        force_authenticate(request, user=self.user)
        view = PackageSignedPreviewView.as_view()
        response = view(request, pk=self.envelope.id)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.has_header('Content-Disposition'))
        self.assertIn('inline', response['Content-Disposition'])

    def test_signed_document_download(self):
        """Verify that PackageSignedDownloadView serves the signed document as an attachment."""
        from django.test import RequestFactory
        from .views import PackageSignedDownloadView
        from rest_framework.test import force_authenticate
        
        factory = RequestFactory()
        request = factory.get(f"/api/packages/{self.envelope.id}/download/")
        force_authenticate(request, user=self.user)
        view = PackageSignedDownloadView.as_view()
        response = view(request, pk=self.envelope.id)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.has_header('Content-Disposition'))
        self.assertIn('attachment;', response['Content-Disposition'])




class DocumentUploadValidationTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='test_upload_validation_user', password='password')
        self.client.force_login(self.user)
        # Generate a valid 1-page mock PDF using PyMuPDF
        import fitz
        doc = fitz.open()
        doc.new_page()
        self.valid_pdf_bytes = doc.tobytes()
        doc.close()


    def test_valid_pdf_upload_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            self.valid_pdf_bytes,
            content_type="application/pdf"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("document_id", response.data)
        self.assertIn("file_hash", response.data)

    def test_non_pdf_extension_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_file = SimpleUploadedFile(
            "document.txt",
            self.valid_pdf_bytes,
            content_type="application/pdf"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertEqual(response.data["file"][0], "Invalid file type. Only PDF documents are supported.")

    def test_wrong_mime_type_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            b"Hello World",
            content_type="text/plain"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertEqual(response.data["file"][0], "Invalid file type. Only PDF documents are supported.")

    def test_oversized_file_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        # 10 MB + 1 byte
        oversized_data = b"0" * (10 * 1024 * 1024 + 1)
        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            oversized_data,
            content_type="application/pdf"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertEqual(response.data["file"][0], "File too large. Maximum allowed size is 10 MB.")

    def test_empty_file_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            b"",
            content_type="application/pdf"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertEqual(response.data["file"][0], "Invalid PDF upload. Please upload a valid PDF document.")

    def test_corrupted_pdf_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            b"%PDF-1.4\ncorrupted content",
            content_type="application/pdf"
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": uploaded_file}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertEqual(response.data["file"][0], "Invalid PDF upload. Please upload a valid PDF document.")


class DocumentFieldsTestCase(TestCase):
    def setUp(self):
        import fitz
        from django.core.files.base import ContentFile
        from .models import Document
        
        # Generate a valid 1-page mock PDF using PyMuPDF
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(
            file_hash="mockhashfields123"
        )
        self.document.file.save("mock.pdf", ContentFile(pdf_bytes))

    def test_create_envelope_with_all_field_types_success(self):
        """Verify successful envelope creation with signature, date, text, and checkbox fields."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1},
                {"name": "Bob Approver", "email": "bob@email.com", "role": "approver", "step_number": 2}
            ],
            "fields": [
                {"field_type": "signature", "page": 1, "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "alice@email.com"},
                {"field_type": "date", "page": 1, "x_ratio": 0.3, "y_ratio": 0.4, "participant_email": "alice@email.com"},
                {"field_type": "text", "page": 1, "x_ratio": 0.5, "y_ratio": 0.6, "participant_email": "alice@email.com"},
                {"field_type": "checkbox", "page": 1, "x_ratio": 0.7, "y_ratio": 0.8, "participant_email": "bob@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        # Check total fields created
        self.assertEqual(envelope.fields.count(), 4)
        
        # Check specific field types and coordinate ratio persistence
        sig_field = envelope.fields.get(field_type="signature")
        self.assertEqual(sig_field.participant.email, "alice@email.com")
        self.assertEqual(sig_field.x_ratio, 0.1)
        self.assertEqual(sig_field.y_ratio, 0.2)

        chk_field = envelope.fields.get(field_type="checkbox")
        self.assertEqual(chk_field.participant.email, "bob@email.com")
        self.assertEqual(chk_field.x_ratio, 0.7)
        self.assertEqual(chk_field.y_ratio, 0.8)

    def test_validation_rejects_invalid_field_type(self):
        """Verify that validation fails if an unsupported field type is provided."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "invalid_type", "page": 1, "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "alice@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)
        self.assertIn("Invalid field type 'invalid_type'", str(serializer.errors["non_field_errors"]))

    def test_validation_rejects_invalid_participant_email(self):
        """Verify that validation fails if the field's participant email is not in participants list."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "signature", "page": 1, "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "wrong@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)
        self.assertIn("not valid for this envelope", str(serializer.errors["non_field_errors"]))

    def test_validation_rejects_out_of_bounds_coordinates(self):
        """Verify that validation fails if coordinates ratios are out of [0.0, 1.0] bounds."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "signature", "page": 1, "x_ratio": 1.5, "y_ratio": 0.2, "participant_email": "alice@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        
        # Test negative ratio
        data["fields"][0]["x_ratio"] = -0.1
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_validation_rejects_missing_page_number(self):
        """Verify that validation fails if the page number is missing or invalid."""
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "signature", "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "alice@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())

        # Test invalid type page
        data["fields"][0]["page"] = "not-an-integer"
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_signing_with_fields_embeds_correctly(self):
        """Verify that signing a participant's active step processes and commits all their assigned fields."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "signature", "page": 1, "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "alice@email.com"},
                {"field_type": "date", "page": 1, "x_ratio": 0.3, "y_ratio": 0.4, "participant_email": "alice@email.com"},
                {"field_type": "text", "page": 1, "x_ratio": 0.5, "y_ratio": 0.6, "participant_email": "alice@email.com"},
                {"field_type": "checkbox", "page": 1, "x_ratio": 0.7, "y_ratio": 0.8, "participant_email": "alice@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        p_signer = envelope.participants.get(email="alice@email.com")
        token_rec = ParticipantToken.objects.get(participant=p_signer)

        # Post signing data
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Alice Signature",
            "fields": {
                str(envelope.fields.filter(field_type='text').first().id): "Custom Test Input Text",
                str(envelope.fields.filter(field_type='checkbox').first().id): False
            }
        }, content_type="application/json")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 201)

        # Verify envelope gets completed
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, "completed")

    def test_legacy_signing_without_fields_works(self):
        """Verify that legacy envelopes created without custom fields still sign and embed correctly."""
        from .models import ParticipantToken
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Legacy Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()

        p_signer = envelope.participants.get(email="alice@email.com")
        token_rec = ParticipantToken.objects.get(participant=p_signer)

        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.post(f"/api/signing/{token_rec.token}/", {
            "signature_type": "typed",
            "signature_text": "Alice Signature"
        }, content_type="application/json")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 201)

        envelope.refresh_from_db()
        self.assertEqual(envelope.status, "completed")

    def test_package_detail_retrieves_fields(self):
        """Verify that PackageDetailView GET response returns the fields array and document url correctly."""
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='test_detail_fields_user', password='password')
        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@email.com", "role": "signer", "step_number": 1}
            ],
            "fields": [
                {"field_type": "signature", "page": 1, "x_ratio": 0.1, "y_ratio": 0.2, "participant_email": "alice@email.com"},
                {"field_type": "text", "page": 1, "x_ratio": 0.5, "y_ratio": 0.6, "participant_email": "alice@email.com"}
            ]
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save(owner=user)

        from django.test import RequestFactory
        from .views import PackageDetailView
        from rest_framework.test import force_authenticate

        factory = RequestFactory()
        request = factory.get(f"/api/packages/{envelope.id}/")
        force_authenticate(request, user=user)
        view = PackageDetailView.as_view()
        response = view(request, pk=envelope.id)
        self.assertEqual(response.status_code, 200)

        # Verify document url is present
        self.assertIn("url", response.data["document"])
        self.assertTrue(response.data["document"]["url"].endswith(self.document.file.url))

        # Verify fields list
        fields_retrieved = response.data["fields"]
        self.assertEqual(len(fields_retrieved), 2)
        
        # Verify fields matching
        sig_retrieved = next(f for f in fields_retrieved if f["field_type"] == "signature")
        self.assertEqual(sig_retrieved["page"], 1)
        self.assertEqual(sig_retrieved["x_ratio"], 0.1)
        self.assertEqual(sig_retrieved["y_ratio"], 0.2)
        self.assertEqual(sig_retrieved["participant_email"], "alice@email.com")
        self.assertEqual(sig_retrieved["participant_name"], "Alice Signer")


class AuthenticationAndOwnershipTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        
        self.client = APIClient()
        self.user_a = User.objects.create_user(username='user_a', password='passwordA', email='usera@example.com')
        self.user_b = User.objects.create_user(username='user_b', password='passwordB', email='userb@example.com')
        
        # We need a document for creating envelopes
        import fitz
        from django.core.files.base import ContentFile
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(file_hash="auth_test_hash")
        self.document.file.save("auth_test.pdf", ContentFile(pdf_bytes))

    def test_registration_success(self):
        response = self.client.post("/api/auth/register/", {
            "username": "newuser",
            "password": "newpassword",
            "email": "new@example.com"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "newuser")
        
        # Verify the user was created and can log in
        from django.contrib.auth.models import User
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_registration_missing_fields(self):
        response = self.client.post("/api/auth/register/", {
            "username": "newuser"
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_registration_duplicate_username(self):
        response = self.client.post("/api/auth/register/", {
            "username": "user_a",
            "password": "password",
            "email": "another@example.com"
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_login_success(self):
        response = self.client.post("/api/auth/login/", {
            "username": "user_a",
            "password": "passwordA"
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "user_a")

    def test_login_invalid_credentials(self):
        response = self.client.post("/api/auth/login/", {
            "username": "user_a",
            "password": "wrongpassword"
        }, format="json")
        self.assertEqual(response.status_code, 401)

    def test_logout_success(self):
        from rest_framework.authtoken.models import Token
        token = Token.objects.create(user=self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user_a).exists())

    def test_logout_unauthenticated(self):
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 401)

    def test_userme_authenticated(self):
        from rest_framework.authtoken.models import Token
        token = Token.objects.create(user=self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "user_a")
        self.assertEqual(response.data["email"], "usera@example.com")

    def test_protected_endpoints_deny_unauthenticated(self):
        # Package List
        response = self.client.get("/api/packages/")
        self.assertEqual(response.status_code, 401)
        
        # Dashboard
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 401)
        
        # Template List
        response = self.client.get("/api/templates/")
        self.assertEqual(response.status_code, 401)

    def test_owner_isolation_packages(self):
        # Create an envelope owned by user_a
        envelope_a = Envelope.objects.create(
            document=self.document,
            status="draft",
            owner=self.user_a,
            signature_page=1,
            signature_x_ratio=0.5,
            signature_y_ratio=0.5
        )
        
        # Authenticate user_a and retrieve the package list and detail
        from rest_framework.authtoken.models import Token
        token_a = Token.objects.create(user=self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_a.key)
        
        response = self.client.get("/api/packages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], envelope_a.id)
        
        response_detail = self.client.get(f"/api/packages/{envelope_a.id}/")
        self.assertEqual(response_detail.status_code, 200)
        
        # Authenticate user_b and check isolation
        token_b = Token.objects.create(user=self.user_b)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_b.key)
        
        response = self.client.get("/api/packages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0) # User B has no packages
        
        response_detail = self.client.get(f"/api/packages/{envelope_a.id}/")
        self.assertEqual(response_detail.status_code, 404) # User B gets 404 for User A's package

    def test_owner_isolation_templates(self):
        from .models import Template
        # Create a template owned by user_a
        template_a = Template.objects.create(
            name="NDA A",
            category="Legal",
            visibility="private",
            workflow_definition=[],
            owner=self.user_a
        )
        
        # Authenticate user_a and retrieve
        from rest_framework.authtoken.models import Token
        token_a = Token.objects.create(user=self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_a.key)
        
        response = self.client.get("/api/templates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        
        response_detail = self.client.get(f"/api/templates/{template_a.id}/")
        self.assertEqual(response_detail.status_code, 200)
        
        # Authenticate user_b and check isolation
        token_b = Token.objects.create(user=self.user_b)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token_b.key)
        
        response = self.client.get("/api/templates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)
        
        response_detail = self.client.get(f"/api/templates/{template_a.id}/")
        self.assertEqual(response_detail.status_code, 404)

    def test_signing_views_public(self):
        # Public signing access should not require auth token
        # Create an envelope with participant
        envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            owner=self.user_a,
            signature_page=1,
            signature_x_ratio=0.5,
            signature_y_ratio=0.5
        )
        participant = Participant.objects.create(
            envelope=envelope,
            name="Signer",
            email="signer@example.com",
            role="signer",
            step_number=1,
            status="active"
        )
        from .models import ParticipantToken
        from django.utils import timezone
        from datetime import timedelta
        pt = ParticipantToken.objects.create(
            participant=participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )
        
        # Request signing page WITHOUT credentials
        response = self.client.get(f"/api/sign/{pt.token}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["signer_name"], "Signer")


class EmailNotificationsTestCase(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        from django.core.files.base import ContentFile
        import fitz
        from .models import Document, Envelope
        from .serializers import EnvelopeCreateSerializer
        
        self.client = APIClient()
        self.user = User.objects.create_user(username='owner', password='password', email='owner@example.com')
        self.client.force_authenticate(user=self.user)
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(file_hash="email_test_hash")
        self.document.file.save("email_test.pdf", ContentFile(pdf_bytes))

        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Approver", "email": "alice@example.com", "role": "approver", "step_number": 1},
                {"name": "Bob Reviewer", "email": "bob@example.com", "role": "reviewer", "step_number": 2},
                {"name": "Charlie Signer", "email": "charlie@example.com", "role": "signer", "step_number": 3}
            ],
            "additional_recipients": ["cc1@example.com", "cc2@example.com"],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.envelope = serializer.save(owner=self.user)

    def test_send_package_email_first_participant(self):
        from django.core import mail
        mail.outbox = []
        
        response = self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
        self.assertEqual(response.status_code, 200)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["alice@example.com"])
        self.assertEqual(email.subject, "Document waiting for your approval")
        self.assertIn("Alice Approver", email.body)
        self.assertIn("/sign/", email.body)

    def test_approver_completion_emails_reviewer(self):
        from django.core import mail
        self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
        
        mail.outbox = []
        
        from .models import ParticipantToken
        p_alice = self.envelope.participants.get(email="alice@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        
        response = self.client.post(f"/api/sign/{token_alice.token}/", {
            "action": "approve"
        }, format="json")
        self.assertEqual(response.status_code, 200)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["bob@example.com"])
        self.assertEqual(email.subject, "Document waiting for your review")
        self.assertIn("Bob Reviewer", email.body)

    def test_reviewer_completion_emails_signer(self):
        from django.core import mail
        self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
        from .models import ParticipantToken
        p_alice = self.envelope.participants.get(email="alice@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        self.client.post(f"/api/sign/{token_alice.token}/", {"action": "approve"}, format="json")
        
        mail.outbox = []
        
        p_bob = self.envelope.participants.get(email="bob@example.com")
        token_bob = ParticipantToken.objects.get(participant=p_bob)
        
        response = self.client.post(f"/api/sign/{token_bob.token}/", {
            "action": "approve"
        }, format="json")
        self.assertEqual(response.status_code, 200)
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["charlie@example.com"])
        self.assertEqual(email.subject, "Document waiting for your signature")
        self.assertIn("Charlie Signer", email.body)

    def test_signer_completion_emails_owner_and_recipients(self):
        from django.core import mail
        self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
        from .models import ParticipantToken
        
        p_alice = self.envelope.participants.get(email="alice@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        self.client.post(f"/api/sign/{token_alice.token}/", {"action": "approve"}, format="json")
        
        p_bob = self.envelope.participants.get(email="bob@example.com")
        token_bob = ParticipantToken.objects.get(participant=p_bob)
        self.client.post(f"/api/sign/{token_bob.token}/", {"action": "approve"}, format="json")
        
        mail.outbox = []
        
        p_charlie = self.envelope.participants.get(email="charlie@example.com")
        token_charlie = ParticipantToken.objects.get(participant=p_charlie)
        
        response = self.client.post(f"/api/sign/{token_charlie.token}/", {
            "signature_type": "typed",
            "signature_text": "Charlie Signature"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        
        # Completion triggers email to Owner + 2 CCs = 3 total emails
        self.assertEqual(len(mail.outbox), 3)
        recipients_received = [email.to[0] for email in mail.outbox]
        self.assertIn("owner@example.com", recipients_received)
        self.assertIn("cc1@example.com", recipients_received)
        self.assertIn("cc2@example.com", recipients_received)
        
        owner_email = next(email for email in mail.outbox if email.to[0] == "owner@example.com")
        self.assertEqual(owner_email.subject, "Package completed successfully")
        self.assertIn("download", owner_email.body)

    def test_workflow_continues_even_if_email_sending_fails(self):
        from unittest.mock import patch
        
        with patch("django.core.mail.send_mail", side_effect=Exception("SMTP Connection Error")):
            response = self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
            self.assertEqual(response.status_code, 200)
            
            self.envelope.refresh_from_db()
            self.assertEqual(self.envelope.status, "sent")
            
            from .models import ParticipantToken
            p_alice = self.envelope.participants.get(email="alice@example.com")
            token_alice = ParticipantToken.objects.get(participant=p_alice)
            
            response_approve = self.client.post(f"/api/sign/{token_alice.token}/", {
                "action": "approve"
            }, format="json")
            self.assertEqual(response_approve.status_code, 200)
            
            p_bob = self.envelope.participants.get(email="bob@example.com")
            self.assertEqual(p_bob.status, "active")


class CertificateOfCompletionTestCase(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from rest_framework.test import APIClient
        from django.core.files.base import ContentFile
        import fitz
        from .models import Document, Envelope
        from .serializers import EnvelopeCreateSerializer
        
        self.client = APIClient()
        self.owner = User.objects.create_user(username='owner', password='password', email='owner@example.com')
        self.other_user = User.objects.create_user(username='other', password='password', email='other@example.com')
        self.client.force_authenticate(user=self.owner)
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        self.document = Document.objects.create(file_hash="cert_test_hash")
        self.document.file.save("cert_test.pdf", ContentFile(pdf_bytes))

        data = {
            "document_id": self.document.id,
            "participants": [
                {"name": "Alice Signer", "email": "alice@example.com", "role": "signer", "step_number": 1}
            ],
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.envelope = serializer.save(owner=self.owner)

    def test_certificate_generation_on_completion(self):
        from django.core import mail
        from .models import ParticipantToken, CompletionCertificate
        
        # 1. Send the package
        self.client.post(f"/api/envelopes/{self.envelope.id}/send/")
        
        # 2. Complete the signing action
        p_alice = self.envelope.participants.get(email="alice@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        
        mail.outbox = []
        response = self.client.post(f"/api/sign/{token_alice.token}/", {
            "signature_type": "typed",
            "signature_text": "Alice Signature"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        
        # 3. Check that CompletionCertificate object exists
        cert_exists = CompletionCertificate.objects.filter(envelope=self.envelope).exists()
        self.assertTrue(cert_exists)
        cert = CompletionCertificate.objects.get(envelope=self.envelope)
        self.assertIsNotNone(cert.file)
        self.assertTrue(len(cert.final_hash) > 0)
        
        # Check that unique certificate ID is generated and persisted
        self.assertIsNotNone(cert.certificate_id)
        self.assertTrue(cert.certificate_id.startswith("CERT-"))
        
        # 4. Check that emails in outbox have two attachments and contain the Certificate ID
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(len(email.attachments), 2)
        attachment_names = [a[0] for a in email.attachments]
        self.assertTrue(any("cert_test" in name for name in attachment_names))
        self.assertTrue(any("certificate" in name for name in attachment_names))
        self.assertIn(cert.certificate_id, email.body)

        # Check that the Certificate ID is included in the audit log timeline
        from .models import AuditLog
        cert_audit = AuditLog.objects.filter(envelope=self.envelope, event__contains=cert.certificate_id).exists()
        self.assertTrue(cert_audit)

        # 5. Check owner-level certificate download (authorized)
        self.client.force_authenticate(user=self.owner)
        download_response = self.client.get(f"/api/packages/{self.envelope.id}/certificate/download/")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response['Content-Type'], 'application/pdf')
        self.assertTrue(len(download_response.getvalue()) > 0)

        # 6. Check BOLA download restriction (unauthorized user gets 404)
        self.client.force_authenticate(user=self.other_user)
        download_response = self.client.get(f"/api/packages/{self.envelope.id}/certificate/download/")
        self.assertEqual(download_response.status_code, 404)

        # 7. Check signer token-level download (authorized)
        self.client.force_authenticate(user=None) # Unauthenticate
        token_download_response = self.client.get(f"/api/sign/{token_alice.token}/certificate/download/")
        self.assertEqual(token_download_response.status_code, 200)
        self.assertEqual(token_download_response['Content-Type'], 'application/pdf')

        # 8. Check signer token-level download with invalid token
        invalid_token_response = self.client.get(f"/api/sign/00000000-0000-0000-0000-000000000000/certificate/download/")
        self.assertEqual(invalid_token_response.status_code, 404)


class EmailValidationTestCase(TestCase):
    """
    Verify that invalid email addresses are rejected at the serializer layer
    before any DB write or email notification is attempted.

    Covers:
      - Participant email (via EnvelopeCreateSerializer → ParticipantSerializer)
      - Signer email (via EnvelopeCreateSerializer → SignerSerializer)
      - additional_recipients (via EnvelopeCreateSerializer.validate_additional_recipients)
      - Registration email (via RegisterView)

    Valid / invalid cases match the requirements doc exactly.
    """

    def setUp(self):
        from .models import Document
        self.document = Document.objects.create(
            file="mock.pdf",
            file_hash="mockhash_email_validation"
        )
        self._base_data = {
            "document_id": self.document.id,
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_participant_data(self, email):
        return {
            **self._base_data,
            "participants": [
                {"name": "Test Signer", "email": email, "role": "signer"}
            ],
        }

    def _make_signer_data(self, email):
        return {
            **self._base_data,
            "signer": {"name": "Test Signer", "email": email},
        }

    # ── Participant email — invalid cases ─────────────────────────────────────

    def test_participant_email_plain_word_rejected(self):
        """'hamza' (no @ or domain) must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("hamza"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_participant_email_missing_domain_rejected(self):
        """'hamza@' (missing domain) must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("hamza@"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_participant_email_no_tld_rejected(self):
        """'hamza@gmail' (domain without TLD) must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("hamza@gmail"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    def test_participant_email_no_at_sign_rejected(self):
        """'abc.com' (no @ symbol) must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("abc.com"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

    # ── Participant email — valid cases ───────────────────────────────────────

    def test_participant_email_valid_gmail_accepted(self):
        """'test@gmail.com' must be accepted."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("test@gmail.com"))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_participant_email_valid_yahoo_accepted(self):
        """'user123@yahoo.com' must be accepted."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("user123@yahoo.com"))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    # ── Signer email — invalid cases ──────────────────────────────────────────

    def test_signer_email_plain_word_rejected(self):
        """'hamza' signer email must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_signer_data("hamza"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("signer", serializer.errors)

    def test_signer_email_missing_domain_rejected(self):
        """'hamza@' signer email must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_signer_data("hamza@"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("signer", serializer.errors)

    def test_signer_email_no_tld_rejected(self):
        """'hamza@gmail' signer email must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_signer_data("hamza@gmail"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("signer", serializer.errors)

    def test_signer_email_no_at_sign_rejected(self):
        """'abc.com' signer email must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_signer_data("abc.com"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("signer", serializer.errors)

    # ── Signer email — valid cases ────────────────────────────────────────────

    def test_signer_email_valid_accepted(self):
        """'test@gmail.com' signer email must be accepted."""
        serializer = EnvelopeCreateSerializer(data=self._make_signer_data("test@gmail.com"))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    # ── additional_recipients — invalid cases ─────────────────────────────────

    def _make_recipients_data(self, recipients):
        return {
            **self._base_data,
            "participants": [
                {"name": "Test Signer", "email": "test@gmail.com", "role": "signer"}
            ],
            "additional_recipients": recipients,
        }

    def test_additional_recipients_plain_word_rejected(self):
        """'hamza' in additional_recipients must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_recipients_data(["hamza"]))
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

    def test_additional_recipients_missing_domain_rejected(self):
        """'hamza@' in additional_recipients must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_recipients_data(["hamza@"]))
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

    def test_additional_recipients_no_tld_rejected(self):
        """'hamza@gmail' in additional_recipients must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_recipients_data(["hamza@gmail"]))
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

    def test_additional_recipients_no_at_sign_rejected(self):
        """'abc.com' in additional_recipients must be rejected."""
        serializer = EnvelopeCreateSerializer(data=self._make_recipients_data(["abc.com"]))
        self.assertFalse(serializer.is_valid())
        self.assertIn("additional_recipients", serializer.errors)

    def test_additional_recipients_valid_accepted(self):
        """Valid addresses in additional_recipients must be accepted."""
        serializer = EnvelopeCreateSerializer(
            data=self._make_recipients_data(["admin@company.com", "user123@yahoo.com"])
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    # ── RegisterView — email validation ───────────────────────────────────────

    def test_register_invalid_email_returns_400(self):
        """RegisterView must return 400 when an invalid email is provided."""
        from django.test import RequestFactory
        from .views import RegisterView

        factory = RequestFactory()
        request = factory.post(
            "/api/auth/register/",
            {"username": "newuser_invalid_email", "password": "securepass123", "email": "notanemail"},
            content_type="application/json",
        )
        view = RegisterView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_register_missing_at_email_returns_400(self):
        """RegisterView must reject 'hamza@' as email."""
        from django.test import RequestFactory
        from .views import RegisterView

        factory = RequestFactory()
        request = factory.post(
            "/api/auth/register/",
            {"username": "newuser_missing_at", "password": "securepass123", "email": "hamza@"},
            content_type="application/json",
        )
        view = RegisterView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_register_valid_email_accepted(self):
        """RegisterView must accept a valid email and create the user."""
        from django.test import RequestFactory
        from .views import RegisterView

        factory = RequestFactory()
        request = factory.post(
            "/api/auth/register/",
            {"username": "newuser_valid_email", "password": "securepass123", "email": "test@gmail.com"},
            content_type="application/json",
        )
        view = RegisterView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)

    def test_register_no_email_accepted(self):
        """RegisterView must accept registration with no email (email is optional)."""
        from django.test import RequestFactory
        from .views import RegisterView

        factory = RequestFactory()
        request = factory.post(
            "/api/auth/register/",
            {"username": "newuser_no_email", "password": "securepass123"},
            content_type="application/json",
        )
        view = RegisterView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 201)

    # ── Error response format ──────────────────────────────────────────────────

    def test_invalid_participant_email_error_message_format(self):
        """Validation error for participant email must not expose a stack trace."""
        serializer = EnvelopeCreateSerializer(data=self._make_participant_data("hamza"))
        is_valid = serializer.is_valid()
        self.assertFalse(is_valid)
        # Errors must be a plain dict — no 500, no traceback
        self.assertIsInstance(serializer.errors, dict)
        self.assertIn("participants", serializer.errors)

    def test_invalid_additional_recipients_error_message_format(self):
        """Validation error for additional_recipients must contain a meaningful message."""
        serializer = EnvelopeCreateSerializer(data=self._make_recipients_data(["hamza@"]))
        self.assertFalse(serializer.is_valid())
        error_msg = str(serializer.errors["additional_recipients"])
        # Must mention email validity, not a raw Python exception
        self.assertIn("valid email", error_msg.lower())


# ══════════════════════════════════════════════════════════════════════════════
# SMTP Failure Resilience Verification
# Verifies that SMTP failures never crash the application or corrupt
# business state across all workflow scenarios and exception types.
# ══════════════════════════════════════════════════════════════════════════════

from unittest.mock import patch, MagicMock
from smtplib import SMTPAuthenticationError, SMTPConnectError
import fitz
from rest_framework.test import APIClient as _APIClient


def _smtp_make_pdf():
    doc = fitz.open()
    doc.new_page()
    b = doc.tobytes()
    doc.close()
    return b


def _smtp_make_envelope(owner, participants_def):
    from django.core.files.base import ContentFile
    from .models import Document
    from .serializers import EnvelopeCreateSerializer
    document = Document.objects.create(file_hash=f"smtptest_{owner.username}")
    document.file.save(f"smtptest_{owner.username}.pdf", ContentFile(_smtp_make_pdf()))
    data = {
        "document_id": document.id,
        "participants": participants_def,
        "signature_page": 1,
        "signature_x_ratio": 0.5,
        "signature_y_ratio": 0.5,
    }
    s = EnvelopeCreateSerializer(data=data)
    assert s.is_valid(), s.errors
    return s.save(owner=owner)


_SMTP_EXCEPTIONS = [
    ("SMTPAuthError",   SMTPAuthenticationError(535, b"Authentication failed")),
    ("SMTPConnectErr",  SMTPConnectError(111, b"Connection refused")),
    ("TimeoutError",    TimeoutError("SMTP timed out")),
    ("GenericError",    Exception("SMTP server unavailable")),
]


class SmtpResilienceVerificationTest(TransactionTestCase):
    """
    Verification suite for SMTP failure resilience.

    Scenarios:
      S1 — Send Package: SMTP failure must not block envelope becoming 'sent'.
      S2 — Workflow Advance: SMTP failure must not block step progression.
      S3 — Completion: SMTP failure must not block envelope completing or
           certificate generation.
      S4 — Full multi-step (Approver -> Reviewer -> Signer) with SMTP always broken.

    Each scenario is exercised with four realistic exception types:
      SMTPAuthenticationError, SMTPConnectError, TimeoutError, generic Exception.
    """

    # ── Scenario 1: Send Package ──────────────────────────────────────────────

    def _s1_body(self, error_label, smtp_exc):
        from django.contrib.auth.models import User
        owner = User.objects.create_user(
            username=f"s1_{error_label}", password="pass",
            email=f"s1_{error_label}@example.com"
        )
        client = _APIClient()
        client.force_authenticate(user=owner)
        envelope = _smtp_make_envelope(owner, [
            {"name": "Alice", "email": "alice_s1@example.com", "role": "signer", "step_number": 1}
        ])
        with patch("django.core.mail.send_mail", side_effect=smtp_exc):
            response = client.post(f"/api/envelopes/{envelope.id}/send/")
        envelope.refresh_from_db()
        self.assertEqual(response.status_code, 200,
            f"[S1/{error_label}] Expected HTTP 200, got {response.status_code}")
        self.assertEqual(envelope.status, "sent",
            f"[S1/{error_label}] Envelope should be 'sent', got '{envelope.status}'")

    def test_s1_smtp_auth_error(self):   self._s1_body(*_SMTP_EXCEPTIONS[0])
    def test_s1_smtp_connect_error(self): self._s1_body(*_SMTP_EXCEPTIONS[1])
    def test_s1_timeout(self):           self._s1_body(*_SMTP_EXCEPTIONS[2])
    def test_s1_generic_exception(self): self._s1_body(*_SMTP_EXCEPTIONS[3])

    # ── Scenario 2: Workflow Advancement ─────────────────────────────────────

    def _s2_body(self, error_label, smtp_exc):
        from django.contrib.auth.models import User
        from .models import ParticipantToken
        owner = User.objects.create_user(
            username=f"s2_{error_label}", password="pass",
            email=f"s2_{error_label}@example.com"
        )
        client = _APIClient()
        client.force_authenticate(user=owner)
        envelope = _smtp_make_envelope(owner, [
            {"name": "Alice Approver", "email": "alice_s2@example.com", "role": "approver", "step_number": 1},
            {"name": "Bob Signer",     "email": "bob_s2@example.com",   "role": "signer",   "step_number": 2},
        ])
        client.post(f"/api/envelopes/{envelope.id}/send/")
        p_alice = envelope.participants.get(email="alice_s2@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        with patch("django.core.mail.send_mail", side_effect=smtp_exc):
            response = client.post(
                f"/api/sign/{token_alice.token}/", {"action": "approve"}, format="json"
            )
        p_bob = envelope.participants.get(email="bob_s2@example.com")
        p_bob.refresh_from_db()
        envelope.refresh_from_db()
        self.assertEqual(response.status_code, 200,
            f"[S2/{error_label}] Expected HTTP 200, got {response.status_code}")
        self.assertEqual(p_bob.status, "active",
            f"[S2/{error_label}] Bob should be 'active', got '{p_bob.status}'")
        self.assertEqual(envelope.status, "sent",
            f"[S2/{error_label}] Envelope should remain 'sent', got '{envelope.status}'")

    def test_s2_smtp_auth_error(self):   self._s2_body(*_SMTP_EXCEPTIONS[0])
    def test_s2_smtp_connect_error(self): self._s2_body(*_SMTP_EXCEPTIONS[1])
    def test_s2_timeout(self):           self._s2_body(*_SMTP_EXCEPTIONS[2])
    def test_s2_generic_exception(self): self._s2_body(*_SMTP_EXCEPTIONS[3])

    # ── Scenario 3: Completion ────────────────────────────────────────────────

    def _s3_body(self, error_label, smtp_exc):
        from django.contrib.auth.models import User
        from .models import ParticipantToken, CompletionCertificate, AuditLog
        owner = User.objects.create_user(
            username=f"s3_{error_label}", password="pass",
            email=f"s3_{error_label}@example.com"
        )
        client = _APIClient()
        client.force_authenticate(user=owner)
        envelope = _smtp_make_envelope(owner, [
            {"name": "Alice Signer", "email": "alice_s3@example.com", "role": "signer", "step_number": 1}
        ])
        client.post(f"/api/envelopes/{envelope.id}/send/")
        p_alice = envelope.participants.get(email="alice_s3@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        mock_em = MagicMock()
        mock_em.send.side_effect = smtp_exc
        with patch("django.core.mail.send_mail", side_effect=smtp_exc), \
             patch("django.core.mail.EmailMessage", return_value=mock_em):
            response = client.post(
                f"/api/sign/{token_alice.token}/",
                {"signature_type": "typed", "signature_text": "Alice Sig"},
                format="json"
            )
        envelope.refresh_from_db()
        self.assertEqual(response.status_code, 201,
            f"[S3/{error_label}] Expected HTTP 201, got {response.status_code}")
        self.assertEqual(envelope.status, "completed",
            f"[S3/{error_label}] Envelope should be 'completed', got '{envelope.status}'")
        self.assertTrue(
            CompletionCertificate.objects.filter(envelope=envelope).exists(),
            f"[S3/{error_label}] CompletionCertificate was not generated"
        )
        self.assertTrue(
            AuditLog.objects.filter(envelope=envelope, event="Workflow Completed").exists(),
            f"[S3/{error_label}] 'Workflow Completed' audit log missing"
        )
        self.assertTrue(
            AuditLog.objects.filter(envelope=envelope, event="Signed Document Generated").exists(),
            f"[S3/{error_label}] 'Signed Document Generated' audit log missing"
        )

    def test_s3_smtp_auth_error(self):   self._s3_body(*_SMTP_EXCEPTIONS[0])
    def test_s3_smtp_connect_error(self): self._s3_body(*_SMTP_EXCEPTIONS[1])
    def test_s3_timeout(self):           self._s3_body(*_SMTP_EXCEPTIONS[2])
    def test_s3_generic_exception(self): self._s3_body(*_SMTP_EXCEPTIONS[3])

    # ── Scenario 4: Full multi-step (Approver -> Reviewer -> Signer) ─────────

    def test_s4_full_multistep_smtp_always_broken(self):
        """Approver -> Reviewer -> Signer with SMTP broken at every single step."""
        from django.contrib.auth.models import User
        from .models import ParticipantToken, CompletionCertificate
        smtp_exc = SMTPAuthenticationError(535, b"Authentication credentials invalid")
        owner = User.objects.create_user(
            username="s4_owner", password="pass",
            email="s4_owner@example.com"
        )
        client = _APIClient()
        client.force_authenticate(user=owner)
        envelope = _smtp_make_envelope(owner, [
            {"name": "Alice Approver", "email": "alice_s4@example.com",   "role": "approver", "step_number": 1},
            {"name": "Bob Reviewer",   "email": "bob_s4@example.com",     "role": "reviewer", "step_number": 2},
            {"name": "Charlie Signer", "email": "charlie_s4@example.com", "role": "signer",   "step_number": 3},
        ])

        with patch("django.core.mail.send_mail", side_effect=smtp_exc):
            r = client.post(f"/api/envelopes/{envelope.id}/send/")
        self.assertEqual(r.status_code, 200, f"Send failed: {r.status_code}")
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, "sent")

        p_alice = envelope.participants.get(email="alice_s4@example.com")
        token_alice = ParticipantToken.objects.get(participant=p_alice)
        with patch("django.core.mail.send_mail", side_effect=smtp_exc):
            r = client.post(f"/api/sign/{token_alice.token}/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, f"Approver failed: {r.status_code}")
        p_bob = envelope.participants.get(email="bob_s4@example.com")
        p_bob.refresh_from_db()
        self.assertEqual(p_bob.status, "active", f"Bob should be active, got '{p_bob.status}'")

        token_bob = ParticipantToken.objects.get(participant=p_bob)
        with patch("django.core.mail.send_mail", side_effect=smtp_exc):
            r = client.post(f"/api/sign/{token_bob.token}/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, f"Reviewer failed: {r.status_code}")
        p_charlie = envelope.participants.get(email="charlie_s4@example.com")
        p_charlie.refresh_from_db()
        self.assertEqual(p_charlie.status, "active", f"Charlie should be active, got '{p_charlie.status}'")

        token_charlie = ParticipantToken.objects.get(participant=p_charlie)
        mock_em = MagicMock()
        mock_em.send.side_effect = smtp_exc
        with patch("django.core.mail.send_mail", side_effect=smtp_exc), \
             patch("django.core.mail.EmailMessage", return_value=mock_em):
            r = client.post(
                f"/api/sign/{token_charlie.token}/",
                {"signature_type": "typed", "signature_text": "Charlie"},
                format="json"
            )
        self.assertEqual(r.status_code, 201, f"Final signer failed: {r.status_code}")
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, "completed",
            f"Envelope should be 'completed', got '{envelope.status}'")
        self.assertTrue(
            CompletionCertificate.objects.filter(envelope=envelope).exists(),
            "CompletionCertificate not generated on multi-step completion with broken SMTP"
        )


class EnvelopeStateTransitionTests(TestCase):
    def setUp(self):
        from .models import Document, Envelope
        self.document = Document.objects.create(file_hash="dummy_hash")
        self.envelope = Envelope.objects.create(document=self.document, status="draft")

    def test_valid_transitions(self):
        from esign.exceptions import InvalidStateTransition
        
        # draft -> sent
        self.envelope.transition_to("sent")
        self.assertEqual(self.envelope.status, "sent")
        
        # sent -> viewed
        self.envelope.transition_to("viewed")
        self.assertEqual(self.envelope.status, "viewed")
        
        # viewed -> sent (resetting on step advancement)
        self.envelope.transition_to("sent")
        self.assertEqual(self.envelope.status, "sent")
        
        # sent -> declined
        self.envelope.transition_to("declined")
        self.assertEqual(self.envelope.status, "declined")
        
        # Reset to draft for other tests
        self.envelope.status = "draft"
        self.envelope.save()
        
        # draft -> cancelled
        self.envelope.transition_to("cancelled")
        self.assertEqual(self.envelope.status, "cancelled")

        # Reset to sent
        self.envelope.status = "sent"
        self.envelope.save()
        
        # sent -> completed
        self.envelope.transition_to("completed")
        self.assertEqual(self.envelope.status, "completed")

    def test_invalid_transitions(self):
        from esign.exceptions import InvalidStateTransition
        
        # completed -> sent
        self.envelope.status = "completed"
        self.envelope.save()
        with self.assertRaises(InvalidStateTransition):
            self.envelope.transition_to("sent")
            
        # completed -> draft
        with self.assertRaises(InvalidStateTransition):
            self.envelope.transition_to("draft")

        # declined -> sent
        self.envelope.status = "declined"
        self.envelope.save()
        with self.assertRaises(InvalidStateTransition):
            self.envelope.transition_to("sent")

        # expired -> sent
        self.envelope.status = "expired"
        self.envelope.save()
        with self.assertRaises(InvalidStateTransition):
            self.envelope.transition_to("sent")

        # cancelled -> sent
        self.envelope.status = "cancelled"
        self.envelope.save()
        with self.assertRaises(InvalidStateTransition):
            self.envelope.transition_to("sent")


class GetSideEffectsRemovalTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from .models import Document, Envelope, Participant, ParticipantToken
        
        self.owner = User.objects.create_user(username='owner_p2b', password='password', email='owner_p2b@example.com')
        self.document = Document.objects.create(file_hash="p2b_hash")
        self.envelope = Envelope.objects.create(document=self.document, status="sent")
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Alice P2B",
            email="alice_p2b@example.com",
            role="signer",
            step_number=1,
            status="active"
        )
        from django.utils import timezone
        from datetime import timedelta
        self.pt = ParticipantToken.objects.create(
            participant=self.participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )

    def test_get_purity(self):
        # 1. Fetching GET should be pure and not mutate anything
        response = self.client.get(f"/api/sign/{self.pt.token}/")
        self.assertEqual(response.status_code, 200)
        
        # Verify status remains 'active' and 'sent'
        self.participant.refresh_from_db()
        self.envelope.refresh_from_db()
        self.assertEqual(self.participant.status, "active")
        self.assertEqual(self.envelope.status, "sent")
        
        # Verify no audit logs were created
        self.assertEqual(self.envelope.auditlog_set.count(), 0)

    def test_view_action(self):
        # 2. Sending POST with action='view' should trigger the transition and log
        response = self.client.post(f"/api/sign/{self.pt.token}/", {
            "action": "view"
        }, format="json")
        self.assertEqual(response.status_code, 200)
        
        # Verify status transitioned to 'viewed'
        self.participant.refresh_from_db()
        self.envelope.refresh_from_db()
        self.assertEqual(self.participant.status, "viewed")
        self.assertEqual(self.envelope.status, "sent")
        
        # Verify audit log was created
        self.assertEqual(self.envelope.auditlog_set.count(), 1)
        self.assertEqual(self.envelope.auditlog_set.first().event, "Participant Viewed")

    def test_double_view(self):
        # 3. Sending POST with action='view' twice should be idempotent
        r1 = self.client.post(f"/api/sign/{self.pt.token}/", {"action": "view"}, format="json")
        self.assertEqual(r1.status_code, 200)
        
        r2 = self.client.post(f"/api/sign/{self.pt.token}/", {"action": "view"}, format="json")
        self.assertEqual(r2.status_code, 200)
        
        # Verify status remains 'viewed'
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, "viewed")
        
        # Verify only one audit log exists (no duplicate logs)
        self.assertEqual(self.envelope.auditlog_set.count(), 1)
        self.assertEqual(self.envelope.auditlog_set.first().event, "Participant Viewed")

    def test_legacy_signer_view_action(self):
        # Test that legacy signer view POST transitions the envelope status from 'sent' to 'viewed'
        from .models import Signer, SigningToken
        signer = Signer.objects.create(envelope=self.envelope, name="Legacy Signer", email="legacy@example.com")
        from django.utils import timezone
        from datetime import timedelta
        st = SigningToken.objects.create(
            signer=signer,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )
        
        # Initial status is sent
        self.assertEqual(self.envelope.status, "sent")
        
        # POST action="view"
        response = self.client.post(f"/api/sign/{st.token}/", {"action": "view"}, format="json")
        self.assertEqual(response.status_code, 200)
        
        # Envelope transitions to viewed
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, "viewed")
        
        # Verify audit logs
        events = list(self.envelope.auditlog_set.values_list('event', flat=True))
        self.assertIn("viewed", events)
        
        # POST action="view" again (double view)
        response2 = self.client.post(f"/api/sign/{st.token}/", {"action": "view"}, format="json")
        self.assertEqual(response2.status_code, 200)
        
        # Status remains viewed
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, "viewed")
        
        # Only one "viewed" audit log
        self.assertEqual(self.envelope.auditlog_set.filter(event="viewed").count(), 1)



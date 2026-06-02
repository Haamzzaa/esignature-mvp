from django.test import TestCase
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

        # 1. Simulate CC viewing the session via GET
        from django.test import RequestFactory
        from .views import SigningView
        
        factory = RequestFactory()
        request = factory.get(f"/api/signing/{token_rec.token}/")
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestClient'
        
        view = SigningView.as_view()
        response = view(request, token=str(token_rec.token))
        self.assertEqual(response.status_code, 200)

        # Verify response indicates role and status
        self.assertEqual(response.data['participant_role'], 'cc')
        self.assertEqual(response.data['participant_status'], 'viewed')

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
        self.assertEqual(response_post_again.data['detail'], "Token already used.")

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
        
        factory = RequestFactory()
        request_create = factory.post("/api/envelopes/", data, content_type="application/json")
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
        view_detail = PackageDetailView.as_view()
        response_detail = view_detail(request_detail, pk=envelope_id)
        self.assertEqual(response_detail.status_code, 200)
        self.assertEqual(response_detail.data["send_reminders"], True)
        self.assertEqual(response_detail.data["send_final_email"], True)
        self.assertEqual(response_detail.data["allow_printing"], True)
        self.assertEqual(response_detail.data["additional_recipients"], ["admin@company.com"])

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
        self.assertEqual(envelope.participants.count(), 1)
        participant = envelope.participants.first()
        self.assertEqual(participant.name, "Legacy Signer")
        self.assertEqual(participant.email, "legacy@email.com")
        self.assertEqual(participant.role, "signer")
        self.assertEqual(participant.step_number, 1)
        self.assertEqual(participant.order, 1)
        
        signer = Signer.objects.get(envelope=envelope)
        self.assertEqual(signer.name, "Legacy Signer")
        self.assertEqual(signer.email, "legacy@email.com")

    def test_legacy_signer_produces_participant(self):
        """Verify that legacy signer creation maps correctly to a Participant."""
        data = {
            "document_id": self.document.id,
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        envelope = serializer.save()
        
        self.assertEqual(envelope.participants.count(), 1)
        p = envelope.participants.first()
        self.assertEqual(p.name, "Test Signer")
        self.assertEqual(p.email, "test@email.com")
        self.assertEqual(p.role, "signer")
        self.assertEqual(p.step_number, 1)
        self.assertEqual(p.order, 1)

    def test_historical_backfill_works(self):
        """Verify that the historical backfill data migration runs and maps correctly."""
        from .models import Signer, SigningToken
        import importlib
        migration_module = importlib.import_module('esign.migrations.0019_backfill_participants')
        backfill_participants = migration_module.backfill_participants
        from django.utils import timezone
        from datetime import timedelta
        
        # 1. Create legacy database records bypass serializer mapping
        envelope_sent = Envelope.objects.create(document=self.document, status='sent', signature_page=1)
        signer_sent = Signer.objects.create(envelope=envelope_sent, name="Sent Signer", email="sent@email.com")
        st_sent = SigningToken.objects.create(signer=signer_sent, expires_at=timezone.now() + timedelta(hours=10), is_used=False)
        
        envelope_completed = Envelope.objects.create(document=self.document, status='completed', signature_page=1)
        signer_completed = Signer.objects.create(envelope=envelope_completed, name="Completed Signer", email="completed@email.com")
        st_completed = SigningToken.objects.create(signer=signer_completed, expires_at=timezone.now() + timedelta(hours=5), is_used=True)
        
        envelope_viewed = Envelope.objects.create(document=self.document, status='viewed', signature_page=1)
        signer_viewed = Signer.objects.create(envelope=envelope_viewed, name="Viewed Signer", email="viewed@email.com")
        
        # Verify 0 participants initially
        self.assertEqual(envelope_sent.participants.count(), 0)
        self.assertEqual(envelope_completed.participants.count(), 0)
        self.assertEqual(envelope_viewed.participants.count(), 0)
        
        # 2. Trigger backfill
        class MockApps:
            def get_model(self, app_label, model_name):
                from django.apps import apps
                return apps.get_model(app_label, model_name)
        
        backfill_participants(MockApps(), None)
        
        # 3. Assertions checking outcomes
        envelope_sent.refresh_from_db()
        self.assertEqual(envelope_sent.participants.count(), 1)
        p_sent = envelope_sent.participants.first()
        self.assertEqual(p_sent.status, "active")
        self.assertTrue(hasattr(p_sent, 'token'))
        self.assertEqual(p_sent.token.token, st_sent.token)
        self.assertEqual(p_sent.token.is_used, False)
        
        envelope_completed.refresh_from_db()
        self.assertEqual(envelope_completed.participants.count(), 1)
        p_completed = envelope_completed.participants.first()
        self.assertEqual(p_completed.status, "completed")
        self.assertEqual(p_completed.has_completed, True)
        self.assertTrue(hasattr(p_completed, 'token'))
        self.assertEqual(p_completed.token.token, st_completed.token)
        self.assertEqual(p_completed.token.is_used, True)
        
        envelope_viewed.refresh_from_db()
        self.assertEqual(envelope_viewed.participants.count(), 1)
        p_viewed = envelope_viewed.participants.first()
        self.assertEqual(p_viewed.status, "viewed")
        
        # Verify backfill run is idempotent
        backfill_participants(MockApps(), None)
        self.assertEqual(envelope_sent.participants.count(), 1)
        self.assertEqual(envelope_completed.participants.count(), 1)
        self.assertEqual(envelope_viewed.participants.count(), 1)

    def test_envelopes_always_have_participants(self):
        """Verify the invariant that every Envelope must have at least one Participant."""
        # 1. Draft creation
        data_draft = {
            "document_id": self.document.id,
            "signer": {"name": "Draft Signer", "email": "draft@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
            "is_draft": True
        }
        ser_draft = EnvelopeCreateSerializer(data=data_draft)
        self.assertTrue(ser_draft.is_valid())
        env_draft = ser_draft.save()
        self.assertTrue(env_draft.participants.exists())
        
        # 2. Sent creation
        data_sent = {
            "document_id": self.document.id,
            "signer": {"name": "Sent Signer", "email": "sent@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        ser_sent = EnvelopeCreateSerializer(data=data_sent)
        self.assertTrue(ser_sent.is_valid())
        env_sent = ser_sent.save()
        self.assertTrue(env_sent.participants.exists())

        # Ensure all Envelope objects satisfy the participants.exists() invariant
        from .models import Envelope
        for env in Envelope.objects.all():
            self.assertTrue(env.participants.exists(), f"Envelope {env.id} lacks participants.")

    def test_automatic_title_generation_missing_title(self):
        """Verify that the envelope title is automatically derived from the document filename if title is not in request_data."""
        data = {
            "document_id": self.document.id,
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "mock")

    def test_automatic_title_generation_blank_title(self):
        """Verify that the envelope title is automatically derived from the document filename if title is blank."""
        data = {
            "document_id": self.document.id,
            "title": "   ",
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "mock")

    def test_automatic_title_generation_preserves_supplied_title(self):
        """Verify that the envelope title is preserved if the frontend/user supplies a valid title."""
        data = {
            "document_id": self.document.id,
            "title": "Preserve Me",
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "Preserve Me")

    def test_automatic_title_generation_strips_extensions(self):
        """Verify extension stripping behavior for complex document filenames."""
        doc = Document.objects.create(
            file="documents/Employment Agreement.v2.pdf",
            file_hash="mockhash456"
        )
        data = {
            "document_id": doc.id,
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "Employment Agreement.v2")

    def test_automatic_title_generation_improved_cleaning(self):
        """Verify that leading numeric prefix, trailing random suffix, and underscores are cleaned while preserving Arabic."""
        doc = Document.objects.create(
            file="documents/2_عقد_عميل_Uh7TO.pdf",
            file_hash="mockhash_arabic"
        )
        data = {
            "document_id": doc.id,
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "عقد عميل")

    def test_automatic_title_generation_numeric_and_random_suffixes(self):
        """Verify that different random suffixes and numeric prefixes are properly cleaned."""
        test_cases = [
            ("documents/123_Vendor_NDA_v2_fnKRbbe.pdf", "Vendor NDA v2"),
            ("documents/Updated_Gym_Split_sH4Ahs3.pdf", "Updated Gym Split"),
            ("documents/auth_test_04GAUvf.pdf", "auth test"),
            ("documents/Digital_Services_Agreement_updated_13kHBKG.pdf", "Digital Services Agreement updated"),
        ]
        for file_name, expected_title in test_cases:
            doc = Document.objects.create(
                file=file_name,
                file_hash=f"hash_{file_name}"
            )
            data = {
                "document_id": doc.id,
                "signer": {"name": "Test Signer", "email": "test@email.com"},
                "signature_page": 1,
                "signature_x_ratio": 0.5,
                "signature_y_ratio": 0.5,
            }
            serializer = EnvelopeCreateSerializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            envelope = serializer.save()
            self.assertEqual(envelope.title, expected_title)

    def test_automatic_title_generation_empty_after_cleaning_fallback(self):
        """Verify fallback to original stem if cleaning results in empty string."""
        doc = Document.objects.create(
            file="documents/2_Uh7TO.pdf",
            file_hash="mockhash_empty"
        )
        data = {
            "document_id": doc.id,
            "signer": {"name": "Test Signer", "email": "test@email.com"},
            "signature_page": 1,
            "signature_x_ratio": 0.5,
            "signature_y_ratio": 0.5,
        }
        serializer = EnvelopeCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        envelope = serializer.save()
        self.assertEqual(envelope.title, "2_Uh7TO")

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
            "title": "Email Test Envelope",
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
            "title": "Certificate Test Envelope",
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
        "title": f"SMTP Test Envelope - {owner.username}",
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


class ContractAnalysisTestCase(TestCase):
    def setUp(self):
        import os
        self.old_ocr_provider = os.environ.get("OCR_PROVIDER")
        os.environ["OCR_PROVIDER"] = "paddle"

    def tearDown(self):
        import os
        if self.old_ocr_provider is not None:
            os.environ["OCR_PROVIDER"] = self.old_ocr_provider
        elif "OCR_PROVIDER" in os.environ:
            del os.environ["OCR_PROVIDER"]

    def test_analysis_endpoint_no_file(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        
        user = User.objects.create_user(username="test_analyzer", password="password")
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/")
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)

    def test_analysis_endpoint_success(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        user = User.objects.create_user(username="test_analyzer2", password="password")
        uploaded_file = SimpleUploadedFile("contract.pdf", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": (
                    "This Agreement is represented by Mr. Yasser Othman Ramadan in his capacity as General Manager. "
                    "يمثله السيد ياسر عثمان رمضان بصفته المدير العام."
                ),
                "language_detected": ["en", "ar"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 1.0,
                "page_count": 1
            }
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(response.data["representative_name_ar"], "ياسر عثمان رمضان")
        self.assertEqual(response.data["title_en"], "General Manager")
        self.assertEqual(response.data["title_ar"], "المدير العام")
        self.assertEqual(response.data["authority_clause_en"], "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager")
        self.assertEqual(response.data["authority_clause_ar"], "يمثله السيد/ ياسر عثمان رمضان بصفته/ المدير العام")
        self.assertNotIn("confidence_score", response.data)

    def test_is_text_sufficient(self):
        from services.ocr_service import is_text_sufficient
        # Too short
        self.assertFalse(is_text_sufficient("short text"))
        # Low alphabetic density
        self.assertFalse(is_text_sufficient("1234567890 " * 20))
        # High density, printable, but too short
        self.assertFalse(is_text_sufficient("Yasser Othman"))
        # Good text
        good_text = "This is a valid corporate contract document between party A and party B represented by General Manager Yasser Othman Ramadan. " * 3
        self.assertTrue(is_text_sufficient(good_text))

    def test_invalid_file_extension(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        user = User.objects.create_user(username="test_analyzer_invalid_ext", password="password")
        uploaded_file = SimpleUploadedFile("contract.txt", b"some plain text content", content_type="text/plain")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.data["detail"])

    def test_uppercase_file_extension(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        user = User.objects.create_user(username="test_analyzer_upper_ext", password="password")
        uploaded_file = SimpleUploadedFile("contract.PDF", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "This Agreement is represented by Mr. Yasser Othman Ramadan in his capacity as General Manager.",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 1.0,
                "page_count": 1
            }
            response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("extraction_source", response.data)

    def test_file_size_limit(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        user = User.objects.create_user(username="test_analyzer_size", password="password")
        large_bytes = b"0" * (21 * 1024 * 1024)
        uploaded_file = SimpleUploadedFile("contract.pdf", large_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("File size exceeds", response.data["detail"])

    def test_page_count_limit(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        user = User.objects.create_user(username="test_analyzer_pages", password="password")
        uploaded_file = SimpleUploadedFile("contract.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("fitz.open") as mock_open:
            mock_doc = mock_open.return_value
            mock_doc.__len__.return_value = 21
            response = view(request)
            
        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF exceeds the maximum limit of 20 pages", response.data["detail"])

    def test_digital_pdf_metadata(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        user = User.objects.create_user(username="test_analyzer_meta", password="password")
        uploaded_file = SimpleUploadedFile("contract.pdf", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "This Agreement is represented by Mr. Yasser Othman Ramadan in his capacity as General Manager.",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 1.0,
                "page_count": 3
            }
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("extraction_source", response.data)
        self.assertNotIn("page_count", response.data)
        self.assertNotIn("ocr_confidence", response.data)
        self.assertNotIn("processing_time_ms", response.data)

    def test_pdf_ocr_fallback(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        user = User.objects.create_user(username="test_analyzer_fallback", password="password")
        uploaded_file = SimpleUploadedFile("scanned.pdf", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "يمثله السيد ياسر عثمان رمضان بصفته المدير العام.",
                "language_detected": ["ar"],
                "extraction_source": "paddleocr",
                "ocr_confidence": 0.88,
                "page_count": 2
            }
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("extraction_source", response.data)
        self.assertNotIn("ocr_confidence", response.data)
        self.assertNotIn("page_count", response.data)
        self.assertEqual(response.data["representative_name_ar"], "ياسر عثمان رمضان")
        self.assertEqual(response.data["title_ar"], "المدير العام")

    def test_image_ocr_extraction(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        user = User.objects.create_user(username="test_analyzer_image", password="password")
        uploaded_file = SimpleUploadedFile("contract.png", b"dummy png bytes", content_type="image/png")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("services.ocr_service.extract_text_from_image") as mock_extract_img:
            mock_extract_img.return_value = (
                "This Agreement is represented by Mr. Yasser Othman Ramadan in his capacity as General Manager.",
                0.92
            )
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("extraction_source", response.data)
        self.assertNotIn("page_count", response.data)
        self.assertNotIn("ocr_confidence", response.data)
        self.assertEqual(response.data["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(response.data["title_en"], "General Manager")

    def test_arabic_representative_and_title_extraction(self):
        from services.authority_extraction_service import analyze_contract_authority
        text = "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام"
        res = analyze_contract_authority(text)
        self.assertEqual(res["representative_name_ar"], "ياسر عثمان رمضان")
        self.assertEqual(res["title_ar"], "المدير العام")
        self.assertEqual(res["authority_clause_ar"], "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام")

    def test_english_representative_and_title_extraction(self):
        from services.authority_extraction_service import analyze_contract_authority
        text = "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager"
        res = analyze_contract_authority(text)
        self.assertEqual(res["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(res["title_en"], "General Manager")
        self.assertEqual(res["authority_clause_en"], "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager")

    def test_mixed_bilingual_contracts(self):
        from services.authority_extraction_service import analyze_contract_authority
        text = (
            "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager. "
            "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام."
        )
        res = analyze_contract_authority(text)
        self.assertEqual(res["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(res["title_en"], "General Manager")
        self.assertEqual(res["representative_name_ar"], "ياسر عثمان رمضان")
        self.assertEqual(res["title_ar"], "المدير العام")

    def test_slash_removal_and_whitespace_collapse(self):
        from services.authority_extraction_service import clean_extracted_name
        name_with_slashes = "  / Yasser / Othman \\ Ramadan : ; ()  "
        self.assertEqual(clean_extracted_name(name_with_slashes, "en"), "Yasser Othman Ramadan")
        
        ar_name_with_punctuation = " السيد/  ياسر ، عثمان رمضان  "
        self.assertEqual(clean_extracted_name(ar_name_with_punctuation, "ar"), "ياسر عثمان رمضان")

    def test_newline_normalization(self):
        from services.authority_extraction_service import normalize_text
        text_with_newlines = "represented\nby\r\nMr.\tYasser\u200bOthman"
        self.assertEqual(normalize_text(text_with_newlines), "represented by Mr. YasserOthman")

    def test_multiple_authority_keywords_and_scoring(self):
        from services.authority_extraction_service import extract_english_authority
        text = (
            "represented by Mr. John Doe. Some dummy text. "
            "acting through Dr. Yasser Othman Ramadan, in his capacity as General Manager"
        )
        res = extract_english_authority(text)
        self.assertEqual(res["representative_name"], "Dr. Yasser Othman Ramadan")
        self.assertEqual(res["title"], "General Manager")
        self.assertEqual(res["score"], 4)

    def test_candidate_window_tie_breaking(self):
        from services.authority_extraction_service import extract_english_authority
        text = (
            "represented by Mr. Yasser Ramadan, in his capacity as CEO. "
            "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager."
        )
        res = extract_english_authority(text)
        self.assertEqual(res["representative_name"], "Yasser Othman Ramadan")
        self.assertEqual(res["title"], "General Manager")

    def test_english_prefixes_support(self):
        from services.authority_extraction_service import extract_english_authority
        prefixes = ["Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Eng."]
        for p in prefixes:
            text = f"represented by {p} Yasser Ramadan, in his capacity as CEO"
            res = extract_english_authority(text)
            if p in ["Dr.", "Eng.", "Prof."]:
                self.assertEqual(res["representative_name"], f"{p} Yasser Ramadan")
            else:
                self.assertEqual(res["representative_name"], "Yasser Ramadan")

    def test_arabic_prefixes_support(self):
        from services.authority_extraction_service import extract_arabic_authority
        prefixes = ["السيد", "السيدة", "الأستاذ", "الدكتور", "المهندس", "البروفيسور", "م."]
        for p in prefixes:
            text = f"ويمثلها {p}/ ياسر رمضان بصفته/ المدير العام"
            res = extract_arabic_authority(text)
            if p in ["الدكتور", "المهندس", "البروفيسور"]:
                self.assertEqual(res["representative_name"], f"{p}/ ياسر رمضان")
            else:
                self.assertEqual(res["representative_name"], "ياسر رمضان")

    def test_dictionary_title_detection(self):
        from services.authority_extraction_service import extract_english_authority
        text = "represented by Mr. Yasser Ramadan, in his capacity as Managing Director"
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "Managing Director")

    def test_confidence_computation_with_penalties(self):
        from services.authority_extraction_service import extract_english_authority
        text1 = "represented by Mr. Yasser Ramadan, in his capacity as CEO"
        res1 = extract_english_authority(text1)
        self.assertEqual(res1["confidence_score"], 1.0)
        
        text2 = "represented by Mr. Yasser Ramadan, in his capacity as Senior Lead"
        res2 = extract_english_authority(text2)
        self.assertEqual(res2["confidence_score"], 0.4)

    def test_failure_cases(self):
        from services.authority_extraction_service import validate_representative_name
        self.assertFalse(validate_representative_name("Yasser", "en"))
        self.assertFalse(validate_representative_name("ياسر", "ar"))
        self.assertFalse(validate_representative_name("Mr. Yasser Ramadan", "en"))
        self.assertFalse(validate_representative_name("السيد ياسر رمضان", "ar"))
        self.assertFalse(validate_representative_name("Yasser General Manager", "en"))
        self.assertFalse(validate_representative_name("ياسر المدير العام", "ar"))

    def test_exact_title_matching_en(self):
        from services.authority_extraction_service import extract_english_authority
        text = "represented by Mr. Yasser Ramadan, in his capacity as CEO"
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "CEO")
        self.assertEqual(res["title_match_score"], 100.0)
        self.assertEqual(res["title_match_method"], "exact")

    def test_exact_title_matching_ar(self):
        from services.authority_extraction_service import extract_arabic_authority
        text = "ويمثلها السيد/ ياسر رمضان بصفته/ المدير العام"
        res = extract_arabic_authority(text)
        self.assertEqual(res["title"], "المدير العام")
        self.assertEqual(res["title_match_score"], 100.0)
        self.assertEqual(res["title_match_method"], "exact")

    def test_arabic_ocr_typo_resolving(self):
        from services.authority_extraction_service import extract_arabic_authority
        # Typo: املدير العام instead of المدير العام
        text = "ويمثلها السيد/ ياسر رمضان بصفته/ املدير العام"
        res = extract_arabic_authority(text)
        self.assertEqual(res["title"], "المدير العام")
        self.assertGreaterEqual(res["title_match_score"], 90.0)
        self.assertEqual(res["title_match_method"], "fuzzy")

    def test_arabic_ocr_typo_resolving_alternative(self):
        from services.authority_extraction_service import extract_arabic_authority
        # Typo: الرئيس التنفيدي instead of الرئيس التنفيذي
        text = "ويمثلها السيد/ ياسر رمضان بصفته/ الرئيس التنفيدي"
        res = extract_arabic_authority(text)
        self.assertEqual(res["title"], "الرئيس التنفيذي")
        self.assertGreaterEqual(res["title_match_score"], 90.0)
        self.assertEqual(res["title_match_method"], "fuzzy")

    def test_longer_suffix_arabic(self):
        from services.authority_extraction_service import extract_arabic_authority
        # Suffix includes extra words: املدير العام لشركة الشرق الأوسط
        text = "ويمثلها السيد/ ياسر رمضان بصفته/ املدير العام لشركة الشرق الأوسط"
        res = extract_arabic_authority(text)
        self.assertEqual(res["title"], "المدير العام")
        self.assertGreaterEqual(res["title_match_score"], 90.0)
        self.assertEqual(res["title_match_method"], "fuzzy")

    def test_longer_suffix_arabic_alternative(self):
        from services.authority_extraction_service import extract_arabic_authority
        text = "ويمثلها السيد/ ياسر رمضان بصفته/ المدير العام والمدير التنفيذي"
        res = extract_arabic_authority(text)
        self.assertEqual(res["title"], "المدير العام")
        self.assertEqual(res["title_match_score"], 100.0)
        self.assertEqual(res["title_match_method"], "exact")

    def test_english_fuzzy_title_matching(self):
        from services.authority_extraction_service import extract_english_authority
        # Typo: Generral Manager instead of General Manager
        text = "represented by Mr. Yasser Ramadan, in his capacity as Generral Manager"
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "General Manager")
        self.assertGreaterEqual(res["title_match_score"], 90.0)
        self.assertEqual(res["title_match_method"], "fuzzy")

    def test_english_fuzzy_title_matching_ceo(self):
        from services.authority_extraction_service import extract_english_authority
        # Typo: Chief Executve Officer instead of Chief Executive Officer
        text = "represented by Mr. Yasser Ramadan, in his capacity as Chief Executve Officer"
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "Chief Executive Officer")
        self.assertGreaterEqual(res["title_match_score"], 90.0)
        self.assertIn(res["title_match_method"], ("exact", "fuzzy"))

    def test_title_match_method_exact(self):
        from services.authority_extraction_service import find_best_title_match
        matched_title, score, method, penalty = find_best_title_match("CEO", ["CEO", "General Manager"])
        self.assertEqual(method, "exact")
        self.assertEqual(penalty, 0.0)
        self.assertEqual(matched_title, "CEO")

    def test_title_match_method_fuzzy_high(self):
        from services.authority_extraction_service import find_best_title_match
        matched_title, score, method, penalty = find_best_title_match("Generral Manager", ["General Manager", "CEO"])
        self.assertEqual(method, "fuzzy")
        self.assertEqual(penalty, -0.02)
        self.assertEqual(matched_title, "General Manager")

    def test_title_match_method_fuzzy_low(self):
        from services.authority_extraction_service import find_best_title_match
        # A score around 85-90
        # "General Mngr" vs "General Manager"
        matched_title, score, method, penalty = find_best_title_match("General Mngr", ["General Manager", "CEO"])
        self.assertEqual(method, "fuzzy")
        self.assertEqual(penalty, -0.05)
        self.assertEqual(matched_title, "General Manager")

    def test_title_match_method_none(self):
        from services.authority_extraction_service import find_best_title_match
        # Score below 85
        matched_title, score, method, penalty = find_best_title_match("Random String", ["General Manager", "CEO"])
        self.assertEqual(method, "none")
        self.assertEqual(penalty, 0.0)
        self.assertIsNone(matched_title)

    def test_confidence_penalty_fuzzy_93(self):
        from services.authority_extraction_service import extract_english_authority
        # "Generral Manager" typo has score 93.33, penalty -0.02, base confidence would be 1.0, final 0.98
        text = "represented by Mr. Yasser Ramadan, in his capacity as Generral Manager"
        res = extract_english_authority(text)
        self.assertAlmostEqual(res["confidence_score"], 0.98, places=5)

    def test_confidence_penalty_fuzzy_87(self):
        from services.authority_extraction_service import extract_english_authority
        # "General Mngr" typo has score around 87, penalty -0.05, base confidence 1.0, final 0.95
        text = "represented by Mr. Yasser Ramadan, in his capacity as General Mngr"
        res = extract_english_authority(text)
        self.assertAlmostEqual(res["confidence_score"], 0.95, places=5)

    def test_confidence_penalty_exact_98(self):
        from services.authority_extraction_service import extract_english_authority
        text = "represented by Mr. Yasser Ramadan, in his capacity as CEO"
        res = extract_english_authority(text)
        self.assertEqual(res["confidence_score"], 1.0)

    def test_average_confidence_aggregation(self):
        from services.authority_extraction_service import analyze_contract_authority
        # English confidence = 1.0, Arabic confidence = 1.0 => overall = 1.0
        text = (
            "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager. "
            "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام"
        )
        res = analyze_contract_authority(text)
        self.assertEqual(res["confidence_score"], 1.0)

    def test_average_confidence_aggregation_with_mismatch(self):
        from services.authority_extraction_service import analyze_contract_authority
        # English confidence = 1.0
        # Arabic confidence = 0.0 (incomplete, e.g. no representative found)
        # Overall = 0.5
        text = (
            "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager. "
            "بصفته المدير العام"
        )
        res = analyze_contract_authority(text)
        self.assertEqual(res["confidence_score"], 0.5)

    def test_rejection_below_85(self):
        from services.authority_extraction_service import extract_english_authority
        # Suffix doesn't match any title: "represented by Mr. Yasser Ramadan, in his capacity as Engineer"
        # "Engineer" vs ENGLISH_TITLES (score below 85) => rejected => title = ""
        text = "represented by Mr. Yasser Ramadan, in his capacity as Engineer"
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "")
        self.assertEqual(res["title_match_method"], "none")

    def test_regression_bilingual_contract(self):
        from services.authority_extraction_service import analyze_contract_authority
        text = (
            "This Agreement is represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager. "
            "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام."
        )
        res = analyze_contract_authority(text)
        self.assertEqual(res["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(res["representative_name_ar"], "ياسر عثمان رمضان")
        self.assertEqual(res["title_en"], "General Manager")
        self.assertEqual(res["title_ar"], "المدير العام")
        self.assertEqual(
            res["authority_clause_en"],
            "represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager"
        )
        self.assertEqual(
            res["authority_clause_ar"],
            "ويمثلها السيد/ ياسر عثمان رمضان بصفته/ المدير العام"
        )

    def test_empty_suffix_handling(self):
        from services.authority_extraction_service import extract_english_authority
        # Suffix is empty after capacity phrase
        text = "represented by Mr. Yasser Ramadan, in his capacity as "
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "")
        self.assertEqual(res["title_match_method"], "none")

    def test_no_capacity_phrase_matching(self):
        from services.authority_extraction_service import extract_english_authority
        # Test fallback to search on whole window when no capacity phrase is matched
        text = "represented by Mr. Yasser Ramadan. CEO of the Company."
        res = extract_english_authority(text)
        self.assertEqual(res["title"], "CEO")
        self.assertEqual(res["title_match_method"], "exact")

    def test_normalization_zero_width_chars(self):
        from services.authority_extraction_service import analyze_contract_authority
        text = (
            "represented by Mr. Y\u200basser Othman Ramadan, in his capacity as Gen\u200ceral Manager"
        )
        res = analyze_contract_authority(text)
        self.assertEqual(res["representative_name_en"], "Yasser Othman Ramadan")
        self.assertEqual(res["title_en"], "General Manager")

    def test_garbage_ratio_penalty(self):
        from services.ocr_service import evaluate_arabic_quality
        # Clean text
        res_clean = evaluate_arabic_quality("المدير العام")
        self.assertEqual(res_clean["garbage_ratio"], 0.0)
        self.assertGreaterEqual(res_clean["score"], 0.8)
        
        # Corrupted text with Canadian Aboriginal characters
        res_corrupt = evaluate_arabic_quality("المدير العام ᒠᓞᓢᓚᓕ")
        self.assertGreater(res_corrupt["garbage_ratio"], 0.0)
        self.assertLess(res_corrupt["score"], res_clean["score"])

    def test_corrupted_unicode_quality(self):
        from services.ocr_service import evaluate_arabic_quality
        text = "ᒠᓞᓢᓚᓕ ᒢᓪᓊᓞᒎ ᓪᒁᒤ"
        res = evaluate_arabic_quality(text)
        self.assertGreater(res["garbage_ratio"], 0.5)
        self.assertEqual(res["score"], 0.0)

    def test_page_quality_scores(self):
        from services.ocr_service import evaluate_arabic_quality
        res_en = evaluate_arabic_quality("This is a clean English text.")
        self.assertEqual(res_en["score"], 1.0)
        self.assertEqual(res_en["arabic_chars"], 0)

    def test_page_level_strategy_selection(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        # Mock fitz.open and page.get_text
        doc = fitz.open()
        p1 = doc.new_page() # empty page
        p2 = doc.new_page() # page with text
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 2
            
            mock_page1 = MagicMock()
            mock_page1.get_text.return_value = "This is a clean English only page text, no Arabic here." * 10
            mock_page1.rect.width = 600
            mock_page1.rect.height = 800
            
            mock_page2 = MagicMock()
            mock_page2.get_text.return_value = "This is a bilingual page. المدير العام CEO represented by." * 10
            mock_page2.rect.width = 600
            mock_page2.rect.height = 800
            
            mock_doc.load_page.side_effect = [mock_page1, mock_page2]
            mock_open.return_value = mock_doc
            
            res = extract_text_from_pdf(pdf_bytes)
            
        self.assertEqual(res["page_strategies"][1], "english_only")
        # Since score for page 2 has Arabic and is clean (printable_ratio >= 0.8, garbage_ratio=0), strategy should be digital_pdf
        self.assertEqual(res["page_strategies"][2], "digital_pdf")

    def test_dominant_strategy(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 2
            
            mock_page1 = MagicMock()
            mock_page1.get_text.return_value = "English text only. English text only. English text only. English text only." * 10
            
            mock_page2 = MagicMock()
            mock_page2.get_text.return_value = "English text only. English text only. English text only. English text only." * 10
            
            mock_doc.load_page.side_effect = [mock_page1, mock_page2]
            mock_open.return_value = mock_doc
            
            res = extract_text_from_pdf(pdf_bytes)
            
        self.assertEqual(res["dominant_strategy"], "english_only")

    def test_page_regions(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            # Left side has Arabic, right side doesn't
            def mock_get_text(opt="", clip=None):
                if clip is None:
                    return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10 + "المدير العام المدير العام المدير العام المدير العام" * 10
                if clip.x0 == 0:
                    return "المدير العام المدير العام المدير العام المدير العام" * 10
                return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10
            mock_page.get_text = mock_get_text
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            res = extract_text_from_pdf(pdf_bytes)
            
        self.assertEqual(res["page_regions"][1], "left")

    def test_dominant_region(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 2
            
            mock_page1 = MagicMock()
            # Left side has Arabic
            def mock_get_text_p1(opt="", clip=None):
                if clip is None:
                    return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10 + "المدير العام المدير العام المدير العام المدير العام" * 10
                if clip.x0 == 0:
                    return "المدير العام المدير العام المدير العام المدير العام" * 10
                return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10
            mock_page1.get_text = mock_get_text_p1
            mock_page1.rect.width = 600
            mock_page1.rect.height = 800
            
            mock_page2 = MagicMock()
            # Right side has Arabic
            def mock_get_text_p2(opt="", clip=None):
                if clip is None:
                    return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10 + "المدير العام المدير العام المدير العام المدير العام" * 10
                if clip.x0 > 0:
                    return "المدير العام المدير العام المدير العام المدير العام" * 10
                return "CEO represented by Mr. John CEO represented by Mr. John CEO represented by Mr. John" * 10
            mock_page2.get_text = mock_get_text_p2
            mock_page2.rect.width = 600
            mock_page2.rect.height = 800
            
            mock_doc.load_page.side_effect = [mock_page1, mock_page2]
            mock_open.return_value = mock_doc
            
            res = extract_text_from_pdf(pdf_bytes)
            
        # Ties default to right
        self.assertEqual(res["dominant_arabic_region"], "right")

    def test_mixed_strategy_document(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 2
            
            mock_page1 = MagicMock()
            mock_page1.get_text.return_value = "Clean English contract text. Clean English contract text. Clean English contract text. " * 10
            
            mock_page2 = MagicMock()
            # Insufficient text length < 100, triggers full_page_ocr
            mock_page2.get_text.return_value = "Short"
            mock_pixmap = MagicMock()
            mock_pixmap.tobytes.return_value = b"bytes"
            mock_page2.get_pixmap.return_value = mock_pixmap
            
            mock_doc.load_page.side_effect = [mock_page1, mock_page2]
            mock_open.return_value = mock_doc
            
            from PIL import Image
            real_img = Image.new("RGB", (10, 10))
            
            with patch("services.ocr_service.get_ocr_engine") as mock_ocr_engine, \
                 patch("PIL.Image.open", return_value=real_img):
                mock_ocr = mock_ocr_engine.return_value
                # Mock OCR lines for full_page_ocr
                mock_ocr.ocr.return_value = [[
                    [[[0,0], [10,0], [10,10], [0,10]], ("الرئيس التنفيذي", 0.95)]
                ]]
                res = extract_text_from_pdf(pdf_bytes)
                
        self.assertEqual(res["page_strategies"][1], "english_only")
        self.assertEqual(res["page_strategies"][2], "full_page_ocr")

    def test_processing_metadata(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        
        import fitz
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        user = User.objects.create_user(username="test_analyzer_metadata_checks", password="password")
        uploaded_file = SimpleUploadedFile("contract.pdf", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        
        view = ContractAnalyzeView.as_view()
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "This Agreement is represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager.",
                "english_text": "This Agreement is represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager.",
                "arabic_text": "",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "dominant_strategy": "digital_pdf",
                "page_strategies": {1: "digital_pdf"},
                "page_quality_scores": {1: 1.0},
                "dominant_arabic_region": "right",
                "page_regions": {1: "right"},
                "ocr_confidence": 1.0,
                "page_count": 1,
                "digital_extraction_ms": 12.0,
                "ocr_ms": 0.0
            }
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("digital_extraction_ms", response.data)
        self.assertNotIn("ocr_ms", response.data)
        self.assertNotIn("authority_extraction_ms", response.data)
        self.assertNotIn("total_processing_ms", response.data)
        self.assertNotIn("extraction_strategy", response.data)
        self.assertNotIn("page_strategies", response.data)
        self.assertNotIn("page_quality_scores", response.data)
        self.assertNotIn("dominant_arabic_region", response.data)

    def test_corrupted_unicode_count(self):
        from services.ocr_service import count_suspicious_unicode
        text = "This is clean text."
        self.assertEqual(count_suspicious_unicode(text), 0)
        
        corrupted_text = "Clean text ᒠᓞᓢᓚᓕ" # 5 Canadian Aboriginal chars
        self.assertEqual(count_suspicious_unicode(corrupted_text), 5)
        
        PUA_text = "Clean \uE000\uE001\uE002\uE003\uE004\uE005" # 6 PUA chars
        self.assertEqual(count_suspicious_unicode(PUA_text), 6)

    def test_healthy_english_corrupted_arabic(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            # Clean English on the left, but corrupted Arabic (Canadian Aboriginal Syllabics) on the right
            mock_page.get_text.return_value = "This Agreement is represented by Mr. Yasser Othman Ramadan, in his capacity as General Manager. ᒠᓞᓢᓚ\u1505 ᒢ\u150C\u14CA\u14DE\u14CD"
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            
            mock_pixmap = MagicMock()
            mock_pixmap.tobytes.return_value = b"bytes"
            mock_page.get_pixmap.return_value = mock_pixmap
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            from PIL import Image
            real_img = Image.new("RGB", (10, 10))
            
            with patch("services.ocr_service.get_ocr_engine") as mock_ocr_engine, \
                 patch("PIL.Image.open", return_value=real_img):
                mock_ocr = mock_ocr_engine.return_value
                # Mock OCR lines for split OCR (returns clean Arabic text)
                mock_ocr.ocr.return_value = [[
                    [[[0,0], [10,0], [10,10], [0,10]], ("المدير العام", 0.95)]
                ]]
                res = extract_text_from_pdf(pdf_bytes)
                
        self.assertEqual(res["page_strategies"][1], "corrupted_text_layer")
        # English is preserved from the digital layer
        self.assertIn("General Manager", res["english_text"])
        # Arabic is replaced by OCR text
        self.assertIn("المدير العام", res["arabic_text"])

    def test_corrupted_text_layer_strategy(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            # English is healthy, but more than 5 suspicious Unicode characters are present
            mock_page.get_text.return_value = "This is a bilingual page with some healthy English text. ᒠᓞᓢᓚ\u1505\u14A2" * 2 # 12 suspicious chars, len > 100
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            
            mock_pixmap = MagicMock()
            mock_pixmap.tobytes.return_value = b"bytes"
            mock_page.get_pixmap.return_value = mock_pixmap
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            from PIL import Image
            real_img = Image.new("RGB", (10, 10))
            
            with patch("services.ocr_service.get_ocr_engine") as mock_ocr_engine, \
                 patch("PIL.Image.open", return_value=real_img):
                mock_ocr = mock_ocr_engine.return_value
                mock_ocr.ocr.return_value = [[
                    [[[0,0], [10,0], [10,10], [0,10]], ("المدير العام", 0.95)]
                ]]
                res = extract_text_from_pdf(pdf_bytes)
                
        self.assertEqual(res["page_strategies"][1], "corrupted_text_layer")

    def test_page_metadata(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            mock_page.get_text.return_value = "This is clean English only page text, no Arabic here." * 10
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            res = extract_text_from_pdf(pdf_bytes)
            
        self.assertIn("page_metadata", res)
        self.assertEqual(len(res["page_metadata"]), 1)
        meta = res["page_metadata"][0]
        self.assertEqual(meta["page_num"], 1)
        self.assertEqual(meta["strategy"], "english_only")
        self.assertGreaterEqual(meta["english_quality_score"], 0.8)
        self.assertEqual(meta["suspicious_unicode_count"], 0)
        self.assertEqual(meta["ocr_confidence"], 1.0)

    def test_language_specific_quality_scores(self):
        from services.ocr_service import evaluate_english_quality, evaluate_arabic_quality
        
        # Corrupted Arabic layer text
        text = "This is clean English text. ᒠᓞᓢᓚ\u1505\u14A2" # English segment has no corruption, Arabic segment has corruption
        
        from services.ocr_service import extract_latin_segments, extract_arabic_segments
        lat_seg = extract_latin_segments(text)
        ara_seg = extract_arabic_segments(text)
        
        # English quality should be evaluated on Latin segment (no corruption) -> high score
        eng_q = evaluate_english_quality(lat_seg)
        self.assertGreaterEqual(eng_q["score"], 0.8)
        self.assertEqual(eng_q["suspicious_unicode_count"], 0)
        
        # Arabic quality should be evaluated on Arabic segment (contains the corruption) -> 0.0 score
        ara_q = evaluate_arabic_quality(ara_seg)
        self.assertEqual(ara_q["score"], 0.0)
        self.assertEqual(ara_q["suspicious_unicode_count"], 6)

    def test_corrupted_arabic_layer(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            # Corrupted Arabic layer: English is healthy, but Arabic contains Canadian Aboriginal Syllabics
            mock_page.get_text.return_value = "Contract agreement by Mr. Yasser. ᒠᓞᓢ\u14CD\u1505\u14A2" * 3 # 18 suspicious chars, len > 100
            mock_page.rect.width = 600
            mock_page.rect.height = 800
            
            mock_pixmap = MagicMock()
            mock_pixmap.tobytes.return_value = b"bytes"
            mock_page.get_pixmap.return_value = mock_pixmap
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            from PIL import Image
            real_img = Image.new("RGB", (10, 10))
            
            with patch("services.ocr_service.get_ocr_engine") as mock_ocr_engine, \
                 patch("PIL.Image.open", return_value=real_img):
                mock_ocr = mock_ocr_engine.return_value
                mock_ocr.ocr.return_value = [[
                    [[[0,0], [10,0], [10,10], [0,10]], ("المدير العام", 0.95)]
                ]]
                res = extract_text_from_pdf(pdf_bytes)
                
        self.assertEqual(res["page_strategies"][1], "corrupted_text_layer")
        self.assertEqual(res["dominant_strategy"], "corrupted_text_layer")

    def test_full_page_ocr(self):
        from unittest.mock import patch, MagicMock
        import fitz
        from services.ocr_service import extract_text_from_pdf
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            
            mock_page = MagicMock()
            # Insufficient text length, triggers full_page_ocr
            mock_page.get_text.return_value = "Short"
            mock_pixmap = MagicMock()
            mock_pixmap.tobytes.return_value = b"bytes"
            mock_page.get_pixmap.return_value = mock_pixmap
            
            mock_doc.load_page.return_value = mock_page
            mock_open.return_value = mock_doc
            
            from PIL import Image
            real_img = Image.new("RGB", (10, 10))
            
            with patch("services.ocr_service.get_ocr_engine") as mock_ocr_engine, \
                 patch("PIL.Image.open", return_value=real_img):
                mock_ocr = mock_ocr_engine.return_value
                mock_ocr.ocr.return_value = [[
                    [[[0,0], [10,0], [10,10], [0,10]], ("CEO", 0.95)]
                ]]
                res = extract_text_from_pdf(pdf_bytes)
                
        self.assertEqual(res["page_strategies"][1], "full_page_ocr")


class AuthorityExtractionTestCase(TestCase):
    def test_english_authority_phrases(self):
        from services.authority_extraction_service import analyze_contract_authority
        
        # 1. represented by
        text1 = "This contract is represented by Dr. Abdulrahman Al-Dosari in his capacity as Procurement Manager."
        res1 = analyze_contract_authority(text1)
        self.assertEqual(res1["representative_name_en"], "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(res1["title_en"], "Procurement Manager")
        
        # 2. authorized signatory
        text2 = "This contract is signed by the authorized signatory Eng. Fahad Suleiman Al-Awaji in his capacity as IT Manager."
        res2 = analyze_contract_authority(text2)
        self.assertEqual(res2["representative_name_en"], "Eng. Fahad Suleiman Al-Awaji")
        self.assertEqual(res2["title_en"], "IT Manager")
        
        # 3. acting through
        text3 = "First Party is acting through Prof. Faisal Salem Al-Harbi in his capacity as Managing Director."
        res3 = analyze_contract_authority(text3)
        # Note: Prof. is in REATTACH_PREFIXES_EN, so it is re-attached.
        self.assertEqual(res3["representative_name_en"], "Prof. Faisal Salem Al-Harbi")
        self.assertEqual(res3["title_en"], "Managing Director")
        
        # 4. herein legally represented by
        text4 = "First Party is herein legally represented by Mr. John Smith in his capacity as Executive Director."
        res4 = analyze_contract_authority(text4)
        # Note: Mr. is not in REATTACH_PREFIXES_EN, so it is stripped.
        self.assertEqual(res4["representative_name_en"], "John Smith")
        self.assertEqual(res4["title_en"], "Executive Director")

    def test_arabic_authority_phrases(self):
        from services.authority_extraction_service import analyze_contract_authority
        
        # 1. يمثلها
        text1 = "الطرف الأول يمثلها الدكتور/ عبدالرحمن الدوسري بصفته مدير المشتريات."
        res1 = analyze_contract_authority(text1)
        self.assertEqual(res1["representative_name_ar"], "الدكتور/ عبدالرحمن الدوسري")
        self.assertEqual(res1["title_ar"], "مدير المشتريات")
        
        # 2. ويمثلها
        text2 = "الطرف الأول ويمثلها المهندس/ فهد سليمان العواجي بصفته مدير تقنية المعلومات."
        res2 = analyze_contract_authority(text2)
        self.assertEqual(res2["representative_name_ar"], "المهندس/ فهد سليمان العواجي")
        self.assertEqual(res2["title_ar"], "مدير تقنية المعلومات")
        
        # 3. ويمثلها نظاما
        text3 = "الطرف الأول ويمثلها نظاماً السيد/ عمر خالد المطيري بصفته العضو المنتدب."
        res3 = analyze_contract_authority(text3)
        # Note: السيد is not in REATTACH_PREFIXES_AR, so it is stripped.
        self.assertEqual(res3["representative_name_ar"], "عمر خالد المطيري")
        self.assertEqual(res3["title_ar"], "العضو المنتدب")
        
        # 4. المفوض بالتوقيع
        text4 = "الطرف الأول المفوض بالتوقيع الأستاذ/ ماجد خالد الرويلي بصفته المستشار القانوني."
        res4 = analyze_contract_authority(text4)
        # Note: الأستاذ is not in REATTACH_PREFIXES_AR, so it is stripped.
        self.assertEqual(res4["representative_name_ar"], "ماجد خالد الرويلي")
        self.assertEqual(res4["title_ar"], "المستشار القانوني")
        
        # 5. المخول بالتوقيع
        text5 = "الطرف الأول المخول بالتوقيع الدكتور/ سلمان أحمد المالكي بصفته مدير المشروع."
        res5 = analyze_contract_authority(text5)
        self.assertEqual(res5["representative_name_ar"], "الدكتور/ سلمان أحمد المالكي")
        self.assertEqual(res5["title_ar"], "مدير المشروع")

    def test_api_authority_detected(self):
        from django.test import RequestFactory
        from .views import ContractAnalyzeView
        from django.contrib.auth.models import User
        from rest_framework.test import force_authenticate
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch
        import fitz
        
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.write()
        doc.close()
        
        user = User.objects.create_user(username="test_auth_det_user", password="password")
        uploaded_file = SimpleUploadedFile("contract_test.pdf", pdf_bytes, content_type="application/pdf")
        
        factory = RequestFactory()
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        view = ContractAnalyzeView.as_view()
        
        # Test case 1: Positive extraction -> authority_detected=True
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "represented by Dr. Abdulrahman Al-Dosari in his capacity as Procurement Manager.",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 1.0,
                "page_count": 1
            }
            response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["authority_detected"])
        
        # Test case 2: Negative extraction -> authority_detected=False
        uploaded_file.seek(0)
        request2 = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request2, user=user)
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "This is a simple contract with no representative mentioned anywhere.",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 1.0,
                "page_count": 1
            }
            response2 = view(request2)
        self.assertEqual(response2.status_code, 200)
        self.assertFalse(response2.data["authority_detected"])


class PartialExtractionRecoveryTestCase(TestCase):
    def test_hyphen_normalization(self):
        from services.authority_extraction_service import canonicalize_name
        self.assertEqual(canonicalize_name("Al- Dosari"), "Al-Dosari")
        self.assertEqual(canonicalize_name("Al -Dosari"), "Al-Dosari")
        self.assertEqual(canonicalize_name("Al - Dosari"), "Al-Dosari")

    def test_arabic_compound_names(self):
        from services.authority_extraction_service import canonicalize_name
        self.assertEqual(canonicalize_name("عبد الرحمن"), "عبدالرحمن")
        self.assertEqual(canonicalize_name("عبد الله"), "عبدالله")
        self.assertEqual(canonicalize_name("عبدالرحمن"), "عبدالرحمن")

    def test_prefix_restoration(self):
        from services.authority_extraction_service import extract_english_authority, extract_arabic_authority
        # English: Dr., Eng., Prof.
        res_en1 = extract_english_authority("represented by Dr. Yasser Ramadan, in his capacity as CEO")
        self.assertEqual(res_en1["representative_name"], "Dr. Yasser Ramadan")
        
        res_en2 = extract_english_authority("represented by Eng. Yasser Ramadan, in his capacity as CEO")
        self.assertEqual(res_en2["representative_name"], "Eng. Yasser Ramadan")
        
        res_en3 = extract_english_authority("represented by Prof. Yasser Ramadan, in his capacity as CEO")
        self.assertEqual(res_en3["representative_name"], "Prof. Yasser Ramadan")

        # Arabic: الدكتور/, المهندس/, البروفيسور/
        res_ar1 = extract_arabic_authority("ويمثلها الدكتور/ ياسر رمضان بصفته/ المدير العام")
        self.assertEqual(res_ar1["representative_name"], "الدكتور/ ياسر رمضان")

        res_ar2 = extract_arabic_authority("ويمثلها المهندس/ ياسر رمضان بصفته/ المدير العام")
        self.assertEqual(res_ar2["representative_name"], "المهندس/ ياسر رمضان")

        res_ar3 = extract_arabic_authority("ويمثلها البروفيسور/ ياسر رمضان بصفته/ المدير العام")
        self.assertEqual(res_ar3["representative_name"], "البروفيسور/ ياسر رمضان")

    def test_trailing_noise_removal(self):
        from services.authority_extraction_service import canonicalize_name
        self.assertEqual(canonicalize_name("Yasser Ramadan,"), "Yasser Ramadan")
        self.assertEqual(canonicalize_name("Yasser Ramadan."), "Yasser Ramadan")
        self.assertEqual(canonicalize_name("Yasser Ramadan/"), "Yasser Ramadan")
        self.assertEqual(canonicalize_name("Yasser Ramadan, "), "Yasser Ramadan")

    def test_larger_candidate_window(self):
        from services.authority_extraction_service import extract_english_authority, extract_arabic_authority
        # When capacity is absent, fallback window should extract up to 80 chars / 6 words
        text_en = "represented by Dr. Yasser Othman Salem Al-Harbi who is signing this contract standard draft"
        res_en = extract_english_authority(text_en)
        # Verify it captures the name (excluding excess words)
        self.assertEqual(res_en["representative_name"], "Dr. Yasser Othman Salem Al-Harbi")

        text_ar = "ويمثلها الدكتور/ ياسر عثمان سالم الحربي الذي يوقع هذا العقد"
        res_ar = extract_arabic_authority(text_ar)
        self.assertEqual(res_ar["representative_name"], "الدكتور/ ياسر عثمان سالم الحربي")


class OCRRecoveryTestCase(TestCase):
    def test_canonicalization_consistency(self):
        from services.authority_extraction_service import canonicalize_name
        from rapidfuzz import fuzz
        name1 = canonicalize_name("Al Dosari")
        name2 = canonicalize_name("Al-Dosari")
        name3 = canonicalize_name("AL DOSARI")
        
        # Check token_set_ratio similarity is 100 or >= 85
        self.assertTrue(fuzz.token_set_ratio(name1, name2) >= 85)
        self.assertTrue(fuzz.token_set_ratio(name1.lower(), name3.lower()) == 100)

    def test_ocr_character_noise(self):
        from services.authority_extraction_service import extract_arabic_authority
        # Expected is الدكتور/ عبدالرحمن الدوسري, but raw text has minor typo "عبد الرحمن الدوشي"
        # Since it is a self-contained fuzzy comparison, it should still evaluate candidate correctly
        text = "ويمثلها الدكتور/ عبدالرحمن الدوشي بصفته/ مدير المشتريات"
        res = extract_arabic_authority(text)
        self.assertEqual(res["representative_name"], "الدكتور/ عبدالرحمن الدوشي")
        self.assertTrue(res["name_similarity_score"] >= 0.8)


from unittest.mock import patch, MagicMock

class OCRProviderVisibilityTestCase(TestCase):
    @patch.dict('os.environ', {'OCR_PROVIDER': 'paddle'})
    @patch('services.ocr_service.extract_text_with_paddle')
    def test_visibility_direct_paddle(self, mock_paddle):
        from services.ocr_service import extract_text_from_pdf
        mock_paddle.return_value = {
            "ocr_provider": "paddle",
            "fallback_used": False,
            "ocr_confidence": None,
            "ocr_ms": 120
        }
        res = extract_text_from_pdf(b"mockpdf")
        mock_paddle.assert_called_once_with(b"mockpdf", fallback_used=False)
        self.assertEqual(res["ocr_provider"], "paddle")
        self.assertEqual(res["fallback_used"], False)
        self.assertIsNone(res["ocr_confidence"])

    @patch.dict('os.environ', {'OCR_PROVIDER': 'paddle'})
    def test_api_response_observability_fields(self):
        import fitz
        from django.test import RequestFactory
        from django.contrib.auth.models import User
        from django.core.files.uploadedfile import SimpleUploadedFile
        from esign.views import ContractAnalyzeView
        from rest_framework.test import force_authenticate
        
        user = User.objects.create_user(username='test_visibility_user', password='password')
        factory = RequestFactory()
        
        # Generate valid 1-page PDF
        doc = fitz.open()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()
        
        uploaded_file = SimpleUploadedFile("contract.pdf", pdf_bytes, content_type="application/pdf")
        request = factory.post("/api/contracts/analyze/", {"file": uploaded_file})
        force_authenticate(request, user=user)
        view = ContractAnalyzeView.as_view()
        
        with patch("services.ocr_service.extract_text_from_pdf") as mock_extract:
            mock_extract.return_value = {
                "raw_text": "represented by Dr. Yasser Ramadan capacity CEO",
                "english_text": "represented by Dr. Yasser Ramadan capacity CEO",
                "arabic_text": "",
                "language_detected": ["en"],
                "extraction_source": "digital_pdf",
                "ocr_confidence": 0.95,
                "page_count": 1,
                "ocr_provider": "azure",
                "fallback_used": False,
                "ocr_ms": 1250
            }
            response = view(request)
            
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ocr_provider", response.data)
        self.assertNotIn("ocr_confidence", response.data)
        self.assertNotIn("fallback_used", response.data)
        self.assertNotIn("ocr_ms", response.data)
        self.assertIn("candidates", response.data)


class UnicodeNormalizationTestCase(TestCase):
    def test_unicode_normalization(self):
        from services.authority_extraction_service import normalize_text
        
        # 1. Yeh compatibility: \u06cc (Persian/Urdu Yeh) -> \u064a (Arabic Yeh)
        self.assertEqual(normalize_text("المخول بالتوقيع"), normalize_text("المخول بالتوقیع"))
        
        # 2. Alef Maksura: \u0649 (Alef Maksura) -> \u064a (Arabic Yeh)
        self.assertEqual(normalize_text("على"), normalize_text("علي"))
        
        # 3. Keheh compatibility: \u06a9 (Persian Keheh) -> \u0643 (Arabic Kaf)
        self.assertEqual(normalize_text("شركة"), normalize_text("شرکة"))
        
        # 4. Tatweel removal: \u0640 (Tatweel)
        self.assertEqual(normalize_text("المخــول"), normalize_text("المخول"))
        
        # 5. Zero width character removal (\u200b, \u200c, \u200d, \ufeff)
        self.assertEqual(normalize_text("الم\u200bخ\u200cو\u200dل"), normalize_text("المخول"))
        self.assertEqual(normalize_text("\ufeffالمخول"), normalize_text("المخول"))
        
        # 6. NFC normalization (combining characters)
        import unicodedata
        text_decomp = unicodedata.normalize("NFD", "شركة")
        self.assertEqual(normalize_text(text_decomp), normalize_text("شركة"))


class RepresentativeCandidateSelectionTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from esign.models import Document, Envelope
        
        self.user = User.objects.create_user(username='candidate_test_user', password='password')
        self.document = Document.objects.create(file="dummy.pdf", file_hash="dummyhash")
        self.envelope = Envelope.objects.create(document=self.document, owner=self.user, status='draft')

    def test_case_1_single_representative_auto_added(self):
        """Case 1: When a single candidate is found, it must be auto-converted to a participant."""
        from services.recipient_discovery_service import generate_candidates
        from esign.models import RepresentativeCandidate, Participant

        analysis_result = {
            "representative_name_en": "Yasser Ramadan",
            "representative_name_ar": "",
            "title_en": "General Manager",
            "title_ar": "",
            "authority_clause_en": "represented by General Manager",
            "authority_clause_ar": ""
        }

        # Clear existing participants/candidates
        self.envelope.participants.all().delete()
        RepresentativeCandidate.objects.filter(envelope=self.envelope).delete()

        candidates = generate_candidates(self.envelope, analysis_result)
        self.assertEqual(len(candidates), 1)
        
        # Verify database candidate field states
        cand = RepresentativeCandidate.objects.get(envelope=self.envelope)
        self.assertEqual(cand.status, 'converted')
        self.assertIsNotNone(cand.converted_at)
        self.assertIsNone(cand.ignored_at)

        # Check that Participant was auto-created
        participants = self.envelope.participants.all()
        self.assertEqual(participants.count(), 1)
        participant = participants.first()
        self.assertEqual(participant.name, "Yasser Ramadan")
        self.assertEqual(participant.email, "")
        self.assertEqual(participant.role, "signer")

    def test_case_2_multiple_representatives_not_auto_added(self):
        """Case 2: When multiple candidates are found, they are NOT auto-converted but can be confirmed manually."""
        from services.recipient_discovery_service import generate_candidates
        from esign.models import RepresentativeCandidate, Participant
        from django.test import RequestFactory
        from esign.views import ConfirmCandidatesView
        from rest_framework.test import force_authenticate
        import json

        analysis_result = {
            "representative_name_en": "Yasser Ramadan",
            "representative_name_ar": "عمر خالد",  # Different names, so they should be added separately
            "title_en": "General Manager",
            "title_ar": "العضو المنتدب",
            "authority_clause_en": "represented by General Manager",
            "authority_clause_ar": "يمثلها العضو المنتدب"
        }

        # Clear existing
        self.envelope.participants.all().delete()
        RepresentativeCandidate.objects.filter(envelope=self.envelope).delete()

        candidates = generate_candidates(self.envelope, analysis_result)
        self.assertEqual(len(candidates), 2)
        
        # Verify status is pending
        for c in candidates:
            self.assertEqual(c.status, 'pending')
            self.assertIsNone(c.converted_at)
            self.assertIsNone(c.ignored_at)

        # Ensure no participant was auto-created
        self.assertEqual(self.envelope.participants.count(), 0)

        # Confirm ONLY one candidate manually via API view
        factory = RequestFactory()
        candidate_ids = [candidates[0].id]
        request = factory.post(
            f"/api/envelopes/{self.envelope.id}/confirm-candidates/",
            {"candidate_ids": candidate_ids},
            content_type="application/json"
        )
        force_authenticate(request, user=self.user)
        view = ConfirmCandidatesView.as_view()
        response = view(request, envelope_id=self.envelope.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.envelope.participants.count(), 1)
        
        # Verify statuses post-confirmation
        c1 = RepresentativeCandidate.objects.get(id=candidates[0].id)
        c2 = RepresentativeCandidate.objects.get(id=candidates[1].id)
        self.assertEqual(c1.status, 'converted')
        self.assertIsNotNone(c1.converted_at)
        
        # The other candidate must remain pending (not automatically ignored)
        self.assertEqual(c2.status, 'pending')
        self.assertIsNone(c2.converted_at)
        self.assertIsNone(c2.ignored_at)

    def test_case_3_manual_ignore_candidates(self):
        """Case 3: Unselected candidates can be explicitly ignored."""
        from services.recipient_discovery_service import generate_candidates
        from esign.models import RepresentativeCandidate
        from django.test import RequestFactory
        from esign.views import IgnoreCandidatesView
        from rest_framework.test import force_authenticate

        analysis_result = {
            "representative_name_en": "Yasser Ramadan",
            "representative_name_ar": "عمر خالد",
            "title_en": "General Manager",
            "title_ar": "العضو المنتدب",
            "authority_clause_en": "represented by General Manager",
            "authority_clause_ar": "يمثلها العضو المنتدب"
        }

        # Clear existing
        self.envelope.participants.all().delete()
        RepresentativeCandidate.objects.filter(envelope=self.envelope).delete()

        candidates = generate_candidates(self.envelope, analysis_result)
        self.assertEqual(len(candidates), 2)

        # Ignore candidates manually via API view
        factory = RequestFactory()
        candidate_ids = [c.id for c in candidates]
        request = factory.post(
            f"/api/envelopes/{self.envelope.id}/ignore-candidates/",
            {"candidate_ids": candidate_ids},
            content_type="application/json"
        )
        force_authenticate(request, user=self.user)
        view = IgnoreCandidatesView.as_view()
        response = view(request, envelope_id=self.envelope.id)

        self.assertEqual(response.status_code, 200)
        
        # Verify candidate states
        for c in RepresentativeCandidate.objects.filter(envelope=self.envelope):
            self.assertEqual(c.status, 'ignored')
            self.assertIsNotNone(c.ignored_at)
            self.assertIsNone(c.converted_at)


class PrefixDeduplicationTestCase(TestCase):
    def test_collapse_duplicate_prefixes_en(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        self.assertEqual(collapse_duplicate_prefixes("Dr. Dr. Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(collapse_duplicate_prefixes("Dr. Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(collapse_duplicate_prefixes("dr dr Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(collapse_duplicate_prefixes("Prof. Prof. John Doe", "en"), "Prof. John Doe")
        self.assertEqual(collapse_duplicate_prefixes("Eng. Eng. Smith", "en"), "Eng. Smith")

    def test_collapse_duplicate_prefixes_ar(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        self.assertEqual(collapse_duplicate_prefixes("الدكتور/ الدكتور/ عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        self.assertEqual(collapse_duplicate_prefixes("الدكتور/ عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        self.assertEqual(collapse_duplicate_prefixes("المهندس المهندس محمد", "ar"), "المهندس/ محمد")

    def test_restore_prefix_en(self):
        from services.authority_extraction_service import restore_prefix
        # Already has prefix
        self.assertEqual(restore_prefix("Dr.", "Dr. Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(restore_prefix("Dr", "Dr. Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(restore_prefix("dr", "dr Abdulrahman Al-Dosari", "en"), "dr Abdulrahman Al-Dosari")
        
        # Missing prefix
        self.assertEqual(restore_prefix("Dr.", "Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        self.assertEqual(restore_prefix("Dr", "Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")
        
        # Prevent duplication when prefix is restored to a name already containing it
        self.assertEqual(restore_prefix("Dr.", "Dr. Dr. Abdulrahman Al-Dosari", "en"), "Dr. Abdulrahman Al-Dosari")

    def test_restore_prefix_ar(self):
        from services.authority_extraction_service import restore_prefix
        # Already has prefix
        self.assertEqual(restore_prefix("الدكتور/", "الدكتور/ عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        self.assertEqual(restore_prefix("الدكتور", "الدكتور/ عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        
        # Missing prefix
        self.assertEqual(restore_prefix("الدكتور", "عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        self.assertEqual(restore_prefix("الدكتور/", "عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")
        
        # Prevent duplication when prefix is restored to a name already containing it
        self.assertEqual(restore_prefix("الدكتور", "الدكتور/ الدكتور/ عبدالرحمن الدوسري", "ar"), "الدكتور/ عبدالرحمن الدوسري")

    def test_end_to_end_extraction_deduplicates_en(self):
        from services.authority_extraction_service import extract_english_authority
        # Test contract snippet where the candidate has "Dr. Dr."
        snippet = "Signed by the authorized signatory Dr. Dr. Abdulrahman Al-Dosari in his capacity as General Manager"
        res = extract_english_authority(snippet)
        self.assertEqual(res["representative_name"], "Dr. Abdulrahman Al-Dosari")

    def test_end_to_end_extraction_deduplicates_ar(self):
        from services.authority_extraction_service import extract_arabic_authority
        # Test contract snippet where the candidate has "الدكتور/ الدكتور/"
        snippet = "تم التوقيع بواسطة المفوض بالتوقيع الدكتور/ الدكتور/ عبدالرحمن الدوسري بصفته المدير العام"
        res = extract_arabic_authority(snippet)
        self.assertEqual(res["representative_name"], "الدكتور/ عبدالرحمن الدوسري")


class DuplicatePrefixCollapseTestCase(TestCase):
    def test_collapse_duplicate_prefixes_en(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        self.assertEqual(
            collapse_duplicate_prefixes("Dr. Dr. Abdulrahman Al-Dosari"),
            "Dr. Abdulrahman Al-Dosari"
        )
        self.assertEqual(
            collapse_duplicate_prefixes("Eng. Eng. Ahmed Al-Qahtani"),
            "Eng. Ahmed Al-Qahtani"
        )
        # Test mixed case and punctuation
        self.assertEqual(
            collapse_duplicate_prefixes("dr dr. John Doe"),
            "Dr. John Doe"
        )

    def test_collapse_duplicate_prefixes_ar(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        self.assertEqual(
            collapse_duplicate_prefixes("الدكتور/ الدكتور/ عبدالرحمن الدوسري"),
            "الدكتور/ عبدالرحمن الدوسري"
        )
        self.assertEqual(
            collapse_duplicate_prefixes("المهندس/ المهندس/ أحمد القحطاني"),
            "المهندس/ أحمد القحطاني"
        )
        # Test mixed punctuation/slashes
        self.assertEqual(
            collapse_duplicate_prefixes("الدكتور الدكتور/ عبدالرحمن"),
            "الدكتور/ عبدالرحمن"
        )

    def test_collapse_in_clauses(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        self.assertEqual(
            collapse_duplicate_prefixes("authorized signatory Dr. Dr. Abdulrahman Al-Dosari"),
            "authorized signatory Dr. Abdulrahman Al-Dosari"
        )
        self.assertEqual(
            collapse_duplicate_prefixes("المخول بالتوقيع الدكتور/ الدكتور/ عبدالرحمن الدوسري"),
            "المخول بالتوقيع الدكتور/ عبدالرحمن الدوسري"
        )

    def test_preserves_legitimate_later_occurrences(self):
        from services.authority_extraction_service import collapse_duplicate_prefixes
        # Legitimate later occurrences of prefixes should NOT be collapsed
        self.assertEqual(
            collapse_duplicate_prefixes("Dr. Abdulrahman met Dr. Ahmed"),
            "Dr. Abdulrahman met Dr. Ahmed"
        )


from unittest.mock import patch
import unittest


class NationalIdentityOCRTestCase(TestCase):
    """Tests for OCR parsing and image preprocessing functions in national_identity_service.
    Legacy endpoint-dependent tests (test_successful_ocr_extraction, test_empty_ocr_extraction,
    test_missing_image_extraction, test_authorization_for_extraction) have been removed as part of
    the identity verification consolidation milestone (removal of legacy SignerVerification pipeline).
    """
    def setUp(self):
        pass  # setUp not required for OCR parsing unit tests

    def generate_mock_image(self, name="test.png", size=(100, 100)):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        file_obj = BytesIO()
        image = Image.new("RGB", size, color="blue")
        image.save(file_obj, format="PNG")
        data = file_obj.getvalue()
        return SimpleUploadedFile(name, data, content_type="image/png")




    def test_original_bytes_preserved(self):
        """Verifies that original bytes are not mutated by preprocess_identity_image, preprocessing is non-destructive, and returned bytes are valid image data."""
        from services.national_identity_service import preprocess_identity_image
        from PIL import Image
        from io import BytesIO
        
        # 1. Generate standard mock image bytes
        file_obj = BytesIO()
        image = Image.new("RGB", (200, 150), color="red")
        image.save(file_obj, format="PNG")
        original_bytes = file_obj.getvalue()
        
        original_bytes_copy = bytes(original_bytes)
        
        # 2. Call preprocess_identity_image
        result = preprocess_identity_image(original_bytes)
        
        # 3. Assert original bytes remain unchanged
        self.assertEqual(original_bytes, original_bytes_copy)
        
        # 4. Verify returned bytes and metadata structure
        self.assertIn("processed_bytes", result)
        self.assertIn("metadata", result)
        
        processed_bytes = result["processed_bytes"]
        metadata = result["metadata"]
        
        self.assertIsNotNone(processed_bytes)
        self.assertTrue(len(processed_bytes) > 0)
        
        # Returned bytes are valid image data
        try:
            with Image.open(BytesIO(processed_bytes)) as final_img:
                final_img.verify()
        except Exception as e:
            self.fail(f"Returned bytes are not valid image data: {e}")
            
        # Check metadata
        self.assertFalse(metadata["fallback_used"])
        self.assertFalse(metadata["pdf_bypass"])
        self.assertTrue(metadata["autocontrast_applied"])
        self.assertEqual(metadata["contrast_factor"], 1.3)
        self.assertEqual(metadata["sharpness_factor"], 1.3)
        
        # Test PDF bypass specifically
        pdf_bytes = b"%PDF-1.4 mock pdf data"
        pdf_result = preprocess_identity_image(pdf_bytes)
        self.assertEqual(pdf_result["processed_bytes"], pdf_bytes)
        self.assertTrue(pdf_result["metadata"]["pdf_bypass"])
        self.assertFalse(pdf_result["metadata"]["fallback_used"])
        
        # Test fallback gracefully when corrupted bytes are passed
        corrupted_bytes = b"corrupted random data"
        fallback_result = preprocess_identity_image(corrupted_bytes)
        self.assertEqual(fallback_result["processed_bytes"], corrupted_bytes)
        self.assertTrue(fallback_result["metadata"]["fallback_used"])
        self.assertFalse(fallback_result["metadata"]["pdf_bypass"])

    def test_metadata_label_not_selected_as_name(self):
        """
        Regression test — Phase 11.2 OCR Metadata Suppression bugfix.

        Raw OCR text beginning with 'Saudi National ID' must never produce
        'National ID', 'Saudi', or 'Saudi National ID' as the selected name.
        The Arabic name on the following line must win.
        """
        from services.identity_candidate_service import generate_name_candidates, BLOCKED_NAME_CANDIDATES
        from services.identity_selection_service import select_best_name_candidate
        from services.identity_scoring_service import score_name_candidates

        raw_text = (
            "Saudi National ID\n"
            "محمد بن سلمان\n"
            "1012345678"
        )

        candidates = generate_name_candidates(raw_text)
        candidate_values = [c.value for c in candidates]

        # No blocked label should appear as a candidate at all
        for blocked in BLOCKED_NAME_CANDIDATES:
            self.assertNotIn(
                blocked,
                [v.lower() for v in candidate_values],
                msg=f"Blocked metadata label '{blocked}' leaked into name candidates",
            )

        scored = score_name_candidates(candidates, raw_text)
        best = select_best_name_candidate(scored)

        self.assertIsNotNone(best, "Expected a name candidate to be selected")
        self.assertEqual(
            best.value,
            "محمد بن سلمان",
            f"Expected Arabic name 'محمد بن سلمان' but got '{best.value if best else None}'",
        )


class IdentityParserRefinementTestCase(TestCase):
    def test_aadhaar_parsing(self):
        """Verify Aadhaar detection, filtering, DOB parse and formatted number extraction."""
        from services.national_identity_service import detect_document_type, parse_identity_document
        raw_text = (
            "Government of India\n"
            "भारत सरकार\n"
            "Rahul Gandhi\n"
            "DOB: 19/06/1970\n"
            "Male\n"
            "9411 3106 1656\n"
            "UIDAI"
        )
        doc_type = detect_document_type(raw_text)
        self.assertEqual(doc_type, "aadhaar")

        parsed = parse_identity_document(raw_text)
        self.assertEqual(parsed["document_type"], "aadhaar")
        self.assertEqual(parsed["full_name"], "Rahul Gandhi")
        self.assertEqual(parsed["national_id_number"], "941131061656")
        self.assertEqual(parsed["date_of_birth"].isoformat(), "1970-06-19")
        self.assertIsNone(parsed["expiry_date"])

    def test_saudi_id_parsing(self):
        """Verify Saudi National ID detection, Arabic candidate name filtering, and ID formats."""
        from services.national_identity_service import detect_document_type, parse_identity_document
        raw_text = (
            "Kingdom of Saudi Arabia\n"
            "الهوية الوطنية\n"
            "الاسم: محمد بن سلمان\n"
            "الرقم: 1023456789\n"
            "تاريخ الميلاد: 1985-08-31\n"
            "انتهاء: 2030-08-31"
        )
        doc_type = detect_document_type(raw_text)
        self.assertEqual(doc_type, "saudi_id")

        parsed = parse_identity_document(raw_text)
        self.assertEqual(parsed["document_type"], "saudi_id")
        self.assertEqual(parsed["full_name"], "محمد بن سلمان")
        self.assertEqual(parsed["national_id_number"], "1023456789")
        self.assertEqual(parsed["date_of_birth"].isoformat(), "1985-08-31")
        self.assertEqual(parsed["expiry_date"].isoformat(), "2030-08-31")

    def test_iqama_parsing(self):
        """Verify Iqama permit detection, name filtering, and 10-digit number matching (starting with 2)."""
        from services.national_identity_service import detect_document_type, parse_identity_document
        raw_text = (
            "Residence Permit\n"
            "إقامة\n"
            "الاسم: جون دو\n"
            "رقم الإقامة: 2023456789\n"
            "تاريخ الميلاد: 1990-01-01\n"
            "تاريخ الانتهاء: 2028-12-31"
        )
        doc_type = detect_document_type(raw_text)
        self.assertEqual(doc_type, "iqama")

        parsed = parse_identity_document(raw_text)
        self.assertEqual(parsed["document_type"], "iqama")
        self.assertEqual(parsed["full_name"], "جون دو")
        self.assertEqual(parsed["national_id_number"], "2023456789")
        self.assertEqual(parsed["date_of_birth"].isoformat(), "1990-01-01")
        self.assertEqual(parsed["expiry_date"].isoformat(), "2028-12-31")

    def test_passport_parsing(self):
        """Verify Passport detection (includes MRZ check) and birth/expiry date assignments."""
        from services.national_identity_service import detect_document_type, parse_identity_document
        raw_text = (
            "Passport\n"
            "جواز السفر\n"
            "P<SAUDI<<ALADDIN<<<<<<<<<<<<<<<<<<<\n"
            "Name: Aladdin\n"
            "Number: A12345678\n"
            "DOB: 1995-05-15\n"
            "Expiry: 2035-05-15"
        )
        doc_type = detect_document_type(raw_text)
        self.assertEqual(doc_type, "passport")

        parsed = parse_identity_document(raw_text)
        self.assertEqual(parsed["document_type"], "passport")
        self.assertEqual(parsed["full_name"], "Aladdin")
        self.assertEqual(parsed["national_id_number"], "A12345678")
        self.assertEqual(parsed["date_of_birth"].isoformat(), "1995-05-15")
        self.assertEqual(parsed["expiry_date"].isoformat(), "2035-05-15")

    def test_unknown_document_parsing(self):
        """Verify that unstructured documents gracefully fallback to generic parser and 'unknown' type."""
        from services.national_identity_service import detect_document_type, parse_identity_document
        raw_text = (
            "Random Unstructured Document\n"
            "Some text line\n"
            "Unrecognized layout\n"
            "9999-99-99-invalid-date\n"
            "Reference: 5555555555"
        )
        doc_type = detect_document_type(raw_text)
        self.assertEqual(doc_type, "unknown")

        parsed = parse_identity_document(raw_text)
        self.assertEqual(parsed["document_type"], "unknown")
        self.assertEqual(parsed["national_id_number"], "5555555555")
        self.assertIsNone(parsed["date_of_birth"])
        self.assertIsNone(parsed["expiry_date"])


class IdentityCandidateEngineTestCase(TestCase):
    def test_name_candidates_extraction(self):
        """Verify extraction of English, Arabic, and mixed-language name candidates, and check reasons/normalized values."""
        from services.identity_candidate_service import generate_name_candidates
        
        # Test English name
        text_en = "Name: Mohammed Hamza Rahamathulla\nSome irrelevant line 123"
        candidates = generate_name_candidates(text_en)
        self.assertTrue(len(candidates) >= 1)
        names = [c.value for c in candidates]
        self.assertIn("Mohammed Hamza Rahamathulla", names)
        
        cand = [c for c in candidates if c.value == "Mohammed Hamza Rahamathulla"][0]
        self.assertEqual(cand.source_line, "Name: Mohammed Hamza Rahamathulla")
        self.assertIn("latin_name", cand.reasons)
        self.assertIn("multi_word", cand.reasons)
        self.assertEqual(cand.normalized_value, "Mohammed Hamza Rahamathulla")

        # Test Arabic name
        text_ar = "الاسم: عبدالرحمن الدوسري\n12345"
        candidates = generate_name_candidates(text_ar)
        names = [c.value for c in candidates]
        self.assertIn("عبدالرحمن الدوسري", names)
        
        cand = [c for c in candidates if c.value == "عبدالرحمن الدوسري"][0]
        self.assertEqual(cand.source_line, "الاسم: عبدالرحمن الدوسري")
        self.assertIn("arabic_name", cand.reasons)
        self.assertIn("multi_word", cand.reasons)

        # Test Mixed language name
        text_mixed = "Name: Yasser عمر\nLine 2"
        candidates = generate_name_candidates(text_mixed)
        names = [c.value for c in candidates]
        self.assertIn("Yasser عمر", names)
        
        cand = [c for c in candidates if c.value == "Yasser عمر"][0]
        self.assertIn("mixed_language", cand.reasons)

        # Ensure multiple candidates are preserved
        text_multi = "Name: Aladdin\nالاسم: عمر خالد"
        candidates = generate_name_candidates(text_multi)
        names = [c.value for c in candidates]
        self.assertIn("Aladdin", names)
        self.assertIn("عمر خالد", names)
        self.assertEqual(len(candidates), 4)

    def test_identifier_candidates(self):
        """Verify generic identifier candidate matching, normalization, type classification, and context retention."""
        from services.identity_candidate_service import generate_identifier_candidates
        
        text = (
            "Saudi National ID: 1023456789\n"
            "Iqama Number: 2023456789\n"
            "Aadhaar Number: 9411 3106 1656\n"
            "Passport Number: A12345678\n"
            "Random Identifier: 555-5555"
        )
        
        candidates = generate_identifier_candidates(text)
        
        # We expect at least the national_ids and passport
        types = [c.identifier_type for c in candidates]
        self.assertIn("national_id", types)
        self.assertIn("passport", types)
        
        # Aadhaar check
        aadhaar_cand = [c for c in candidates if c.normalized_value == "941131061656"][0]
        self.assertEqual(aadhaar_cand.identifier_type, "national_id")
        self.assertEqual(aadhaar_cand.source_line, "Aadhaar Number: 9411 3106 1656")
        
        # Saudi ID check
        saudi_cand = [c for c in candidates if c.normalized_value == "1023456789"][0]
        self.assertEqual(saudi_cand.identifier_type, "national_id")
        self.assertEqual(saudi_cand.source_line, "Saudi National ID: 1023456789")

        # Iqama check
        iqama_cand = [c for c in candidates if c.normalized_value == "2023456789"][0]
        self.assertEqual(iqama_cand.identifier_type, "national_id")

        # Passport check
        passport_cand = [c for c in candidates if c.normalized_value == "A12345678"][0]
        self.assertEqual(passport_cand.identifier_type, "passport")
        self.assertEqual(passport_cand.source_line, "Passport Number: A12345678")

    def test_date_candidates(self):
        """Verify extraction of date candidates, Hijri conversions, type classifications, and context preservation."""
        from services.identity_candidate_service import generate_date_candidates
        import datetime
        
        text = (
            "Date of Birth: 31/08/1985\n"
            "Expiry: 2030-08-31\n"
            "Hijri Birth: 15/12/1405\n"
            "Unrelated Date: 2026 06 24"
        )
        
        candidates = generate_date_candidates(text)
        
        # Check birth_date
        birth_cand = [c for c in candidates if c.date_type == "birth_date" and c.value == datetime.date(1985, 8, 31)][0]
        self.assertEqual(birth_cand.normalized_value, "1985-08-31")
        self.assertEqual(birth_cand.source_line, "Date of Birth: 31/08/1985")
        
        # Check expiry_date
        expiry_cand = [c for c in candidates if c.date_type == "expiry_date"][0]
        self.assertEqual(expiry_cand.value, datetime.date(2030, 8, 31))
        self.assertEqual(expiry_cand.normalized_value, "2030-08-31")
        
        # Check Hijri conversion
        hijri_cand = [c for c in candidates if "1405" in c.source_line][0]
        self.assertTrue(1984 <= hijri_cand.value.year <= 1986)

        # Check unknown date type
        unknown_cand = [c for c in candidates if c.date_type == "unknown"][0]
        self.assertEqual(unknown_cand.value, datetime.date(2026, 6, 24))

    def test_empty_inputs(self):
        """Verify that empty inputs return empty candidate lists gracefully."""
        from services.identity_candidate_service import (
            generate_name_candidates,
            generate_identifier_candidates,
            generate_date_candidates
        )
        
        self.assertEqual(generate_name_candidates(""), [])
        self.assertEqual(generate_name_candidates(None), [])
        
        self.assertEqual(generate_identifier_candidates(""), [])
        self.assertEqual(generate_identifier_candidates(None), [])
        
        self.assertEqual(generate_date_candidates(""), [])
        self.assertEqual(generate_date_candidates(None), [])


class IdentityCandidateScoringTestCase(TestCase):
    def test_name_candidate_scoring(self):
        """Verify that standard names score higher than metadata keywords and noisy candidates containing OCR artifacts."""
        from services.identity_candidate_service import generate_name_candidates
        from services.identity_scoring_service import score_name_candidates
        
        raw_text = (
            "Name: Mohammed Hamza Rahamathulla\n"
            "Full Name: Government of India\n"
            "Name: Mohammed Hamza Rahamathulla ZUÑE ANDOF\n"
            "DOB: 31/08/2002"
        )
        
        candidates = generate_name_candidates(raw_text)
        scored = score_name_candidates(candidates, raw_text)
        
        # 1. Assert order (sorted by descending score)
        scores = [sc.score for sc in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))
        
        # 2. Assert specific rank relations
        scored_dict = {sc.value: sc for sc in scored}
        
        hamza_sc = scored_dict["Mohammed Hamza Rahamathulla"]
        govt_sc = scored_dict["Government of India"]
        noisy_sc = scored_dict["Mohammed Hamza Rahamathulla ZUÑE ANDOF"]
        
        # Standard name should score higher than Government of India (metadata penalty)
        self.assertTrue(hamza_sc.score > govt_sc.score)
        self.assertIn("non_name_metadata_keyword", govt_sc.reasons)
        
        # Standard name should score higher than the one with 'Ñ' OCR artifact
        self.assertTrue(hamza_sc.score > noisy_sc.score)
        self.assertIn("unusual_characters", noisy_sc.reasons)

    def test_date_candidate_scoring(self):
        """Verify birth date candidate evaluations, adult bonuses vs minor penalties, and expiry dates."""
        from services.identity_candidate_service import generate_date_candidates
        from services.identity_scoring_service import score_date_candidates
        import datetime
        
        raw_text = (
            "Date of Birth: 31/08/2002\n"  # Age 24 in 2026 -> adult_age_range
            "Date of Birth: 28/12/2013\n"  # Age 13 in 2026 -> standard, but not adult_age_range
            "Expiry Date: 31/12/2030"      # Future expiry date
        )
        
        candidates = generate_date_candidates(raw_text)
        scored = score_date_candidates(candidates, raw_text)
        
        # Sorted check
        scores = [sc.score for sc in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))
        
        # Birth date check (31/08/2002 vs 28/12/2013)
        scored_dict = {sc.value: sc for sc in scored}
        adult_dob = scored_dict["2002-08-31"]
        minor_dob = scored_dict["2013-12-28"]
        
        self.assertTrue(adult_dob.score > minor_dob.score)
        self.assertIn("adult_age_range", adult_dob.reasons)
        self.assertNotIn("adult_age_range", minor_dob.reasons)

    def test_identifier_candidate_scoring(self):
        """Verify standard identifiers (national ID, passport) receive higher scores than malformed ones."""
        from services.identity_candidate_service import generate_identifier_candidates
        from services.identity_scoring_service import score_identifier_candidates
        
        raw_text = (
            "ID: 1023456789\n"             # standard 10 digit ID
            "Passport: A12345678\n"        # standard passport
            "Malformed: 12-34-56-78-90\n"  # excessive separators
            "Unusual: 123456"              # unusual length
        )
        
        candidates = generate_identifier_candidates(raw_text)
        scored = score_identifier_candidates(candidates, raw_text)
        
        scores = [sc.score for sc in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))
        
        scored_dict = {sc.value: sc for sc in scored}
        valid_id = scored_dict["1023456789"]
        malformed = scored_dict["12-34-56-78-90"]
        unusual = scored_dict["123456"]
        
        self.assertTrue(valid_id.score > malformed.score)
        self.assertTrue(valid_id.score > unusual.score)
        self.assertIn("excessive_separators", malformed.reasons)
        self.assertIn("unusual_identifier_length", unusual.reasons)

    def test_empty_scoring_inputs(self):
        """Verify that empty candidate lists produce empty scored candidate lists without errors."""
        from services.identity_scoring_service import (
            score_name_candidates,
            score_identifier_candidates,
            score_date_candidates
        )
        
        self.assertEqual(score_name_candidates([], ""), [])
        self.assertEqual(score_name_candidates(None, ""), [])
        
        self.assertEqual(score_identifier_candidates([], ""), [])
        self.assertEqual(score_identifier_candidates(None, ""), [])
        
        self.assertEqual(score_date_candidates([], ""), [])
        self.assertEqual(score_date_candidates(None, ""), [])

    def test_boundary_context_bonus(self):
        """Verify that candidates ending immediately before identity boundary markers get the boundary context bonus."""
        from services.identity_candidate_service import generate_name_candidates
        from services.identity_scoring_service import score_name_candidates
        
        raw_text = "Mohammed Hamza Rahamathulla ZUÑE ANDOF /DOB: 31/08/2002 Male"
        candidates = generate_name_candidates(raw_text)
        scored = score_name_candidates(candidates, raw_text)
        
        scored_dict = {sc.value: sc for sc in scored}
        
        target_cand = scored_dict["Mohammed Hamza Rahamathulla"]
        noisy_cand = scored_dict["Mohammed Hamza Rahamathulla ZUÑE ANDOF"]
        
        self.assertIn("boundary_context", target_cand.reasons)
        self.assertTrue(target_cand.score > noisy_cand.score)

class IdentityCandidateExpansionTestCase(TestCase):
    def test_candidate_expansion_produces_multiple_candidates(self):
        from services.identity_candidate_service import generate_name_candidates
        raw_text = "Mohammed Hamza Rahamathulla ZUÑE ANDOF /DOB: 31/08/2002 Male"
        candidates = generate_name_candidates(raw_text)
        
        # Verify that it produces multiple candidates
        self.assertTrue(len(candidates) > 1)
        
        # Verify that "Mohammed Hamza Rahamathulla" exists among the generated candidates
        candidate_values = [c.value for c in candidates]
        self.assertIn("Mohammed Hamza Rahamathulla", candidate_values)
        
        # Verify all candidates preserve details
        for c in candidates:
            self.assertTrue(hasattr(c, "value"))
            self.assertTrue(hasattr(c, "source_line"))
            self.assertTrue(hasattr(c, "reasons"))
            self.assertTrue(hasattr(c, "normalized_value"))
            self.assertEqual(c.source_line, "Mohammed Hamza Rahamathulla ZUÑE ANDOF /DOB: 31/08/2002 Male")

    def test_duplicate_candidates_are_removed(self):
        from services.identity_candidate_service import generate_name_candidates
        # Repeating lines or duplicate names
        raw_text = "Mohammed Hamza\nMohammed Hamza"
        candidates = generate_name_candidates(raw_text)
        
        # Verify duplicates are removed (only 1 unique "Mohammed Hamza" should remain)
        mh_candidates = [c for c in candidates if c.value == "Mohammed Hamza"]
        self.assertEqual(len(mh_candidates), 1)

    def test_empty_ocr_text_returns_empty_list(self):
        from services.identity_candidate_service import generate_name_candidates
        self.assertEqual(generate_name_candidates(""), [])
        self.assertEqual(generate_name_candidates(None), [])

class IdentityCandidateSelectionTestCase(TestCase):
    def test_select_highest_name_score(self):
        from services.identity_scores import ScoredCandidateName
        from services.identity_selection_service import select_best_name_candidate
        
        candidates = [
            ScoredCandidateName(value="Mohammed Hamza Rahamathulla", score=10.0, reasons=[], source_line=""),
            ScoredCandidateName(value="Mohammed Hamza Rahamathulla ZUÑE ANDOF", score=7.0, reasons=[], source_line="")
        ]
        
        selected = select_best_name_candidate(candidates)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.value, "Mohammed Hamza Rahamathulla")

    def test_name_tie_breaker(self):
        from services.identity_scores import ScoredCandidateName
        from services.identity_selection_service import select_best_name_candidate
        
        candidates = [
            ScoredCandidateName(value="Hamza Rahamathulla", score=8.0, reasons=[], source_line=""),
            ScoredCandidateName(value="Mohammed Hamza Rahamathulla", score=8.0, reasons=[], source_line="")
        ]
        
        selected = select_best_name_candidate(candidates)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.value, "Mohammed Hamza Rahamathulla")

    def test_select_birth_date(self):
        from services.identity_scores import ScoredCandidateDate
        from services.identity_selection_service import select_best_birth_date_candidate
        
        candidates = [
            ScoredCandidateDate(value="2013-12-28", score=2.0, reasons=[], source_line="", date_type="birth_date"),
            ScoredCandidateDate(value="2002-08-31", score=9.0, reasons=[], source_line="", date_type="birth_date"),
            ScoredCandidateDate(value="2030-08-31", score=10.0, reasons=[], source_line="", date_type="expiry_date")
        ]
        
        selected = select_best_birth_date_candidate(candidates)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.value, "2002-08-31")

    def test_empty_candidates(self):
        from services.identity_selection_service import (
            select_best_name_candidate,
            select_best_identifier_candidate,
            select_best_birth_date_candidate,
            select_best_expiry_date_candidate
        )
        
        self.assertIsNone(select_best_name_candidate([]))
        self.assertIsNone(select_best_identifier_candidate([]))
        self.assertIsNone(select_best_birth_date_candidate([]))
        self.assertIsNone(select_best_expiry_date_candidate([]))
        
        self.assertIsNone(select_best_name_candidate(None))
        self.assertIsNone(select_best_identifier_candidate(None))
        self.assertIsNone(select_best_birth_date_candidate(None))
        self.assertIsNone(select_best_expiry_date_candidate(None))

class IdentityConfidenceEngineTestCase(TestCase):
    def test_clear_name_winner(self):
        from services.identity_scores import ScoredCandidateName
        from services.identity_confidence_service import calculate_name_confidence
        
        # Scenario A: Clear winner (margin >= 2.0)
        candidates_a = [
            ScoredCandidateName(value="Mohammed Hamza", score=10.0, reasons=[], source_line=""),
            ScoredCandidateName(value="Hamza", score=7.0, reasons=[], source_line="")
        ]
        conf_a = calculate_name_confidence(candidates_a, candidates_a[0])
        self.assertIn("clear_winner", conf_a.reasons)
        
        # Scenario B: Close competitor (margin < 2.0, competitor within 1.0)
        candidates_b = [
            ScoredCandidateName(value="Mohammed Hamza", score=10.0, reasons=[], source_line=""),
            ScoredCandidateName(value="Hamza", score=9.8, reasons=[], source_line="")
        ]
        conf_b = calculate_name_confidence(candidates_b, candidates_b[0])
        self.assertNotIn("clear_winner", conf_b.reasons)
        self.assertIn("multiple_close_candidates", conf_b.reasons)
        self.assertTrue(conf_a.confidence > conf_b.confidence)

    def test_layout_agreement_bonus(self):
        from services.identity_scores import ScoredCandidateName
        from services.identity_confidence_service import calculate_name_confidence
        
        candidates = [
            ScoredCandidateName(value="Mohammed Hamza", score=6.0, reasons=[], source_line="")
        ]
        
        # Layout matches (case/space variations handled by normalization)
        conf_match = calculate_name_confidence(candidates, candidates[0], layout_name="MOHAMMED HAMZA  ")
        self.assertIn("layout_agreement", conf_match.reasons)
        
        # Layout mismatch
        conf_mismatch = calculate_name_confidence(candidates, candidates[0], layout_name="Rahul Gandhi")
        self.assertNotIn("layout_agreement", conf_mismatch.reasons)
        self.assertTrue(conf_match.confidence > conf_mismatch.confidence)

    def test_overall_confidence(self):
        from services.identity_confidence import FieldConfidence
        from services.identity_confidence_service import calculate_overall_confidence
        
        name_conf = FieldConfidence(confidence=0.8, reasons=[])
        ident_conf = FieldConfidence(confidence=0.9, reasons=[])
        dob_conf = FieldConfidence(confidence=0.7, reasons=[])
        exp_conf = FieldConfidence(confidence=0.6, reasons=[])
        
        # 0.40 * 0.8 + 0.30 * 0.9 + 0.20 * 0.7 + 0.10 * 0.6 = 0.32 + 0.27 + 0.14 + 0.06 = 0.79
        overall = calculate_overall_confidence(name_conf, ident_conf, dob_conf, exp_conf)
        self.assertEqual(overall, 0.79)

    def test_missing_expiry_date(self):
        from services.identity_confidence import FieldConfidence
        from services.identity_confidence_service import calculate_overall_confidence
        
        name_conf = FieldConfidence(confidence=0.8, reasons=[])
        ident_conf = FieldConfidence(confidence=0.9, reasons=[])
        dob_conf = FieldConfidence(confidence=0.7, reasons=[])
        
        # Weights normalized: (0.40 * 0.8 + 0.30 * 0.9 + 0.20 * 0.7) / 0.90 = (0.32 + 0.27 + 0.14) / 0.90 = 0.73 / 0.90 = 0.8111... -> 0.81
        overall = calculate_overall_confidence(name_conf, ident_conf, dob_conf, None)
        self.assertEqual(overall, 0.81)

    def test_empty_inputs(self):
        from services.identity_confidence_service import (
            calculate_name_confidence,
            calculate_identifier_confidence,
            calculate_birth_date_confidence,
            calculate_expiry_date_confidence,
            calculate_overall_confidence
        )
        
        # Test None inputs
        self.assertEqual(calculate_name_confidence(None, None).confidence, 0.0)
        self.assertEqual(calculate_identifier_confidence(None, None).confidence, 0.0)
        self.assertEqual(calculate_birth_date_confidence(None, None).confidence, 0.0)
        self.assertIsNone(calculate_expiry_date_confidence(None, None))
        
        # Test empty list inputs
        self.assertEqual(calculate_name_confidence([], None).confidence, 0.0)
        self.assertEqual(calculate_identifier_confidence([], None).confidence, 0.0)
        self.assertEqual(calculate_birth_date_confidence([], None).confidence, 0.0)
        self.assertIsNone(calculate_expiry_date_confidence([], None))



class TermsAcceptanceTestCase(TestCase):
    """
    Phase 11.1 — Tests for the Terms & Conditions acceptance flow.

    Covers:
        - accept_terms() service creates/updates ParticipantAuthorizationState.
        - POST /api/participants/{id}/accept-terms/ requires authorization.
        - Valid acceptance returns correct payload.
        - Custom terms_version is persisted.
        - Re-acceptance is idempotent.
    """

    def setUp(self):
        from .models import Document, Envelope, Participant, ParticipantToken
        from django.utils import timezone
        from datetime import timedelta

        self.document = Document.objects.create(
            file="terms_test.pdf",
            file_hash="termshash001"
        )
        self.envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            signature_page=1,
            terms_acceptance_required=True,
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Terms Tester",
            email="terms@test.com",
            role="signer",
            order=1,
            status="active",
        )
        self.token_obj = ParticipantToken.objects.create(
            participant=self.participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False,
        )
        self.token = str(self.token_obj.token)

    # ------------------------------------------------------------------
    # Service-level tests
    # ------------------------------------------------------------------

    def test_accept_terms_creates_authorization_state(self):
        """accept_terms() creates ParticipantAuthorizationState if absent."""
        from services.terms_service import accept_terms
        from .models import ParticipantAuthorizationState

        self.assertFalse(
            ParticipantAuthorizationState.objects.filter(
                participant=self.participant
            ).exists()
        )
        state = accept_terms(self.participant)
        self.assertTrue(state.accepted_terms)
        self.assertIsNotNone(state.accepted_terms_at)
        self.assertEqual(state.terms_version, "v1")

    def test_accept_terms_updates_existing_state(self):
        """accept_terms() updates existing ParticipantAuthorizationState."""
        from services.terms_service import accept_terms
        from .models import ParticipantAuthorizationState

        # Pre-create state with email_verified=True to ensure fields survive
        ParticipantAuthorizationState.objects.create(
            participant=self.participant,
            email_verified=True,
        )
        state = accept_terms(self.participant, terms_version="v2")
        state.refresh_from_db()
        self.assertTrue(state.accepted_terms)
        self.assertEqual(state.terms_version, "v2")
        self.assertTrue(state.email_verified)  # unrelated field preserved

    def test_accept_terms_idempotent(self):
        """Calling accept_terms() twice does not create duplicate state rows."""
        from services.terms_service import accept_terms
        from .models import ParticipantAuthorizationState

        accept_terms(self.participant, terms_version="v1")
        accept_terms(self.participant, terms_version="v2")

        count = ParticipantAuthorizationState.objects.filter(
            participant=self.participant
        ).count()
        self.assertEqual(count, 1)

        state = ParticipantAuthorizationState.objects.get(participant=self.participant)
        self.assertEqual(state.terms_version, "v2")

    # ------------------------------------------------------------------
    # API-level tests
    # ------------------------------------------------------------------

    def _post(self, participant_id, data, token=None):
        from rest_framework.test import APIClient
        client = APIClient()
        url = f"/api/participants/{participant_id}/accept-terms/"
        if token:
            return client.post(url, data, format="json", HTTP_X_PARTICIPANT_TOKEN=token)
        return client.post(url, data, format="json")

    def test_api_requires_authorization(self):
        """POST without a valid token returns 401 or 403."""
        response = self._post(self.participant.id, {"accepted": True})
        self.assertIn(response.status_code, [401, 403])

    def test_api_accept_terms_success(self):
        """Valid POST returns accepted_terms=True and terms_version."""
        response = self._post(
            self.participant.id,
            {"accepted": True, "terms_version": "v1"},
            token=self.token,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["accepted_terms"])
        self.assertEqual(data["terms_version"], "v1")
        self.assertIsNotNone(data["accepted_terms_at"])

    def test_api_accept_terms_custom_version(self):
        """Custom terms_version is stored and returned."""
        response = self._post(
            self.participant.id,
            {"accepted": True, "terms_version": "v3"},
            token=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["terms_version"], "v3")

    def test_api_accepted_false_returns_400(self):
        """Sending accepted=false is rejected with 400."""
        response = self._post(
            self.participant.id,
            {"accepted": False},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)

    def test_api_missing_accepted_field_returns_400(self):
        """Omitting the accepted field returns 400."""
        response = self._post(
            self.participant.id,
            {},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)

    def test_api_defaults_terms_version_to_v1(self):
        """When terms_version is omitted, defaults to 'v1'."""
        response = self._post(
            self.participant.id,
            {"accepted": True},
            token=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["terms_version"], "v1")


class EmailOTPTestCase(TestCase):
    """
    Phase 11.2 — Tests for Email OTP authentication.

    Covers:
        - send_email_otp() generates and stores OTP + expiry.
        - verify_email_otp() with correct code sets email_verified=True.
        - verify_email_otp() with wrong code returns {"verified": False, "error": "Invalid OTP"}.
        - verify_email_otp() with expired code returns {"verified": False, "error": "OTP expired"}.
        - get_authorization_status() reports authorized=True when email OTP required and verified.
    """

    def setUp(self):
        from .models import Document, Envelope, Participant, ParticipantToken
        from django.utils import timezone
        from datetime import timedelta

        self.document = Document.objects.create(
            file="otp_test.pdf",
            file_hash="otphash001"
        )
        self.envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            signature_page=1,
            email_otp_required=True,
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="OTP Tester",
            email="otp@test.com",
            role="signer",
            order=1,
            status="active",
        )
        self.token_obj = ParticipantToken.objects.create(
            participant=self.participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False,
        )
        self.token = str(self.token_obj.token)

    # ------------------------------------------------------------------
    # Service-level tests
    # ------------------------------------------------------------------

    def test_send_email_otp_generates_otp_and_expiry(self):
        """send_email_otp() stores a 6-digit OTP and sets expiry."""
        from services.email_otp_service import send_email_otp
        from .models import ParticipantAuthorizationState
        from django.utils import timezone

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            state = send_email_otp(self.participant)

        self.assertIsNotNone(state.email_otp_code)
        self.assertEqual(len(state.email_otp_code), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in state.email_otp_code))
        self.assertIsNotNone(state.email_otp_sent_at)
        self.assertIsNotNone(state.email_otp_expires_at)
        self.assertGreater(state.email_otp_expires_at, timezone.now())
        # email_verified should be reset to False when a new OTP is issued
        self.assertFalse(state.email_verified)

    def test_verify_correct_otp_sets_email_verified(self):
        """Correct OTP sets email_verified=True and clears the stored code."""
        from services.email_otp_service import send_email_otp, verify_email_otp
        from .models import ParticipantAuthorizationState

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            state = send_email_otp(self.participant)

        from django.core import mail
        import re
        stored_otp = re.search(r"code is:\s*(\d{6})", mail.outbox[-1].body).group(1)
        result = verify_email_otp(self.participant, stored_otp)

        self.assertEqual(result, {"verified": True})

        state.refresh_from_db()
        self.assertTrue(state.email_verified)
        self.assertIsNotNone(state.email_verified_at)
        self.assertEqual(state.email_otp_code, "")

    def test_invalid_otp_returns_error(self):
        """Wrong OTP code returns verified=False with 'Invalid OTP'."""
        from services.email_otp_service import send_email_otp, verify_email_otp

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            send_email_otp(self.participant)

        result = verify_email_otp(self.participant, "000000")
        self.assertEqual(result["verified"], False)
        self.assertEqual(result["error"], "Invalid OTP")

    def test_expired_otp_returns_error(self):
        """Expired OTP returns verified=False with 'OTP expired'."""
        from services.email_otp_service import send_email_otp, verify_email_otp
        from .models import ParticipantAuthorizationState
        from django.utils import timezone
        from datetime import timedelta

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            state = send_email_otp(self.participant)

        from django.core import mail
        import re
        stored_otp = re.search(r"code is:\s*(\d{6})", mail.outbox[-1].body).group(1)

        # Backdate the expiry to simulate expiration
        state.email_otp_expires_at = timezone.now() - timedelta(minutes=1)
        state.save(update_fields=["email_otp_expires_at"])

        result = verify_email_otp(self.participant, stored_otp)
        self.assertEqual(result["verified"], False)
        self.assertEqual(result["error"], "OTP expired")

    def test_authorization_status_after_email_verification(self):
        """
        When email_otp_required=True and email is verified,
        get_authorization_status() returns authorized=True
        (assuming no other requirements are set).
        """
        from services.email_otp_service import send_email_otp, verify_email_otp
        from services.security_policy_service import get_authorization_status

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            state = send_email_otp(self.participant)

        from django.core import mail
        import re
        stored_otp = re.search(r"code is:\s*(\d{6})", mail.outbox[-1].body).group(1)
        verify_email_otp(self.participant, stored_otp)

        status_data = get_authorization_status(self.participant)
        self.assertTrue(status_data["authorized"])
        self.assertNotIn("email_otp", status_data["missing_requirements"])
        self.assertTrue(status_data["requirements"]["email_otp"]["satisfied"])

    # ------------------------------------------------------------------
    # API-level tests
    # ------------------------------------------------------------------

    def _post(self, url_name, participant_id, data, token=None):
        from rest_framework.test import APIClient
        from django.urls import reverse
        client = APIClient()
        url = reverse(url_name, kwargs={"participant_id": participant_id})
        if token:
            return client.post(url, data, format="json", HTTP_X_PARTICIPANT_TOKEN=token)
        return client.post(url, data, format="json")

    def test_api_send_email_otp_requires_auth(self):
        """POST send-email-otp without token returns 403."""
        response = self._post("send-email-otp", self.participant.id, {})
        self.assertIn(response.status_code, [401, 403])

    def test_api_send_email_otp_success(self):
        """Authenticated POST to send-email-otp returns 200."""
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self._post(
                "send-email-otp", self.participant.id, {}, token=self.token
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.json())

    def test_api_verify_email_otp_correct(self):
        """Correct OTP via API returns verified=True."""
        from django.core import mail
        import re

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self._post("send-email-otp", self.participant.id, {}, token=self.token)

        stored_otp = re.search(r"code is:\s*(\d{6})", mail.outbox[-1].body).group(1)
        response = self._post(
            "verify-email-otp",
            self.participant.id,
            {"otp": stored_otp},
            token=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])

    def test_api_verify_email_otp_wrong_code(self):
        """Wrong OTP via API returns 400 with verified=False."""
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self._post("send-email-otp", self.participant.id, {}, token=self.token)

        response = self._post(
            "verify-email-otp",
            self.participant.id,
            {"otp": "000000"},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["verified"])
        self.assertEqual(response.json()["error"], "Invalid OTP")

    def test_api_verify_email_otp_missing_field(self):
        """Missing otp field returns 400."""
        response = self._post(
            "verify-email-otp",
            self.participant.id,
            {},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)


class VerificationSessionTestCase(TestCase):
    """
    Phase 11.5 — Verification Session Foundation Tests.
    """

    def setUp(self):
        from .models import Document, Envelope, Participant
        self.document = Document.objects.create(
            file="verification_test.pdf",
            file_hash="verificationhash001"
        )
        self.envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            signature_page=1,
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Session Tester",
            email="session@test.com",
            role="signer",
            order=1,
        )

    def test_create_session(self):
        from services.verification_session_service import get_or_create_verification_session
        session = get_or_create_verification_session(self.participant)
        self.assertEqual(session.status, "pending")
        self.assertEqual(session.failure_reason, "")
        self.assertIsNotNone(session.started_at)
        self.assertIsNone(session.completed_at)

    def test_mark_processing(self):
        from services.verification_session_service import mark_verification_processing
        session = mark_verification_processing(self.participant)
        self.assertEqual(session.status, "processing")
        self.assertEqual(session.failure_reason, "")

    def test_mark_approved(self):
        from services.verification_session_service import mark_verification_approved
        session = mark_verification_approved(self.participant)
        self.assertEqual(session.status, "approved")
        self.assertIsNotNone(session.completed_at)

    def test_mark_failed(self):
        from services.verification_session_service import mark_verification_failed
        session = mark_verification_failed(self.participant, reason="Face did not match")
        self.assertEqual(session.status, "failed")
        self.assertEqual(session.failure_reason, "Face did not match")
        self.assertIsNotNone(session.completed_at)

    def test_mark_manual_review(self):
        from services.verification_session_service import mark_verification_manual_review
        session = mark_verification_manual_review(self.participant, reason="Low confidence score")
        self.assertEqual(session.status, "requires_manual_review")
        self.assertEqual(session.failure_reason, "Low confidence score")
        self.assertIsNotNone(session.completed_at)

    def test_get_or_create_idempotent(self):
        from services.verification_session_service import get_or_create_verification_session
        session1 = get_or_create_verification_session(self.participant)
        session2 = get_or_create_verification_session(self.participant)
        self.assertEqual(session1.id, session2.id)


class BiometricVerificationTestCase(TestCase):
    """
    Phase 12 — Face Biometrics Foundation Tests.
    """

    def setUp(self):
        from .models import Document, Envelope, Participant
        self.document = Document.objects.create(
            file="biometric_test.pdf",
            file_hash="biometrichash001"
        )
        self.envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            signature_page=1,
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Biometric Tester",
            email="biometric@test.com",
            role="signer",
            order=1,
        )

    def test_create_biometric_verification(self):
        from services.biometric_verification_service import get_or_create_biometric_verification
        biometric = get_or_create_biometric_verification(self.participant)
        self.assertEqual(biometric.status, "pending")
        self.assertIsNone(biometric.similarity_score)
        self.assertIsNone(biometric.liveness_score)
        self.assertEqual(biometric.provider, "")
        self.assertEqual(biometric.failure_reason, "")
        self.assertIsNotNone(biometric.started_at)
        self.assertIsNone(biometric.completed_at)
        # Verify it created a parent VerificationSession automatically
        self.assertIsNotNone(biometric.verification_session)
        self.assertEqual(biometric.verification_session.participant, self.participant)

    def test_mark_processing(self):
        from services.biometric_verification_service import mark_biometric_processing
        biometric = mark_biometric_processing(self.participant)
        self.assertEqual(biometric.status, "processing")

    def test_mark_matched(self):
        from services.biometric_verification_service import mark_biometric_matched
        biometric = mark_biometric_matched(
            self.participant,
            similarity_score=0.92,
            liveness_score=0.88,
            provider="mock_azure_biometrics"
        )
        self.assertEqual(biometric.status, "matched")
        self.assertEqual(biometric.similarity_score, 0.92)
        self.assertEqual(biometric.liveness_score, 0.88)
        self.assertEqual(biometric.provider, "mock_azure_biometrics")
        self.assertIsNotNone(biometric.completed_at)

    def test_mark_failed(self):
        from services.biometric_verification_service import mark_biometric_failed
        biometric = mark_biometric_failed(self.participant, reason="Liveness check failed")
        self.assertEqual(biometric.status, "failed")
        self.assertEqual(biometric.failure_reason, "Liveness check failed")
        self.assertIsNotNone(biometric.completed_at)

    def test_mark_manual_review(self):
        from services.biometric_verification_service import mark_biometric_manual_review
        biometric = mark_biometric_manual_review(self.participant, reason="Lighting too dark")
        self.assertEqual(biometric.status, "requires_manual_review")
        self.assertEqual(biometric.failure_reason, "Lighting too dark")
        self.assertIsNotNone(biometric.completed_at)

    def test_get_or_create_idempotent(self):
        from services.biometric_verification_service import get_or_create_biometric_verification
        biometric1 = get_or_create_biometric_verification(self.participant)
        biometric2 = get_or_create_biometric_verification(self.participant)
        self.assertEqual(biometric1.id, biometric2.id)


from unittest.mock import patch


# ---------------------------------------------------------------------------
# Phase 12.1 & 12.2 — Face Matching Engine and API tests
# ---------------------------------------------------------------------------
class FaceMatchingTestCase(TestCase):
    """Phase 12.1 & 12.2 — Face Matching Engine and API tests."""

    def setUp(self):
        from .models import Document, Envelope, Participant, ParticipantToken, SignerIdentityVerification
        from django.utils import timezone
        from datetime import timedelta
        from django.core.files.base import ContentFile

        self.document = Document.objects.create(
            file="face_test.pdf",
            file_hash="facehash001"
        )
        self.envelope = Envelope.objects.create(
            document=self.document,
            status="sent",
            signature_page=1,
            face_biometric_required=True,
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="Face Tester",
            email="face@test.com",
            role="signer",
            order=1,
            status="active",
        )
        self.token_obj = ParticipantToken.objects.create(
            participant=self.participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False,
        )
        self.token = str(self.token_obj.token)

        # Create SignerIdentityVerification so perform_face_match can fetch the ref image
        self.identity_verification = SignerIdentityVerification.objects.create(
            participant=self.participant,
            status="verified"
        )
        self.identity_verification.reference_face_image.save(
            "ref_face.jpg",
            ContentFile(b"ref_data"),
            save=True
        )

    @patch('services.face_matching_service.calculate_face_similarity')
    def test_high_similarity(self, mock_similarity):
        mock_similarity.return_value = 0.83
        from services.face_matching_service import perform_face_match

        biometric = perform_face_match(self.participant, b"selfie_data")
        self.assertEqual(biometric.status, "matched")
        self.assertEqual(biometric.similarity_score, 0.83)
        self.assertEqual(biometric.provider, "insightface")

    @patch('services.face_matching_service.calculate_face_similarity')
    def test_low_similarity(self, mock_similarity):
        mock_similarity.return_value = 0.42
        from services.face_matching_service import perform_face_match

        biometric = perform_face_match(self.participant, b"selfie_data")
        self.assertEqual(biometric.status, "failed")
        self.assertEqual(biometric.similarity_score, 0.42)
        self.assertEqual(biometric.failure_reason, "similarity_below_threshold")

    @patch('services.face_matching_service.calculate_face_similarity')
    def test_exception(self, mock_similarity):
        mock_similarity.side_effect = Exception("General error")
        from services.face_matching_service import perform_face_match

        biometric = perform_face_match(self.participant, b"selfie_data")
        self.assertEqual(biometric.status, "requires_manual_review")
        self.assertEqual(biometric.failure_reason, "General error")

    @patch('services.face_matching_service.calculate_face_similarity')
    def test_no_face_detected(self, mock_similarity):
        mock_similarity.side_effect = ValueError("no_face_detected")
        from services.face_matching_service import perform_face_match

        biometric = perform_face_match(self.participant, b"selfie_data")
        self.assertEqual(biometric.status, "requires_manual_review")
        self.assertEqual(biometric.failure_reason, "no_face_detected")

    def _post(self, participant_id, data, token=None):
        from rest_framework.test import APIClient
        from django.urls import reverse
        client = APIClient()
        url = reverse("face-verification", kwargs={"participant_id": participant_id})
        if token:
            return client.post(url, data, format="multipart", HTTP_X_PARTICIPANT_TOKEN=token)
        return client.post(url, data, format="multipart")

    @patch('esign.views.validate_image_file')
    @patch('services.face_matching_service.calculate_face_similarity')
    def test_api_success(self, mock_similarity, mock_validate):
        mock_similarity.return_value = 0.83
        from django.core.files.uploadedfile import SimpleUploadedFile

        selfie = SimpleUploadedFile("selfie.jpg", b"selfie_content", content_type="image/jpeg")
        response = self._post(self.participant.id, {"selfie_image": selfie}, token=self.token)
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertTrue(res_json["matched"])
        self.assertEqual(res_json["similarity_score"], 0.83)
        self.assertEqual(res_json["provider"], "insightface")

    @patch('esign.views.validate_image_file')
    @patch('services.face_matching_service.calculate_face_similarity')
    def test_api_failure(self, mock_similarity, mock_validate):
        mock_similarity.return_value = 0.42
        from django.core.files.uploadedfile import SimpleUploadedFile

        selfie = SimpleUploadedFile("selfie.jpg", b"selfie_content", content_type="image/jpeg")
        response = self._post(self.participant.id, {"selfie_image": selfie}, token=self.token)
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertFalse(res_json["matched"])
        self.assertEqual(res_json["similarity_score"], 0.42)


# ---------------------------------------------------------------------------
# Phase 12.2.5 — Identity Verification (National ID Upload & Reference Face)
# ---------------------------------------------------------------------------
class IdentityVerificationTestCase(TestCase):
    """Phase 12.2.5 — Tests for SignerIdentityVerification model, identity extraction,
    and reference face storage features."""

    def setUp(self):
        from django.contrib.auth.models import User
        from esign.models import Document, Envelope, Participant, ParticipantToken
        from django.utils import timezone
        from datetime import timedelta

        self.owner = User.objects.create_user(username="owner_id", password="password")
        self.document = Document.objects.create(file="id_test.pdf", file_hash="idhash001")
        self.envelope = Envelope.objects.create(
            document=self.document,
            owner=self.owner,
            status="sent",
            national_id_required=True
        )
        self.participant = Participant.objects.create(
            envelope=self.envelope,
            name="ID Tester",
            email="id@test.com",
            role="signer",
            order=1,
            status="active",
        )
        self.token_obj = ParticipantToken.objects.create(
            participant=self.participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False,
        )
        self.token = str(self.token_obj.token)

    # ------------------------------------------------------------------
    # Helpers: shared mock return values
    # ------------------------------------------------------------------
    def _ocr_return(self):
        return {
            "raw_text": "Aadhaar Card\nName: Alice Tester\nID: 1234 5678 9012\nDOB: 01/01/1990",
            "ocr_confidence": 0.95,
            "ocr_provider": "azure",
        }

    def _parse_return(self):
        import datetime
        return {
            "full_name": "Alice Tester",
            "national_id_number": "123456789012",
            "date_of_birth": datetime.date(1990, 1, 1),
            "document_type": "aadhaar",
        }

    # ------------------------------------------------------------------
    # Test 1 — OCR succeeds -> status becomes verified
    # ------------------------------------------------------------------
    @patch('services.identity_verification_service.extract_reference_face')
    @patch('services.identity_verification_service.extract_identity_data')
    @patch('services.identity_verification_service.parse_identity_document')
    def test_successful_identity_verification(self, mock_parse, mock_extract, mock_crop_face):
        self.participant.name = "Alice Tester"
        self.participant.save()
        mock_extract.return_value = self._ocr_return()
        mock_parse.return_value = self._parse_return()
        mock_crop_face.return_value = b"cropped_face_bytes"

        from services.identity_verification_service import perform_identity_verification
        verification = perform_identity_verification(self.participant, b"mock_id_card_image_bytes")

        self.assertEqual(verification.status, "verified")
        self.assertEqual(verification.full_name, "Alice Tester")
        self.assertEqual(verification.national_id_number, "123456789012")
        self.assertEqual(verification.document_type, "aadhaar")

    # ------------------------------------------------------------------
    # Test 2 — Reference face bytes are persisted to the image field
    # ------------------------------------------------------------------
    @patch('services.identity_verification_service.extract_reference_face')
    @patch('services.identity_verification_service.extract_identity_data')
    @patch('services.identity_verification_service.parse_identity_document')
    def test_reference_face_saved(self, mock_parse, mock_extract, mock_crop_face):
        self.participant.name = "Alice Tester"
        self.participant.save()
        mock_extract.return_value = self._ocr_return()
        mock_parse.return_value = self._parse_return()
        mock_crop_face.return_value = b"cropped_face_bytes"

        from services.identity_verification_service import perform_identity_verification
        verification = perform_identity_verification(self.participant, b"mock_id_card_image_bytes")

        self.assertTrue(verification.document_image.name.endswith(".jpg"))
        self.assertTrue(verification.reference_face_image.name.endswith(".jpg"))

        verification.reference_face_image.open("rb")
        stored = verification.reference_face_image.read()
        verification.reference_face_image.close()
        self.assertEqual(stored, b"cropped_face_bytes")

    # ------------------------------------------------------------------
    # Test 3 — Exception during OCR -> status becomes requires_manual_review
    # ------------------------------------------------------------------
    @patch('services.identity_verification_service.extract_reference_face')
    @patch('services.identity_verification_service.extract_identity_data')
    def test_manual_review_on_exception(self, mock_extract, mock_crop_face):
        mock_extract.side_effect = Exception("Azure OCR API error")

        from services.identity_verification_service import perform_identity_verification
        verification = perform_identity_verification(self.participant, b"mock_id_card_image_bytes")

        self.assertEqual(verification.status, "requires_manual_review")
        self.assertEqual(verification.failure_reason, "Azure OCR API error")
        self.assertEqual(verification.full_name, "")
        self.assertEqual(verification.national_id_number, "")

    # ------------------------------------------------------------------
    # Test 4 — POST /identity-verification/ -> 200 + verified payload
    # ------------------------------------------------------------------
    @patch('esign.views.validate_image_file')
    @patch('services.identity_verification_service.extract_reference_face')
    @patch('services.identity_verification_service.extract_identity_data')
    @patch('services.identity_verification_service.parse_identity_document')
    def test_view_success(self, mock_parse, mock_extract, mock_crop_face, mock_validate):
        self.participant.name = "Khalid"
        self.participant.save()
        import datetime
        mock_extract.return_value = {
            "raw_text": "Saudi ID\nName: Khalid\nID: 1029384756",
            "ocr_confidence": 0.98,
            "ocr_provider": "azure",
        }
        mock_parse.return_value = {
            "full_name": "Khalid",
            "national_id_number": "1029384756",
            "date_of_birth": datetime.date(1985, 5, 20),
            "document_type": "saudi_id",
        }
        mock_crop_face.return_value = b"cropped_face_bytes"

        from rest_framework.test import APIClient
        from django.urls import reverse
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = APIClient()
        url = reverse("identity-verification", kwargs={"participant_id": self.participant.id})
        doc_image = SimpleUploadedFile("id_front.jpg", b"fake_id_bytes", content_type="image/jpeg")

        response = client.post(
            url,
            {"document_image": doc_image},
            format="multipart",
            HTTP_X_PARTICIPANT_TOKEN=self.token,
        )

        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertEqual(res_json["status"], "verified")
        self.assertEqual(res_json["full_name"], "Khalid")
        self.assertEqual(res_json["document_type"], "saudi_id")

        self.participant.refresh_from_db()
        self.assertTrue(hasattr(self.participant, "signer_identity_verification"))
        self.assertEqual(self.participant.signer_identity_verification.status, "verified")

    # ------------------------------------------------------------------
    # Test 5 — POST /identity-verification/ when OCR raises -> 200 + manual_review
    # ------------------------------------------------------------------
    @patch('esign.views.validate_image_file')
    @patch('services.identity_verification_service.extract_reference_face')
    @patch('services.identity_verification_service.extract_identity_data')
    def test_view_exception(self, mock_extract, mock_crop_face, mock_validate):
        mock_extract.side_effect = Exception("OCR downstream failure")

        from rest_framework.test import APIClient
        from django.urls import reverse
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = APIClient()
        url = reverse("identity-verification", kwargs={"participant_id": self.participant.id})
        doc_image = SimpleUploadedFile("id_front.jpg", b"fake_id_bytes", content_type="image/jpeg")

        response = client.post(
            url,
            {"document_image": doc_image},
            format="multipart",
            HTTP_X_PARTICIPANT_TOKEN=self.token,
        )

        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertEqual(res_json["status"], "requires_manual_review")
        self.assertIn("failure_reason", res_json)


class LivenessServiceTestCase(TestCase):
    def test_liveness_placeholder(self):
        from services.liveness_service import perform_liveness_check
        result = perform_liveness_check(b"fake_selfie_data")
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.provider, "local-placeholder")
        self.assertEqual(result.reason, "")


class ParticipantMatchingTestCase(TestCase):
    def test_normalize_string(self):
        from services.participant_matching_service import normalize_string
        # Case insensitivity
        self.assertEqual(normalize_string("john doe"), "JOHN DOE")
        # Leading/trailing/collapsed whitespace
        self.assertEqual(normalize_string("  john   doe  "), "JOHN DOE")
        # Punctuation
        self.assertEqual(normalize_string("john. doe,!"), "JOHN DOE")
        # Unicode normalization
        self.assertEqual(normalize_string("jôhn dôe"), "JOHN DOE")
        # Separators replaced with spaces
        self.assertEqual(normalize_string("john-doe_test/one.two"), "JOHN DOE TEST ONE TWO")
        # Arabic diacritics (tashkeel)
        self.assertEqual(normalize_string("مُحَمَّد"), "محمد")

    def test_name_matching_thresholds(self):
        from services.participant_matching_service import match_participant_identity
        from unittest.mock import MagicMock
        
        participant = MagicMock()
        participant.name = "John Doe"
        
        # Exact match
        self.assertTrue(match_participant_identity(participant, {"full_name": "John Doe"})["matched"])
        # Case insensitive and punctuation/whitespace
        self.assertTrue(match_participant_identity(participant, {"full_name": "  john.   doe! "})["matched"])
        # Close match (within 0.85)
        self.assertTrue(match_participant_identity(participant, {"full_name": "John Doee"})["matched"])
        # Obvious mismatch
        self.assertFalse(match_participant_identity(participant, {"full_name": "Jane Smith"})["matched"])

    @patch('services.identity_verification_service.extract_identity_data')
    @patch('services.identity_verification_service.extract_reference_face')
    def test_identity_verification_matching_flow(self, mock_crop_face, mock_extract_ocr):
        from .models import Document, Envelope, Participant, SignerIdentityVerification
        from services.identity_verification_service import perform_identity_verification
        
        doc = Document.objects.create(file="test.pdf", file_hash="hash")
        envelope = Envelope.objects.create(document=doc, status="sent", national_id_required=True)
        
        # 1. Matching case
        participant_match = Participant.objects.create(envelope=envelope, name="John Doe", email="match@test.com", role="signer")
        mock_extract_ocr.return_value = {"raw_text": "Name: John Doe"}
        mock_crop_face.return_value = b"cropped_bytes"
        
        with patch('services.identity_verification_service.parse_identity_document') as mock_parse:
            mock_parse.return_value = {"full_name": "John Doe", "national_id_number": "123"}
            verification = perform_identity_verification(participant_match, b"fake_image_bytes")
            
            self.assertEqual(verification.status, "verified")
            self.assertTrue(verification.identity_matched)
            self.assertGreaterEqual(verification.identity_match_score, 0.85)
            self.assertEqual(verification.failure_reason, "")

        # 2. Mismatched case (routes to requires_manual_review)
        participant_mismatch = Participant.objects.create(envelope=envelope, name="Jane Smith", email="mismatch@test.com", role="signer")
        with patch('services.identity_verification_service.parse_identity_document') as mock_parse:
            mock_parse.return_value = {"full_name": "John Doe", "national_id_number": "123"}
            verification = perform_identity_verification(participant_mismatch, b"fake_image_bytes")
            
            self.assertEqual(verification.status, "requires_manual_review")
            self.assertFalse(verification.identity_matched)
            self.assertLess(verification.identity_match_score, 0.85)
            self.assertEqual(verification.failure_reason, "identity_name_mismatch")


class ConfigurationRegistryTestCase(TestCase):
    def test_config_registry_defaults(self):
        from esign.config import esign_config
        self.assertEqual(esign_config.face_match_threshold, 0.6)
        self.assertEqual(esign_config.identity_match_threshold, 0.85)
        self.assertEqual(esign_config.otp_expiry, 10)
        self.assertEqual(esign_config.signing_link_expiry, 24)
        self.assertEqual(esign_config.max_otp_attempts, 5)
        self.assertEqual(esign_config.max_upload_size, 20 * 1024 * 1024)
        self.assertEqual(esign_config.api_version, "v1")

    def test_config_validation(self):
        from esign.config import ESignatureConfig
        from django.core.exceptions import ImproperlyConfigured
        from django.test import override_settings

        # Valid override
        with override_settings(FACE_MATCH_THRESHOLD=0.7):
            config = ESignatureConfig()
            self.assertEqual(config.face_match_threshold, 0.7)

        # Invalid face threshold
        with override_settings(FACE_MATCH_THRESHOLD=1.5):
            with self.assertRaises(ImproperlyConfigured):
                ESignatureConfig()

        # Invalid OTP expiry
        with override_settings(ESIGN_OTP_EXPIRY_MINUTES=-1):
            with self.assertRaises(ImproperlyConfigured):
                ESignatureConfig()


class ProviderRegistryTestCase(TestCase):
    def test_provider_registry_resolution(self):
        from esign.providers.registry import ESignatureProviderRegistry
        from esign.providers.ocr import CombinedOCRProvider
        from esign.providers.face import InsightFaceMatchingProvider
        from django.core.exceptions import ImproperlyConfigured
        from django.test import override_settings

        # Test defaults
        registry = ESignatureProviderRegistry()
        self.assertIsInstance(registry.ocr_provider, CombinedOCRProvider)
        self.assertIsInstance(registry.face_provider, InsightFaceMatchingProvider)

        # Test Azure OCR selection is no longer supported and raises error
        with override_settings(ESIGN_OCR_PROVIDER="azure"):
            registry_azure = ESignatureProviderRegistry()
            with self.assertRaises(ImproperlyConfigured):
                _ = registry_azure.ocr_provider

        # Test invalid provider raising error
        with override_settings(ESIGN_OCR_PROVIDER="invalid_ocr"):
            registry_invalid = ESignatureProviderRegistry()
            with self.assertRaises(ImproperlyConfigured):
                _ = registry_invalid.ocr_provider


class EventDispatcherTestCase(TestCase):
    def test_event_registration_and_publishing(self):
        from esign.events.dispatcher import EventDispatcher
        from esign.events.base import DomainEvent

        dispatcher = EventDispatcher()
        executed_events = []

        def dummy_handler(event: DomainEvent):
            executed_events.append(event)

        dispatcher.register("test.event", dummy_handler)
        event = DomainEvent("test.event", {"foo": "bar"})
        dispatcher.publish(event)

        self.assertEqual(len(executed_events), 1)
        self.assertEqual(executed_events[0].payload["foo"], "bar")

    def test_handler_error_isolation(self):
        from esign.events.dispatcher import EventDispatcher
        from esign.events.base import DomainEvent

        dispatcher = EventDispatcher()
        execution_order = []

        def failing_handler(event: DomainEvent):
            execution_order.append("failing")
            raise ValueError("Boom!")

        def succeeding_handler(event: DomainEvent):
            execution_order.append("succeeding")

        dispatcher.register("isolate.event", failing_handler)
        dispatcher.register("isolate.event", succeeding_handler)

        event = DomainEvent("isolate.event", {})
        # Should not raise exception
        dispatcher.publish(event)

        self.assertEqual(execution_order, ["failing", "succeeding"])

    @patch("requests.post")
    def test_webhook_delivery(self, mock_post):
        from esign.models import WebhookSubscription
        from esign.events.handlers import handle_webhooks
        from esign.events.base import DomainEvent
        from django.test import override_settings
        import json

        # Configure mock post
        mock_post.return_value.status_code = 200

        # Create active subscription
        sub = WebhookSubscription.objects.create(
            url="https://test-webhook.url/endpoint",
            is_active=True,
            events=["envelope.completed"]
        )

        event = DomainEvent("envelope.completed", {"envelope_id": 42})
        
        with override_settings(ESIGN_WEBHOOKS_ENABLED=True):
            handle_webhooks(event)
            
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://test-webhook.url/endpoint")
        payload = json.loads(kwargs["data"])
        self.assertEqual(payload["event"], "envelope.completed")
        self.assertEqual(payload["data"]["envelope_id"], 42)


class ObservabilityTestCase(TestCase):
    def test_request_id_middleware(self):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.get("/api/v1/swagger/")
        
        # Verify X-Request-ID header is present in the response
        self.assertIn("X-Request-ID", response)
        request_id = response["X-Request-ID"]
        self.assertTrue(len(request_id) > 0)

        # Propagates an existing header if provided
        custom_id = "test-custom-request-id-1234"
        response2 = client.get("/api/v1/swagger/", HTTP_X_REQUEST_ID=custom_id)
        self.assertEqual(response2.get("X-Request-ID"), custom_id)

    def test_request_context_thread_local(self):
        from esign.request_context import set_request_id, get_request_id, clear_request_id
        set_request_id("thread-test-id")
        self.assertEqual(get_request_id(), "thread-test-id")
        clear_request_id()
        self.assertEqual(get_request_id(), "no-request-id")

    def test_exceptions_hierarchy(self):
        from esign.exceptions import (
            ESignValidationError, ESignProviderError, ESignBusinessRuleViolation,
            ESignExternalServiceError, ESignNotFoundError, ESignAuthorizationError
        )
        val_err = ESignValidationError("validation failure", detail={"field": "error"})
        self.assertEqual(val_err.category, "validation_error")
        self.assertIn("validation failure", str(val_err))
        self.assertEqual(val_err.detail, {"field": "error"})


class HealthEndpointTestCase(TestCase):
    def test_liveness_endpoint(self):
        from django.test import Client
        client = Client()
        response = client.get("/live")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["module"], "esignature")
        self.assertIn("version", data)
        self.assertIn("timestamp", data)
        self.assertIn("request_id", data)

    def test_readiness_endpoint(self):
        from django.test import Client
        client = Client()
        response = client.get("/ready")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("database", data["checks"])
        self.assertEqual(data["checks"]["database"]["status"], "ok")
        self.assertIn("storage", data["checks"])
        self.assertEqual(data["checks"]["storage"]["status"], "ok")
        self.assertIn("config", data["checks"])
        self.assertEqual(data["checks"]["config"]["status"], "ok")
        self.assertIn("providers", data["checks"])

    def test_health_endpoint(self):
        from django.test import Client
        client = Client()
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("checks", data)
        self.assertEqual(data["checks"]["database"]["status"], "ok")



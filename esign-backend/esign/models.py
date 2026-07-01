from django.db import models
import uuid
from django.contrib.auth.models import User
from django.conf import settings

def get_default_user():
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(
        username='default_user',
        defaults={'email': 'default@example.com', 'is_active': True}
    )
    return user

# Create your models here.
class Document(models.Model):
    file = models.FileField(upload_to="documents/")
    file_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True
    )
    def __str__(self):
        return self.file.name if self.file else "Document"

class Envelope(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('signed', 'Signed'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('declined', 'Declined'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE)

    title = models.CharField(
        max_length=255,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    signature_page = models.IntegerField(default=1)

    # Ratio-based click position (0.0–1.0 relative to the rendered page).
    # Multiply by actual PDF page dimensions at signing time to get PDF coords.
    signature_x_ratio = models.FloatField(null=True, blank=True)

    signature_y_ratio = models.FloatField(null=True, blank=True)

    send_reminders = models.BooleanField(default=False)

    send_final_email = models.BooleanField(default=True)

    allow_printing = models.BooleanField(default=True)

    email_otp_required = models.BooleanField(default=False)
    sms_otp_required = models.BooleanField(default=False)
    national_id_required = models.BooleanField(default=False)
    face_biometric_required = models.BooleanField(default=False)
    representative_match_required = models.BooleanField(default=False)
    terms_acceptance_required = models.BooleanField(default=False)

    additional_recipients = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='envelopes', null=True, blank=True)

    VALID_TRANSITIONS = {
        'draft': {'sent', 'viewed', 'completed', 'declined', 'cancelled'},
        'sent': {'sent', 'viewed', 'completed', 'declined', 'expired'},
        'viewed': {'sent', 'viewed', 'completed', 'declined', 'expired'},
        'signed': {'completed'},
        'completed': set(),
        'declined': set(),
        'expired': set(),
        'cancelled': set(),
    }

    def transition_to(self, target_status):
        from esign.exceptions import InvalidStateTransition
        
        valid_targets = self.VALID_TRANSITIONS.get(self.status, set())
        if target_status not in valid_targets:
            raise InvalidStateTransition(
                f"Cannot transition envelope from {self.status} to {target_status}"
            )
        
        self.status = target_status
        self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        if not self.owner:
            self.owner = get_default_user()
        super().save(*args, **kwargs)
        
class Signer(models.Model):
    envelope = models.OneToOneField(Envelope, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField()

    def __str__(self):
        return f"{self.name} <{self.email}>"

class SigningToken(models.Model):
    signer = models.OneToOneField(Signer, on_delete=models.CASCADE)
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)


class AuditLog(models.Model):
    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE)
    event = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event} on {self.envelope} at {self.timestamp}"

class SignedDocument(models.Model):
    envelope = models.OneToOneField(Envelope, on_delete=models.CASCADE)
    file = models.FileField(upload_to="signed/")
    final_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SignedDocument for Envelope {self.envelope.id}"

class CompletionCertificate(models.Model):
    envelope = models.OneToOneField(Envelope, on_delete=models.CASCADE, related_name="completion_certificate")
    file = models.FileField(upload_to="certificates/")
    certificate_id = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    final_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Completion Certificate for Envelope {self.envelope.id}"

class Participant(models.Model):
    ROLE_CHOICES = [
        ("signer", "Signer"),
        ("approver", "Approver"),
        ("reviewer", "Reviewer"),
        ("cc", "CC"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("viewed", "Viewed"),
        ("completed", "Completed"),
        ("declined", "Declined"),
        ("returned", "Returned"),
    ]

    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE, related_name="participants")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="signer"
    )
    order = models.PositiveIntegerField(default=1)
    step_number = models.PositiveIntegerField(default=1)
    has_completed = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}) for Envelope {self.envelope.id}"

class ParticipantToken(models.Model):
    participant = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name="token")
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True
    )
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token for {self.participant.name} ({self.participant.role}) - Used: {self.is_used}"


class ParticipantAuthorizationState(models.Model):
    participant = models.OneToOneField(
        Participant,
        on_delete=models.CASCADE,
        related_name="authorization_state"
    )
    # Email OTP
    email_otp_code = models.CharField(max_length=64, blank=True, default="")
    email_otp_sent_at = models.DateTimeField(null=True, blank=True)
    email_otp_expires_at = models.DateTimeField(null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # SMS OTP
    sms_verified = models.BooleanField(default=False)
    # Terms
    accepted_terms = models.BooleanField(default=False)
    accepted_terms_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Authorization State for Participant {self.participant.id}"


class Template(models.Model):
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('public', 'Public'),
    ]
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='General')
    description = models.TextField(blank=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')
    workflow_definition = models.JSONField(default=list, blank=True)
    request_settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='templates', null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.owner:
            self.owner = get_default_user()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.category})"


class DocumentField(models.Model):
    # Note: Current MVP supports only signature placement.
    # Future planned field types:
    # - date
    # - text
    # - checkbox
    # These remain supported in the data model for future enterprise workflow expansion.
    FIELD_TYPE_CHOICES = [
        ('signature', 'Signature'),
        ('date', 'Date'),
        ('text', 'Text'),
        ('checkbox', 'Checkbox'),
    ]

    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE, related_name="fields")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="fields")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES)
    page = models.IntegerField()
    x_ratio = models.FloatField()
    y_ratio = models.FloatField()
    required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.field_type} on page {self.page} for {self.participant.name}"


class RepresentativeCandidate(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('converted', 'Converted'),
        ('ignored', 'Ignored'),
    ]
    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE, related_name="representative_candidates")
    name_en = models.CharField(max_length=255, blank=True)
    name_ar = models.CharField(max_length=255, blank=True)
    title_en = models.CharField(max_length=255, blank=True)
    title_ar = models.CharField(max_length=255, blank=True)
    authority_clause = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    converted_at = models.DateTimeField(null=True, blank=True)
    ignored_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Candidate {self.name_en or self.name_ar} ({self.status}) for Envelope {self.envelope.id}"


class ContractAnalysisAudit(models.Model):
    envelope = models.OneToOneField(Envelope, on_delete=models.CASCADE, related_name="analysis_audit")
    representative_name = models.CharField(max_length=512, blank=True)
    representative_title = models.CharField(max_length=512, blank=True)
    authority_clause = models.TextField(blank=True)
    authority_detected = models.BooleanField(default=False)
    ocr_provider = models.CharField(max_length=50, blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Audit log for Envelope {self.envelope.id}"





class VerificationSession(models.Model):
    participant = models.OneToOneField(
        Participant,
        on_delete=models.CASCADE,
        related_name="verification_session"
    )
    status = models.CharField(
        max_length=30,
        default="pending"
    )
    failure_reason = models.CharField(
        max_length=255,
        blank=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"VerificationSession ({self.status}) for Participant {self.participant.id}"


class BiometricVerification(models.Model):
    participant = models.OneToOneField(
        Participant,
        on_delete=models.CASCADE,
        related_name="biometric_verification"
    )
    verification_session = models.OneToOneField(
        VerificationSession,
        on_delete=models.CASCADE,
        related_name="biometric_verification"
    )
    status = models.CharField(
        max_length=30,
        default="pending"
    )
    similarity_score = models.FloatField(null=True, blank=True)
    liveness_score = models.FloatField(null=True, blank=True)
    provider = models.CharField(max_length=255, blank=True)
    failure_reason = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"BiometricVerification ({self.status}) for Participant {self.participant.id}"


class SignerIdentityVerification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
        ('requires_manual_review', 'Requires Manual Review'),
    ]

    participant = models.OneToOneField(
        Participant,
        on_delete=models.CASCADE,
        related_name="signer_identity_verification"
    )
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='pending'
    )
    document_image = models.FileField(
        upload_to="identity/documents/",
        blank=True,
        null=True
    )
    reference_face_image = models.FileField(
        upload_to="identity/faces/",
        blank=True,
        null=True
    )
    full_name = models.CharField(
        max_length=255,
        blank=True
    )
    national_id_number = models.CharField(
        max_length=50,
        blank=True
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True
    )
    document_type = models.CharField(
        max_length=50,
        blank=True
    )
    identity_match_score = models.FloatField(
        null=True,
        blank=True
    )
    identity_matched = models.BooleanField(
        null=True,
        blank=True
    )
    failure_reason = models.TextField(
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Identity Verification ({self.status}) for Participant {self.participant.id}"


class WebhookSubscription(models.Model):
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    events = models.JSONField(default=list, help_text="List of events subscribed, e.g. ['envelope.completed'], or ['*'] for all events")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Webhook to {self.url} (Active: {self.is_active})"




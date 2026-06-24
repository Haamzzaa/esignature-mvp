from django.db import models
import uuid
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from esign.constants import (
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_ID_UPLOADED,
    VERIFICATION_STATUS_SELFIE_UPLOADED,
    VERIFICATION_STATUS_UNDER_REVIEW,
    VERIFICATION_STATUS_VERIFIED,
    VERIFICATION_STATUS_FAILED,
    VERIFICATION_STATUS_CHOICES,
    VERIFICATION_METHOD_INTERNAL,
    VERIFICATION_METHOD_CHOICES,
    VERIFICATION_EVENT_CHOICES,
)

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
    email_otp_code = models.CharField(max_length=6, blank=True, default="")
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


class SignerVerification(models.Model):
    participant = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name="verification")
    status = models.CharField(
        max_length=50,
        choices=VERIFICATION_STATUS_CHOICES,
        default=VERIFICATION_STATUS_PENDING,
    )
    verification_method = models.CharField(
        max_length=50,
        choices=VERIFICATION_METHOD_CHOICES,
        default=VERIFICATION_METHOD_INTERNAL,
    )
    national_id_number = models.CharField(max_length=50, blank=True)
    national_id_front = models.FileField(
        upload_to="verification/id_front/",
        blank=True,
        null=True,
    )
    national_id_back = models.FileField(
        upload_to="verification/id_back/",
        blank=True,
        null=True,
    )
    selfie_image = models.FileField(
        upload_to="verification/selfie/",
        blank=True,
        null=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    VALID_TRANSITIONS = {
        VERIFICATION_STATUS_PENDING: {VERIFICATION_STATUS_ID_UPLOADED, VERIFICATION_STATUS_FAILED},
        VERIFICATION_STATUS_ID_UPLOADED: {VERIFICATION_STATUS_SELFIE_UPLOADED, VERIFICATION_STATUS_FAILED},
        VERIFICATION_STATUS_SELFIE_UPLOADED: {VERIFICATION_STATUS_UNDER_REVIEW, VERIFICATION_STATUS_FAILED},
        VERIFICATION_STATUS_UNDER_REVIEW: {VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_FAILED},
        VERIFICATION_STATUS_VERIFIED: {VERIFICATION_STATUS_FAILED},
        VERIFICATION_STATUS_FAILED: {VERIFICATION_STATUS_PENDING},
    }

    def transition_to(self, target_status):
        valid_targets = self.VALID_TRANSITIONS.get(self.status, set())
        if target_status not in valid_targets:
            raise ValidationError(
                f"Cannot transition verification from {self.status} to {target_status}"
            )
        self.status = target_status
        self.save(update_fields=["status"])

    @property
    def masked_national_id(self):
        if not self.national_id_number:
            return ""
        length = len(self.national_id_number)
        if length <= 4:
            return "*" * length
        return "*" * (length - 4) + self.national_id_number[-4:]

    def __str__(self):
        return f"Verification ({self.status}) for Participant {self.participant.id}"


class VerificationEvent(models.Model):
    signer_verification = models.ForeignKey(SignerVerification, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(
        max_length=50,
        choices=VERIFICATION_EVENT_CHOICES,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("VerificationEvent is append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("VerificationEvent is append-only and cannot be deleted.")

    def __str__(self):
        return f"Event {self.event_type} at {self.timestamp}"


class NationalIdentity(models.Model):
    EXTRACTION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    verification = models.OneToOneField(
        "SignerVerification",
        on_delete=models.CASCADE,
        related_name="national_identity"
    )
    document_type = models.CharField(
        max_length=30,
        choices=[
            ("saudi_id", "Saudi National ID"),
            ("iqama", "Iqama"),
            ("passport", "Passport"),
            ("aadhaar", "Aadhaar"),
            ("unknown", "Unknown"),
        ],
        default="unknown"
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
    expiry_date = models.DateField(
        null=True,
        blank=True
    )
    id_photo = models.ImageField(
        upload_to="verification/id_photo/",
        null=True,
        blank=True
    )
    ocr_provider = models.CharField(
        max_length=50,
        default="azure"
    )
    ocr_confidence = models.FloatField(
        null=True,
        blank=True
    )
    raw_text = models.TextField(
        blank=True
    )
    extraction_status = models.CharField(
        max_length=20,
        choices=EXTRACTION_STATUS_CHOICES,
        default="pending"
    )
    failure_reason = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ("no_text_detected", "No text detected"),
            ("parsing_failed", "Parsing failed"),
            ("azure_error", "Azure OCR service error"),
        ]
    )
    extracted_at = models.DateTimeField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    @property
    def masked_national_id(self):
        if not self.national_id_number:
            return ""
        return "*" * max(0, len(self.national_id_number) - 4) + self.national_id_number[-4:]

    def __str__(self):
        return f"NationalIdentity ({self.document_type}) for Verification {self.verification.id}"


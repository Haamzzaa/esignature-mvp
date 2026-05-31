from django.db import models
import uuid

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
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE)

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

    created_at = models.DateTimeField(auto_now_add=True)
        
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
    event = models.CharField(max_length=50)
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
   
   

        
   


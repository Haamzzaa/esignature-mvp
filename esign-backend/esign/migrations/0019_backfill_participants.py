from django.db import migrations
from django.utils import timezone
from datetime import timedelta
import uuid

def backfill_participants(apps, schema_editor):
    Envelope = apps.get_model('esign', 'Envelope')
    Signer = apps.get_model('esign', 'Signer')
    Participant = apps.get_model('esign', 'Participant')
    ParticipantToken = apps.get_model('esign', 'ParticipantToken')
    SigningToken = apps.get_model('esign', 'SigningToken')

    # Iterate through envelopes that have a legacy Signer
    envelopes_with_signer = Envelope.objects.filter(signer__isnull=False)
    
    for envelope in envelopes_with_signer:
        # Idempotent Migration check
        if envelope.participants.exists():
            continue
            
        signer = Signer.objects.filter(envelope=envelope).first()
        if not signer:
            continue
            
        # Conservative Status Mapping
        if envelope.status in ["completed", "signed"]:
            p_status = "completed"
            has_completed = True
            completed_at = timezone.now()
        elif envelope.status == "viewed":
            p_status = "viewed"
            has_completed = False
            completed_at = None
        else:
            p_status = "active"
            has_completed = False
            completed_at = None

        # Create Participant
        p = Participant.objects.create(
            envelope=envelope,
            name=signer.name,
            email=signer.email,
            role="signer",
            step_number=1,
            order=1,
            status=p_status,
            has_completed=has_completed,
            completed_at=completed_at
        )

        # SigningToken Reuse
        legacy_token = SigningToken.objects.filter(signer=signer).first()
        if legacy_token:
            ParticipantToken.objects.create(
                participant=p,
                token=legacy_token.token,
                expires_at=legacy_token.expires_at,
                is_used=legacy_token.is_used
            )
        else:
            # Create a fresh ParticipantToken
            ParticipantToken.objects.create(
                participant=p,
                token=uuid.uuid4(),
                expires_at=timezone.now() + timedelta(hours=24),
                is_used=False
            )

class Migration(migrations.Migration):
    dependencies = [
        ('esign', '0018_alter_auditlog_event'),
    ]

    operations = [
        migrations.RunPython(backfill_participants, reverse_code=migrations.RunPython.noop),
    ]

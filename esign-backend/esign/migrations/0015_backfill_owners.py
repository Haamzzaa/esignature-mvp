from django.db import migrations

def backfill_owners(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Envelope = apps.get_model('esign', 'Envelope')
    Template = apps.get_model('esign', 'Template')

    if Envelope.objects.filter(owner__isnull=True).exists() or Template.objects.filter(owner__isnull=True).exists():
        default_user, created = User.objects.get_or_create(
            username='default_user',
            defaults={'email': 'default@example.com', 'is_active': True}
        )
        Envelope.objects.filter(owner__isnull=True).update(owner=default_user)
        Template.objects.filter(owner__isnull=True).update(owner=default_user)

class Migration(migrations.Migration):
    dependencies = [
        ('esign', '0014_envelope_owner_template_owner'),
    ]

    operations = [
        migrations.RunPython(backfill_owners, reverse_code=migrations.RunPython.noop),
    ]

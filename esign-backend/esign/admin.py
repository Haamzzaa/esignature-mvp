# pyrefly: ignore [missing-import]
from django.contrib import admin
# pyrefly: ignore [missing-import]
from django.apps import apps
from .models import Envelope, Participant

@admin.register(Envelope)
class EnvelopeAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'created_at')

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'role', 'step_number', 'envelope', 'has_completed', 'created_at')

# Auto-register all models from this app so they appear in Django admin.
for model in apps.get_app_config("esign").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

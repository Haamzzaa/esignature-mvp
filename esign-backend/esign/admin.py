from django.contrib import admin
from django.apps import apps

# Register your models here.

# Auto-register all models from this app so they appear in Django admin.
for model in apps.get_app_config("esign").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

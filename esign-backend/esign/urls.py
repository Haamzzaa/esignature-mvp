from django.urls import path
from .views import (
    DocumentUploadView,
    EnvelopeCreateView,
    SendEnvelopeView,
    SigningView,
    SigningDocumentView,
    SigningSignedDocumentView,
    SigningDownloadView,
)

urlpatterns = [
    path('documents/upload/', DocumentUploadView.as_view()),
    path('envelopes/', EnvelopeCreateView.as_view()),
    path('envelopes/<int:envelope_id>/send/', SendEnvelopeView.as_view()),
    path('sign/<uuid:token>/', SigningView.as_view()),
    path('sign/<uuid:token>/document/', SigningDocumentView.as_view(), name='signing-document'),
    path('sign/<uuid:token>/signed/', SigningSignedDocumentView.as_view(), name='signing-signed'),
    path('sign/<uuid:token>/download/', SigningDownloadView.as_view(), name='signing-download'),
]
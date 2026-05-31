from django.urls import path
from .views import DocumentUploadView, EnvelopeCreateView, SendEnvelopeView, SigningView

urlpatterns = [
    path('documents/upload/', DocumentUploadView.as_view()),
    path('envelopes/', EnvelopeCreateView.as_view()),
    path('envelopes/<int:envelope_id>/send/', SendEnvelopeView.as_view()),
    path('sign/<uuid:token>/', SigningView.as_view()),
]
from esign.providers.base import BaseCertificateProvider
from esign.models import Envelope

class InternalPDFCertificateProvider(BaseCertificateProvider):
    """
    Generates E-Signature completion certificate internally using ReportLab.
    """
    def generate_certificate(self, envelope_id: int) -> bytes:
        import services.certificate_service
        envelope = Envelope.objects.get(id=envelope_id)
        cert_pdf_bytes, _ = services.certificate_service.generate_completion_certificate(envelope)
        return cert_pdf_bytes

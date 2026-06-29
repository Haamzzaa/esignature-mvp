from esign.providers.base import BaseOCRProvider

class CombinedOCRProvider(BaseOCRProvider):
    """
    Combines PDF digital extraction with a PaddleOCR fallback engine.
    """
    def extract_text(self, pdf_bytes: bytes) -> dict:
        import services.ocr_service
        return services.ocr_service.extract_text_from_pdf(pdf_bytes)

class AzureOCRProvider(BaseOCRProvider):
    """
    Performs text extraction via Microsoft Azure Document Intelligence.
    """
    def extract_text(self, pdf_bytes: bytes) -> dict:
        import services.azure_ocr_service
        return services.azure_ocr_service.extract_text_with_azure(pdf_bytes)

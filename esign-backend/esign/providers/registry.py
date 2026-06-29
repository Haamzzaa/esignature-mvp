import time
import logging

from django.core.exceptions import ImproperlyConfigured
from esign.config import esign_config

# Import base interfaces
from esign.providers.base import (
    BaseOCRProvider,
    BaseFaceMatchingProvider,
    BaseLivenessProvider,
    BaseNotificationProvider,
    BaseStorageProvider,
    BaseCertificateProvider,
)

logger = logging.getLogger("esign.providers")


def _resolve_provider(category: str, configured_name: str, factory):
    """
    Resolves a provider instance via `factory`, emitting structured
    diagnostics: category, configured name, concrete class, duration.
    Never logs secrets or credential values.
    """
    start = time.perf_counter()
    try:
        instance = factory()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "[ProviderRegistry] Resolved provider: category=%s configured=%s "
            "class=%s duration=%dms",
            category,
            configured_name,
            type(instance).__name__,
            elapsed_ms,
        )
        return instance
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "[ProviderRegistry] Failed to resolve provider: category=%s configured=%s "
            "error=%s duration=%dms",
            category,
            configured_name,
            str(exc),
            elapsed_ms,
        )
        raise


class ESignatureProviderRegistry:
    """
    Central Provider Registry responsible for resolving configured
    external service providers (OCR, Face, Storage, etc.).
    """
    def __init__(self):
        self._ocr_provider = None
        self._face_provider = None
        self._liveness_provider = None
        self._notification_provider = None
        self._storage_provider = None
        self._certificate_provider = None

    @property
    def ocr_provider(self) -> BaseOCRProvider:
        if self._ocr_provider is None:
            provider_name = esign_config.ocr_provider.lower()

            def _factory():
                if provider_name in ('paddle', 'combined'):
                    from esign.providers.ocr import CombinedOCRProvider
                    return CombinedOCRProvider()
                elif provider_name == 'azure':
                    from esign.providers.ocr import AzureOCRProvider
                    return AzureOCRProvider()
                else:
                    raise ImproperlyConfigured(f"Unsupported OCR provider: {provider_name}")

            self._ocr_provider = _resolve_provider("ocr", provider_name, _factory)
        return self._ocr_provider

    @property
    def face_provider(self) -> BaseFaceMatchingProvider:
        if self._face_provider is None:
            provider_name = esign_config.face_provider.lower()

            def _factory():
                if provider_name in ('internal', 'insightface'):
                    from esign.providers.face import InsightFaceMatchingProvider
                    return InsightFaceMatchingProvider()
                else:
                    raise ImproperlyConfigured(f"Unsupported Face provider: {provider_name}")

            self._face_provider = _resolve_provider("face", provider_name, _factory)
        return self._face_provider

    @property
    def liveness_provider(self) -> BaseLivenessProvider:
        if self._liveness_provider is None:
            provider_name = esign_config.liveness_provider.lower()

            def _factory():
                if provider_name in ('internal', 'placeholder'):
                    from esign.providers.liveness import PlaceholderLivenessProvider
                    return PlaceholderLivenessProvider()
                else:
                    raise ImproperlyConfigured(f"Unsupported Liveness provider: {provider_name}")

            self._liveness_provider = _resolve_provider("liveness", provider_name, _factory)
        return self._liveness_provider

    @property
    def notification_provider(self) -> BaseNotificationProvider:
        if self._notification_provider is None:
            provider_name = esign_config.notification_provider.lower()

            def _factory():
                if provider_name in ('email', 'smtp'):
                    from esign.providers.notification import SMTPEmailNotificationProvider
                    return SMTPEmailNotificationProvider()
                else:
                    raise ImproperlyConfigured(f"Unsupported Notification provider: {provider_name}")

            self._notification_provider = _resolve_provider("notification", provider_name, _factory)
        return self._notification_provider

    @property
    def storage_provider(self) -> BaseStorageProvider:
        if self._storage_provider is None:
            def _factory():
                from esign.providers.storage import DjangoStorageProvider
                return DjangoStorageProvider()

            self._storage_provider = _resolve_provider("storage", "django", _factory)
        return self._storage_provider

    @property
    def certificate_provider(self) -> BaseCertificateProvider:
        if self._certificate_provider is None:
            def _factory():
                from esign.providers.certificate import InternalPDFCertificateProvider
                return InternalPDFCertificateProvider()

            self._certificate_provider = _resolve_provider("certificate", "internal_pdf", _factory)
        return self._certificate_provider


# Instantiate central provider registry
esign_provider_registry = ESignatureProviderRegistry()

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
import logging

logger = logging.getLogger(__name__)

class ESignatureConfig:
    """
    Centralized configuration registry for the E-Signature Platform.
    Exposes dynamic properties mapped to Django settings and performs
    startup validation checks.
    """
    def __init__(self):
        # Execute validation on configuration instantiation
        self.validate()

    # ── 1. Security ────────────────────────────────────────────────────────
    @property
    def face_match_threshold(self) -> float:
        return float(getattr(settings, "FACE_MATCH_THRESHOLD", 0.6))

    @property
    def identity_match_threshold(self) -> float:
        return float(getattr(settings, "IDENTITY_MATCH_THRESHOLD", 0.85))

    @property
    def otp_expiry(self) -> int:
        return int(getattr(settings, "ESIGN_OTP_EXPIRY_MINUTES", 10))

    @property
    def signing_link_expiry(self) -> int:
        return int(getattr(settings, "ESIGN_SIGNING_LINK_EXPIRY_HOURS", 24))

    @property
    def max_otp_attempts(self) -> int:
        return int(getattr(settings, "ESIGN_MAX_OTP_ATTEMPTS", 5))

    @property
    def max_upload_size(self) -> int:
        return int(getattr(settings, "ESIGN_MAX_UPLOAD_SIZE_BYTES", 20 * 1024 * 1024))

    # ── 2. File Handling ───────────────────────────────────────────────────
    @property
    def allowed_image_mime_types(self) -> list:
        return list(getattr(settings, "ESIGN_ALLOWED_IMAGE_MIME_TYPES", ['image/jpeg', 'image/jpg', 'image/png']))

    @property
    def allowed_pdf_mime_types(self) -> list:
        return list(getattr(settings, "ESIGN_ALLOWED_PDF_MIME_TYPES", ['application/pdf']))

    @property
    def max_pdf_size(self) -> int:
        return int(getattr(settings, "ESIGN_MAX_PDF_SIZE_BYTES", 10 * 1024 * 1024))

    @property
    def max_image_size(self) -> int:
        return int(getattr(settings, "ESIGN_MAX_IMAGE_SIZE_BYTES", 5 * 1024 * 1024))

    # ── 3. OCR ─────────────────────────────────────────────────────────────
    @property
    def ocr_provider(self) -> str:
        return str(getattr(settings, "ESIGN_OCR_PROVIDER", "paddle"))

    @property
    def identity_ocr_provider(self) -> str:
        return str(getattr(settings, "IDENTITY_OCR_PROVIDER", "gemini"))

    @property
    def contract_ocr_provider(self) -> str:
        return str(getattr(settings, "CONTRACT_OCR_PROVIDER", "gemini"))

    @property
    def ocr_timeout(self) -> int:
        return int(getattr(settings, "ESIGN_OCR_TIMEOUT_SECONDS", 30))

    @property
    def ocr_confidence_threshold(self) -> float:
        return float(getattr(settings, "ESIGN_OCR_CONFIDENCE_THRESHOLD", 0.0))

    # ── 4. Face Verification ───────────────────────────────────────────────
    @property
    def face_provider(self) -> str:
        return str(getattr(settings, "FACE_PROVIDER", getattr(settings, "ESIGN_FACE_PROVIDER", "insightface")))

    @property
    def liveness_provider(self) -> str:
        return str(getattr(settings, "LIVENESS_PROVIDER", getattr(settings, "ESIGN_LIVENESS_PROVIDER", "internal")))

    @property
    def liveness_enabled(self) -> bool:
        return bool(getattr(settings, "ESIGN_LIVENESS_ENABLED", False))

    # ── 5. Notifications ───────────────────────────────────────────────────
    @property
    def reminder_interval(self) -> int:
        return int(getattr(settings, "ESIGN_REMINDER_INTERVAL_HOURS", 24))

    @property
    def notification_provider(self) -> str:
        return str(getattr(settings, "NOTIFICATION_PROVIDER", getattr(settings, "ESIGN_NOTIFICATION_PROVIDER", "brevo")))

    @property
    def notification_retry_count(self) -> int:
        return int(getattr(settings, "ESIGN_NOTIFICATION_RETRY_COUNT", 3))

    # ── 6. General ─────────────────────────────────────────────────────────
    @property
    def api_version(self) -> str:
        return str(getattr(settings, "ESIGN_API_VERSION", "v1"))

    @property
    def module_name(self) -> str:
        return str(getattr(settings, "ESIGN_MODULE_NAME", "esignature"))

    @property
    def default_pagination_size(self) -> int:
        return int(getattr(settings, "ESIGN_DEFAULT_PAGINATION_SIZE", 10))

    # Core Django settings bindings
    @property
    def frontend_url(self) -> str:
        return str(getattr(settings, "FRONTEND_URL", "http://localhost:5173"))

    @property
    def default_from_email(self) -> str:
        return str(getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com"))

    @property
    def use_celery(self) -> bool:
        return bool(getattr(settings, "USE_CELERY", False))

    # ── 7. Webhooks and Events ─────────────────────────────────────────────
    @property
    def webhooks_enabled(self) -> bool:
        return bool(getattr(settings, "ESIGN_WEBHOOKS_ENABLED", True))

    @property
    def events_enabled(self) -> bool:
        return bool(getattr(settings, "ESIGN_EVENTS_ENABLED", True))

    @property
    def webhook_timeout(self) -> int:
        return int(getattr(settings, "ESIGN_WEBHOOK_TIMEOUT_SECONDS", 10))

    @property
    def webhook_max_retries(self) -> int:
        return int(getattr(settings, "ESIGN_WEBHOOK_MAX_RETRIES", 3))

    @property
    def event_logging_enabled(self) -> bool:
        return bool(getattr(settings, "ESIGN_EVENT_LOGGING_ENABLED", True))

    # ── 8. Rate Limiting ───────────────────────────────────────────────────
    @property
    def rate_limit_login(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_LOGIN", "5/m"))

    @property
    def rate_limit_otp_send(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_OTP_SEND", "3/m"))

    @property
    def rate_limit_otp_verify_attempts(self) -> int:
        return int(getattr(settings, "ESIGN_RATE_LIMIT_OTP_VERIFY_ATTEMPTS", 5))

    @property
    def rate_limit_otp_verify_lockout(self) -> int:
        return int(getattr(settings, "ESIGN_RATE_LIMIT_OTP_VERIFY_LOCKOUT_SECONDS", 900))

    @property
    def rate_limit_face_verification(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_FACE_VERIFICATION", "5/m"))

    @property
    def rate_limit_ocr(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_OCR", "10/m"))

    @property
    def rate_limit_contract_analysis(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_CONTRACT_ANALYSIS", "3/m"))

    @property
    def rate_limit_signing(self) -> str:
        return str(getattr(settings, "ESIGN_RATE_LIMIT_SIGNING", "10/m"))

    def validate(self):
        """
        Validates all configuration attributes to prevent invalid runtimes.
        """
        if not (0.0 <= self.face_match_threshold <= 1.0):
            raise ImproperlyConfigured("FACE_MATCH_THRESHOLD must be between 0.0 and 1.0")
        if not (0.0 <= self.identity_match_threshold <= 1.0):
            raise ImproperlyConfigured("IDENTITY_MATCH_THRESHOLD must be between 0.0 and 1.0")
        if self.otp_expiry <= 0:
            raise ImproperlyConfigured("ESIGN_OTP_EXPIRY_MINUTES must be greater than 0")
        if self.signing_link_expiry <= 0:
            raise ImproperlyConfigured("ESIGN_SIGNING_LINK_EXPIRY_HOURS must be greater than 0")
        if self.max_otp_attempts <= 0:
            raise ImproperlyConfigured("ESIGN_MAX_OTP_ATTEMPTS must be greater than 0")
        if self.max_upload_size <= 0:
            raise ImproperlyConfigured("ESIGN_MAX_UPLOAD_SIZE_BYTES must be positive")
        if self.max_pdf_size <= 0:
            raise ImproperlyConfigured("ESIGN_MAX_PDF_SIZE_BYTES must be positive")
        if self.max_image_size <= 0:
            raise ImproperlyConfigured("ESIGN_MAX_IMAGE_SIZE_BYTES must be positive")
        if not self.api_version:
            raise ImproperlyConfigured("ESIGN_API_VERSION cannot be empty")
        if not self.module_name:
            raise ImproperlyConfigured("ESIGN_MODULE_NAME cannot be empty")
        if self.default_pagination_size <= 0:
            raise ImproperlyConfigured("ESIGN_DEFAULT_PAGINATION_SIZE must be positive")
        if self.webhook_timeout <= 0:
            raise ImproperlyConfigured("ESIGN_WEBHOOK_TIMEOUT_SECONDS must be positive")
        if self.webhook_max_retries < 0:
            raise ImproperlyConfigured("ESIGN_WEBHOOK_MAX_RETRIES cannot be negative")

        import re
        rate_limit_regex = re.compile(r'^\d+/\d*[smhd]$')
        for val, name in [
            (self.rate_limit_login, "ESIGN_RATE_LIMIT_LOGIN"),
            (self.rate_limit_otp_send, "ESIGN_RATE_LIMIT_OTP_SEND"),
            (self.rate_limit_face_verification, "ESIGN_RATE_LIMIT_FACE_VERIFICATION"),
            (self.rate_limit_ocr, "ESIGN_RATE_LIMIT_OCR"),
            (self.rate_limit_contract_analysis, "ESIGN_RATE_LIMIT_CONTRACT_ANALYSIS"),
            (self.rate_limit_signing, "ESIGN_RATE_LIMIT_SIGNING")
        ]:
            if not rate_limit_regex.match(val.strip().lower()):
                raise ImproperlyConfigured(f"{name} must be in format '<limit>/[multiplier]<s|m|h|d>', e.g. '5/m', '10/30s'. Got '{val}'")
        
        if self.rate_limit_otp_verify_attempts <= 0:
            raise ImproperlyConfigured("ESIGN_RATE_LIMIT_OTP_VERIFY_ATTEMPTS must be positive")
        if self.rate_limit_otp_verify_lockout <= 0:
            raise ImproperlyConfigured("ESIGN_RATE_LIMIT_OTP_VERIFY_LOCKOUT_SECONDS must be positive")

# Instantiate singleton registry instance
esign_config = ESignatureConfig()

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pyhanko.sign import signers, timestamps
from pyhanko.sign.general import load_certs_from_pemder_data, load_private_key_from_pemder_data
from pyhanko.sign.timestamps import HTTPTimeStamper, DummyTimeStamper

logger = logging.getLogger(__name__)


class TSAError(Exception):
    """Base exception for RFC-3161 timestamping errors."""
    pass


class TSAConfigurationError(TSAError):
    """Raised when TSA is enabled but configuration is invalid or missing."""
    pass


class TSATimeoutError(TSAError):
    """Raised when TSA request times out."""
    pass


class TSARequestError(TSAError):
    """Raised when TSA request fails after exhausting retries."""
    pass


class RetryingHTTPTimeStamper(HTTPTimeStamper):
    """
    Subclass of HTTPTimeStamper providing bounded retry logic (max 1 retry)
    and strict timeout enforcement for RFC-3161 timestamping requests.
    """
    def __init__(
        self,
        url: str,
        timeout: int = 5,
        max_retries: int = 1,
        retry_delay: float = 0.5,
        auth=None,
        headers=None,
        session=None,
    ):
        super().__init__(url=url, timeout=timeout, auth=auth, headers=headers, session=session)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def async_request_tsa_response(self, req):
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    "[TSA] Submitting RFC-3161 timestamp request (attempt %d/%d) to %s",
                    attempt + 1,
                    self.max_retries + 1,
                    self.url,
                )
                return await super().async_request_tsa_response(req)
            except Exception as e:
                last_error = e
                logger.warning("[TSA] Timestamp request failed on attempt %d: %s", attempt + 1, e)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
        raise TSARequestError(f"RFC-3161 timestamp request to {self.url} failed after {self.max_retries + 1} attempts: {last_error}")


_test_tsa_cert_cache: Optional[Tuple[bytes, bytes]] = None


def generate_test_tsa_credentials() -> Tuple[bytes, bytes]:
    """Generates an in-memory test RSA key and X.509 certificate with TimeStamping EKU for testing."""
    global _test_tsa_cert_cache
    if _test_tsa_cert_cache is not None:
        return _test_tsa_cert_cache

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "E-Sign Platform Test TSA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "E-Sign Test Timestamp Authority"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    _test_tsa_cert_cache = (cert_pem, key_pem)
    return _test_tsa_cert_cache


def get_test_timestamper() -> DummyTimeStamper:
    """Returns an in-memory DummyTimeStamper for deterministic offline test execution."""
    ts_cert_pem, ts_key_pem = generate_test_tsa_credentials()
    ts_key = load_private_key_from_pemder_data(ts_key_pem, passphrase=None)
    ts_certs = list(load_certs_from_pemder_data(ts_cert_pem))
    return DummyTimeStamper(
        tsa_cert=ts_certs[0],
        tsa_key=ts_key,
    )


def get_timestamper() -> Any:
    """
    Factory resolving the appropriate RFC-3161 TimeStamper based on configuration:
    - In production with PADES_TSA_URL: returns RetryingHTTPTimeStamper.
    - In development/testing without URL: returns get_test_timestamper().
    - Raises TSAConfigurationError if TSA is required but unconfigured in production.
    """
    if not getattr(settings, "A08_TSA_ENABLED", False):
        return None

    if not getattr(settings, "A08_PADES_ENABLED", False):
        raise TSAConfigurationError("Invalid configuration: A08_TSA_ENABLED cannot be True when A08_PADES_ENABLED is False.")

    tsa_url = getattr(settings, "PADES_TSA_URL", None)
    timeout = getattr(settings, "PADES_TSA_TIMEOUT", 5)

    if tsa_url:
        headers = {}
        auth_header = getattr(settings, "PADES_TSA_AUTH_HEADER", None)
        if auth_header:
            headers["Authorization"] = auth_header

        username = getattr(settings, "PADES_TSA_USERNAME", None)
        password = getattr(settings, "PADES_TSA_PASSWORD", None)
        auth = (username, password) if (username and password) else None

        logger.info("[TSA] Configured RFC-3161 TimeStamper targeting %s (timeout=%ds)", tsa_url, timeout)
        return RetryingHTTPTimeStamper(
            url=tsa_url,
            timeout=timeout,
            max_retries=1,
            retry_delay=0.5,
            auth=auth,
            headers=headers if headers else None,
        )

    # Fallback to test timestamper in non-production test mode
    if getattr(settings, "DEBUG", True) or getattr(settings, "TESTING", False) or not getattr(settings, "A08_PADES_REQUIRE_PROD_CREDS", False):
        logger.info("[TSA] Using ephemeral in-memory test TimeStamper")
        return get_test_timestamper()

    raise TSAConfigurationError("A08_TSA_ENABLED is True but PADES_TSA_URL is not configured.")

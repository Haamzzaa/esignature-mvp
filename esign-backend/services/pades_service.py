import base64
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.general import load_certs_from_pemder_data, load_private_key_from_pemder_data
from pyhanko.sign.validation import validate_pdf_signature

logger = logging.getLogger(__name__)


class PAdESError(Exception):
    """Base exception for PAdES sealing errors."""
    pass


class PAdESConfigurationError(PAdESError):
    """Raised when PAdES is enabled but signing credentials are missing or invalid."""
    pass


_test_cert_cache: Optional[Tuple[bytes, bytes]] = None


def generate_test_credentials() -> Tuple[bytes, bytes]:
    """Generates an in-memory test RSA key and self-signed X.509 certificate for test execution."""
    global _test_cert_cache
    if _test_cert_cache is not None:
        return _test_cert_cache

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "E-Sign Platform Test Authority"),
        x509.NameAttribute(NameOID.COMMON_NAME, "E-Sign Test Signing Authority"),
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
            x509.BasicConstraints(ca=False, path_length=None),
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

    _test_cert_cache = (cert_pem, key_pem)
    return _test_cert_cache


def load_signing_credentials() -> Tuple[bytes, bytes, Optional[str]]:
    """
    Loads signing certificate and private key in memory from settings / environment.
    If credentials are not provided in settings, generates test credentials in non-production.
    Raises PAdESConfigurationError if credentials cannot be resolved.
    """
    cert_b64 = getattr(settings, "PADES_SIGNING_CERT_BASE64", None)
    key_b64 = getattr(settings, "PADES_SIGNING_KEY_BASE64", None)
    passphrase = getattr(settings, "PADES_PASSPHRASE", None)

    if cert_b64 and key_b64:
        try:
            cert_bytes = base64.b64decode(cert_b64)
            key_bytes = base64.b64decode(key_b64)
            return cert_bytes, key_bytes, passphrase
        except Exception as e:
            logger.exception("Failed to decode PAdES Base64 credentials")
            raise PAdESConfigurationError(f"Invalid Base64 credentials for PAdES: {e}")

    # Fallback to test credentials in development / test environments
    if getattr(settings, "DEBUG", True) or getattr(settings, "TESTING", False) or not getattr(settings, "A08_PADES_REQUIRE_PROD_CREDS", False):
        logger.info("[PAdES] Using ephemeral in-memory test signing credentials")
        cert_pem, key_pem = generate_test_credentials()
        return cert_pem, key_pem, None

    raise PAdESConfigurationError("PAdES is enabled but required signing credentials are not configured.")


def sign_pdf_pades(
    pdf_bytes: bytes,
    cert_pem: Optional[bytes] = None,
    key_pem: Optional[bytes] = None,
    passphrase: Optional[str] = None,
    reason: str = "Digital Signature and Document Integrity Seal",
    location: str = "E-Sign Platform",
    field_name: str = "PlatformSignature",
    timestamper: Optional[Any] = None,
) -> bytes:
    """
    Applies an ETSI PAdES-B-B cryptographic signature to the finalized PDF bytes.
    The operation is executed fully in memory using pyHanko and returns signed PDF bytes.
    """
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        raise PAdESError("Invalid PDF bytes provided for PAdES signing.")

    # Check configuration validity: TSA cannot be enabled without PAdES
    if getattr(settings, "A08_TSA_ENABLED", False) and not getattr(settings, "A08_PADES_ENABLED", False):
        raise PAdESConfigurationError("Invalid configuration: A08_TSA_ENABLED cannot be True when A08_PADES_ENABLED is False.")

    if timestamper is None and getattr(settings, "A08_TSA_ENABLED", False):
        from services.timestamp_service import get_timestamper
        timestamper = get_timestamper()

    if cert_pem is None or key_pem is None:
        cert_pem, key_pem, passphrase = load_signing_credentials()

    try:
        signing_key = load_private_key_from_pemder_data(key_pem, passphrase=passphrase.encode("utf-8") if passphrase else None)
        signing_certs = list(load_certs_from_pemder_data(cert_pem))
    except Exception as e:
        logger.exception("Failed to parse PAdES cryptographic key or certificate")
        raise PAdESConfigurationError(f"Failed to parse signing key/certificate: {e}")

    if not signing_certs:
        raise PAdESConfigurationError("No certificates found in provided certificate data.")

    signer = signers.SimpleSigner(
        signing_cert=signing_certs[0],
        signing_key=signing_key,
        cert_registry=signing_certs,
    )

    try:
        inf = io.BytesIO(pdf_bytes)
        w = IncrementalPdfFileWriter(inf)
        fields.append_signature_field(
            w,
            sig_field_spec=fields.SigFieldSpec(sig_field_name=field_name),
        )

        out = io.BytesIO()
        meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            subfilter=fields.SigSeedSubFilter.PADES,
            reason=reason,
            location=location,
        )

        pdf_signer = signers.PdfSigner(meta, signer=signer, timestamper=timestamper)
        pdf_signer.sign_pdf(w, output=out)

        signed_bytes = out.getvalue()
        logger.info("[PAdES] Successfully applied PAdES signature: output size=%d bytes", len(signed_bytes))
        return signed_bytes
    except Exception as e:
        logger.exception("PAdES signing execution failed: %s", e)
        raise PAdESError(f"PAdES cryptographic signature failed: {e}")


def verify_pades_signature(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Validates embedded PAdES digital signatures inside a PDF binary.
    Evaluates signature existence, mathematical integrity, ByteRange digest match,
    and signer certificate metadata.
    """
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return {
            "is_signed": False,
            "signature_valid": False,
            "intact": False,
            "reason": "Invalid or missing PDF data",
        }

    try:
        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        embedded_sigs = reader.embedded_signatures
        if not embedded_sigs:
            return {
                "is_signed": False,
                "signature_valid": False,
                "intact": False,
                "signature_count": 0,
                "reason": "No embedded cryptographic signatures found in PDF",
            }

        results = []
        all_valid = True
        all_intact = True

        for sig in embedded_sigs:
            try:
                val_status = validate_pdf_signature(sig)
                intact = bool(val_status.intact)
                valid = bool(val_status.valid)
                if not intact or not valid:
                    all_valid = False
                    all_intact = False

                cert_subject = None
                if val_status.signing_cert:
                    cert_subject = val_status.signing_cert.subject.human_friendly

                ts_validity = getattr(val_status, "timestamp_validity", None)
                is_timestamped = ts_validity is not None
                ts_valid = False
                ts_time = None
                if is_timestamped:
                    ts_valid = bool(ts_validity.valid) and bool(ts_validity.intact)
                    if ts_validity.timestamp:
                        ts_time = ts_validity.timestamp.isoformat()
                    if not ts_valid:
                        all_valid = False
                        all_intact = False

                results.append({
                    "field_name": sig.field_name,
                    "intact": intact,
                    "valid": valid,
                    "signer_subject": cert_subject,
                    "is_timestamped": is_timestamped,
                    "timestamp_valid": ts_valid,
                    "timestamp_time": ts_time,
                    "pades_type": "PAdES-B-T" if is_timestamped else "PAdES-B-B",
                })
            except Exception as e:
                all_valid = False
                all_intact = False
                results.append({
                    "field_name": sig.field_name,
                    "intact": False,
                    "valid": False,
                    "error": str(e),
                })

        return {
            "is_signed": True,
            "signature_valid": all_valid,
            "intact": all_intact,
            "signature_count": len(embedded_sigs),
            "signatures": results,
            "reason": "PAdES cryptographic signatures intact and valid" if (all_valid and all_intact) else "Cryptographic signature validation failed or document tampered",
        }
    except Exception as e:
        logger.warning("[PAdES] Failed to parse signatures from PDF: %s", e)
        return {
            "is_signed": False,
            "signature_valid": False,
            "intact": False,
            "reason": f"PDF signature validation error: {e}",
        }

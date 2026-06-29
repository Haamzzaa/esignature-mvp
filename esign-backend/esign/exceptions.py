"""
Exception hierarchy for the E-Signature Platform.

Provides typed exception classes so that:
- Logging is consistent and categorized across the codebase.
- A future centralized Exception-to-HTTP mapper can translate them
  to appropriate HTTP status codes without touching business logic.

Current exceptions:
    InvalidStateTransition      — existing, preserved for backward compatibility.
    ESignBaseError              — root of all new typed exceptions.
    ESignValidationError        — input validation failure (→ 400/422).
    ESignAuthorizationError     — permission denied (→ 403).
    ESignNotFoundError          — resource not found (→ 404).
    ESignBusinessRuleViolation  — workflow or business rule prevented action (→ 409).
    ESignProviderError          — a configured provider failed (→ 502).
    ESignExternalServiceError   — upstream/external service unavailable (→ 503).
    ESignConfigurationError     — missing or invalid configuration (→ 500).
"""
from __future__ import annotations


# ── Backward-compatible ───────────────────────────────────────────────────────

class InvalidStateTransition(Exception):
    """Raised when an invalid status transition is attempted on an Envelope."""
    pass


# ── Base ──────────────────────────────────────────────────────────────────────

class ESignBaseError(Exception):
    """
    Root typed exception for the E-Signature module.

    Attributes:
        message:    Human-readable description.
        category:   Machine-readable category string for log classification.
        detail:     Optional extra context (dict or str).
    """
    category: str = "esign_error"

    def __init__(self, message: str, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        if self.detail:
            return f"[{self.category}] {self.message} — {self.detail}"
        return f"[{self.category}] {self.message}"


# ── Typed subclasses ──────────────────────────────────────────────────────────

class ESignValidationError(ESignBaseError):
    """Input failed validation. Suitable for HTTP 400 or 422."""
    category = "validation_error"


class ESignAuthorizationError(ESignBaseError):
    """Authorization denied. Suitable for HTTP 403."""
    category = "authorization_error"


class ESignNotFoundError(ESignBaseError):
    """Requested resource not found. Suitable for HTTP 404."""
    category = "not_found"


class ESignBusinessRuleViolation(ESignBaseError):
    """A workflow or business rule prevented the requested action. Suitable for HTTP 409."""
    category = "business_rule_violation"


class ESignProviderError(ESignBaseError):
    """A configured provider (OCR, face, notification, etc.) returned an error. Suitable for HTTP 502."""
    category = "provider_error"


class ESignExternalServiceError(ESignBaseError):
    """An upstream or external service is unreachable or returned an unexpected response. Suitable for HTTP 503."""
    category = "external_service_error"


class ESignConfigurationError(ESignBaseError):
    """Missing or invalid configuration prevented the operation from completing. Suitable for HTTP 500."""
    category = "configuration_error"

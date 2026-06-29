"""
Health Service for the E-Signature Platform.

Provides all the health, readiness and liveness check logic,
keeping views thin and this module testable in isolation.
"""
from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from datetime import datetime

from django.conf import settings
from esign.request_context import get_request_id

logger = logging.getLogger("esign.health")

# Module metadata (kept lightweight; no heavy imports)
MODULE_NAME = "esignature"
MODULE_VERSION = "1.0.0"


def _check_database() -> dict:
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        logger.error("[HealthService] Database check failed: %s", exc)
        return {"status": "error", "detail": "Database connectivity failed"}


def _check_storage() -> dict:
    try:
        import os
        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root and not os.path.isdir(str(media_root)):
            os.makedirs(str(media_root), exist_ok=True)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("[HealthService] Storage check failed: %s", exc)
        return {"status": "error", "detail": "Storage accessibility failed"}


def _check_config() -> dict:
    try:
        from esign.config import esign_config
        esign_config.validate()
        return {"status": "ok"}
    except Exception as exc:
        logger.error("[HealthService] Config validation failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_event_dispatcher() -> dict:
    try:
        from esign.events.dispatcher import esign_dispatcher
        handler_count = sum(len(v) for v in esign_dispatcher._handlers.values())
        return {"status": "ok", "registered_handlers": handler_count}
    except Exception as exc:
        logger.error("[HealthService] Event dispatcher check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _check_providers() -> dict:
    try:
        from esign.providers.registry import esign_provider_registry
        initialized = []
        errors = []

        for name, prop in [
            ("ocr", "ocr_provider"),
            ("notification", "notification_provider"),
            ("storage", "storage_provider"),
        ]:
            try:
                getattr(esign_provider_registry, prop)
                initialized.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")

        if errors:
            return {
                "status": "degraded",
                "initialized": initialized,
                "errors": errors,
            }
        return {"status": "ok", "initialized": initialized}
    except Exception as exc:
        logger.error("[HealthService] Provider registry check failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def _build_metadata() -> dict:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "timestamp": datetime.now(dt_timezone.utc).isoformat(),
        "request_id": get_request_id(),
    }


def _agg_status(checks: dict) -> str:
    statuses = [v.get("status", "ok") for v in checks.values() if isinstance(v, dict)]
    if "error" in statuses:
        return "error"
    if "degraded" in statuses:
        return "degraded"
    return "ok"


def liveness_check() -> dict:
    """
    Always returns status=ok while the process is running.
    Suitable for Kubernetes/Docker liveness probes.
    """
    return {
        "status": "ok",
        **_build_metadata(),
    }


def readiness_check() -> dict:
    """
    Verifies the application is ready to serve traffic.
    Checks: database, storage, configuration, event dispatcher, providers.
    """
    checks = {
        "database": _check_database(),
        "storage": _check_storage(),
        "config": _check_config(),
        "event_dispatcher": _check_event_dispatcher(),
        "providers": _check_providers(),
    }

    return {
        "status": _agg_status(checks),
        "checks": checks,
        **_build_metadata(),
    }


def full_health_check() -> dict:
    """
    Comprehensive health check including all subsystem diagnostics.
    Superset of readiness_check with additional provider detail.
    """
    checks = {
        "database": _check_database(),
        "storage": _check_storage(),
        "config": _check_config(),
        "event_dispatcher": _check_event_dispatcher(),
        "providers": _check_providers(),
    }

    return {
        "status": _agg_status(checks),
        "checks": checks,
        **_build_metadata(),
    }

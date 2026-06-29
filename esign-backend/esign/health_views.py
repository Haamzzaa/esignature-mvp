"""
Health endpoint views for the E-Signature Platform.

Views are intentionally thin — all logic lives in esign.health_service.
No authentication required (operational use by load balancers and orchestrators).
"""
from django.http import JsonResponse
from esign.health_service import liveness_check, readiness_check, full_health_check


def live_view(request):
    """GET /live — liveness probe (always 200 when process is running)."""
    data = liveness_check()
    return JsonResponse(data, status=200)


def ready_view(request):
    """GET /ready — readiness probe (200 when ready, 503 when not)."""
    data = readiness_check()
    http_status = 200 if data["status"] == "ok" else 503
    return JsonResponse(data, status=http_status)


def health_view(request):
    """GET /health — full diagnostics (200 ok, 207 degraded, 503 error)."""
    data = full_health_check()
    status_map = {"ok": 200, "degraded": 207, "error": 503}
    http_status = status_map.get(data["status"], 200)
    return JsonResponse(data, status=http_status)

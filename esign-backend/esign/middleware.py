"""
Middleware for the E-Signature Platform.

RequestIDMiddleware  — generates/propagates X-Request-ID per request.
RequestTimingMiddleware — logs every request with method, path, status, duration.
"""
import time
import uuid
import logging

from esign.request_context import set_request_id, get_request_id, clear_request_id

logger = logging.getLogger("esign.middleware")

_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
_RESPONSE_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """
    Generates (or propagates) a UUID v4 correlation ID for every request.

    - Reads X-Request-ID from the incoming request if provided by a proxy.
    - Falls back to generating a fresh UUID v4.
    - Stores the ID in thread-local storage so all downstream code can
      call ``get_request_id()`` without needing access to the request object.
    - Injects the ID into the response as the X-Request-ID header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Re-use upstream ID (e.g. load-balancer) or create a new one
        request_id = request.META.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
        set_request_id(request_id)
        # Expose on request for convenient view access
        request.request_id = request_id

        try:
            response = self.get_response(request)
        finally:
            clear_request_id()

        response[_RESPONSE_HEADER] = request_id
        return response


class RequestTimingMiddleware:
    """
    Logs every HTTP request with method, path, response status, and duration.

    Emits a single INFO-level log line per request:
        [Request] GET /api/v1/packages/ → 200 in 42ms [req_id=…]

    This does NOT modify API responses.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Strip query string for cleaner logs
        path = request.path
        method = request.method
        status_code = response.status_code
        request_id = get_request_id()

        logger.info(
            "[Request] %s %s → %s in %dms",
            method,
            path,
            status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )

        return response


class BrowserSecurityMiddleware:
    """
    Injects production-grade HTTP security headers, clickjacking protections,
    MIME sniffing prevention, Permissions Policy, and sensitive browser cache controls.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # 1. Content Security Policy (CSP)
        from django.conf import settings
        csp_config = getattr(settings, 'ESIGN_CSP', {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            "font-src": ["'self'", "https://fonts.gstatic.com"],
            "img-src": ["'self'", "data:", "blob:"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"]
        })
        
        csp_header = "; ".join(f"{directive} {' '.join(sources)}" for directive, sources in csp_config.items())
        response['Content-Security-Policy'] = csp_header

        # 2. Clickjacking Protection
        response['X-Frame-Options'] = 'DENY'

        # 3. MIME Sniffing Protection
        response['X-Content-Type-Options'] = 'nosniff'

        # 4. Referrer Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # 5. Permissions Policy (Allow camera for local face verification)
        response['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=(), payment=(), usb=(), fullscreen=(self)'

        # 6. Cross-Origin Policies
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'

        # 7. Browser Cache Protections for sensitive views
        path = request.path
        if any(keyword in path for keyword in ['/api/sign/', '/participants/', '/media/', '/api/v1/login/']):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

        return response


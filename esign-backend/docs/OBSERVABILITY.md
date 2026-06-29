# Observability Foundation

This document details the telemetry, request correlation, health checks, performance diagnostics, and sensitive data logging controls implemented for the E-Signature module.

---

## 1. Request Correlation (Request ID)

The module implements a request correlation mechanism using `X-Request-ID`. This enables distributed tracing and cross-layer log correlation across views, service boundaries, and event handlers.

- **Generation & Propagation**: The `RequestIDMiddleware` generates a unique UUID v4 for each incoming request. If an upstream proxy (such as a load balancer or gateway) already provides an `X-Request-ID` header, it is preserved and propagated.
- **Context Access**: The request ID is stored in a thread-local context (`esign/request_context.py`) at the start of each request and cleared at response teardown. This allows service layers, provider registries, and event handlers to log the correlation ID without direct access to the HTTP request object.
- **Response Headers**: The correlation ID is injected into the response headers as `X-Request-ID` and is exposed to the frontend clients via CORS configuration.

---

## 2. Console-First Structured Logging

Logging has been updated to support structured formats suitable for cloud runtime environments (e.g. AWS, Azure App Service, Kubernetes, Railway, Render).

- **Stdout-First Default**: By default, logs are written directly to stdout using Python's standard `logging` library.
- **Dynamic Configuration**:
  - `ESIGN_LOG_LEVEL`: Controls the logging level (default: `INFO`).
  - `ESIGN_LOG_FILE_ENABLED`: Set to `True` to enable optional rotating file logs.
  - `ESIGN_LOG_FILE_PATH`: Custom path for file logs (default: `logs/esign.log`).
- **Format**:
  ```
  %(asctime)s [%(levelname)s] [%(request_id)s] %(name)s %(message)s
  ```

---

## 3. Health & Diagnostic Probes

Three endpoints are exposed under the root URL namespace to support liveness, readiness, and diagnostics:

1. **Liveness Check (`GET /live`)**
   - Returns `200 OK` with basic module metadata. Useful for process sanity checks.
2. **Readiness Check (`GET /ready`)**
   - Performs connectivity checks on dependency targets (Database, Storage, Configuration Registry, Provider Registry, Event Dispatcher). Returns `200 OK` if all checks pass, and `503 Service Unavailable` if a degraded/failed dependency is detected.
3. **Full Health Diagnostic (`GET /health`)**
   - Superset of readiness checks. Returns a detailed report of subsystem diagnostic statuses.

*Note: Health endpoints are thin views that delegate all checking logic to the decoupled `esign.health_service`.*

---

## 4. Performance Timing & Subsystem Diagnostics

- **Timing Context**: A lightweight context manager (`esign/timing.py`) computes elapsed milliseconds for performance-critical tasks and logs the duration.
- **Subsystem Coverage**:
  - **OCR Extraction & Matching**: Measures duration of document preprocessing and rapidfuzz matching steps.
  - **Biometrics & Liveness**: Logs similarity calculations and liveness check timings.
  - **Certificate Generation**: Monitors completion certificate timeline rendering and assembly.
  - **Webhook Delivery**: Tracks delivery duration per subscription URL, recording HTTP status and failures.

---

## 5. Sensitive Data Audit (PII Protection)

A comprehensive audit was performed to ensure that no sensitive data (PII or credentials) is logged by the observability layer.

- **OTP Secrets**: Never logged. OTP generation and verification operations only log success or failure status.
- **API Tokens**: Sanitized from views, request loggers, and exception details.
- **National IDs**: Scored name candidates and document numbers are masked before any log emission (e.g. `******1234`).
- **Raw Face Embeddings & Images**: Never logged or saved in stdout log records.

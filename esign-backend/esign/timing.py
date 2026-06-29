"""
Performance timing utilities for the E-Signature Platform.

Provides a context manager that measures wall-clock duration of
critical operations and emits a structured log line on completion.

Usage:
    from esign.timing import timed_operation

    with timed_operation("ocr_extraction", logger, envelope_id=42):
        result = perform_ocr(image_bytes)
"""
import time
import logging
from contextlib import contextmanager
from esign.request_context import get_request_id


@contextmanager
def timed_operation(label: str, op_logger: logging.Logger, **context):
    """
    Context manager that logs the elapsed time for a named operation.

    Args:
        label:      Human-readable operation name (e.g. "face_matching").
        op_logger:  Logger instance to emit the timing line.
        **context:  Optional key=value pairs appended to the log (e.g. envelope_id=5).
    """
    start = time.perf_counter()
    try:
        yield
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        op_logger.info(
            "[Timing] %s completed in %dms %s",
            label,
            elapsed_ms,
            ctx_str,
            extra={"request_id": get_request_id()},
        )
    except Exception:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        op_logger.warning(
            "[Timing] %s failed after %dms %s",
            label,
            elapsed_ms,
            ctx_str,
            extra={"request_id": get_request_id()},
        )
        raise

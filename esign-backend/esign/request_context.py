"""
Request Context: thread-local storage for request_id propagation.
Used by middleware, views, services, and event handlers to
enrich log records with a correlation ID.
"""
import threading

_local = threading.local()


def set_request_id(request_id: str) -> None:
    """Store the current request's correlation ID in thread-local."""
    _local.request_id = request_id


def get_request_id() -> str:
    """Retrieve the current request's correlation ID, or 'no-request-id' if unset."""
    return getattr(_local, "request_id", "no-request-id")


def clear_request_id() -> None:
    """Clear the thread-local request ID (called on response teardown)."""
    if hasattr(_local, "request_id"):
        del _local.request_id

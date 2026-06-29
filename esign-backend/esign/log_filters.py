"""
Log Filters: attaches request_id to every log record so that
the %(request_id)s format specifier is always available in
formatter strings, regardless of where the log is emitted.
"""
import logging
from esign.request_context import get_request_id


class RequestIDFilter(logging.Filter):
    """
    Injects the current request's correlation ID into every LogRecord.
    Attach to handlers or loggers via the LOGGING setting.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True

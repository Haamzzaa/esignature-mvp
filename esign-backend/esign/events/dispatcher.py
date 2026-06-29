import time
import logging
from esign.config import esign_config
from esign.events.base import DomainEvent
from esign.request_context import get_request_id

logger = logging.getLogger("esign.events.dispatcher")

class EventDispatcher:
    """
    Central dispatcher coordinating registering of handlers and synchronous execution of events.
    Isolates errors in individual handlers to protect core execution paths.
    """
    def __init__(self):
        self._handlers = {}

    def register(self, event_name: str, handler):
        """
        Registers a callback handler for a specific event_name (or '*' for all events).
        """
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    def publish(self, event: DomainEvent):
        """
        Publishes a DomainEvent, executing all registered handlers synchronously.
        Logs per-handler timing and isolates failures.
        """
        if not esign_config.events_enabled:
            return

        request_id = get_request_id()
        handlers = self._handlers.get(event.event_name, [])
        handlers_wildcard = self._handlers.get("*", [])
        all_handlers = list(handlers) + list(handlers_wildcard)

        if esign_config.event_logging_enabled:
            logger.info(
                "[EventDispatcher] Publishing event=%s handlers=%d request_id=%s",
                event.event_name,
                len(all_handlers),
                request_id,
            )

        failures = 0
        for handler in all_handlers:
            handler_name = handler.__name__ if hasattr(handler, '__name__') else str(handler)
            start = time.perf_counter()
            try:
                handler(event)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.debug(
                    "[EventDispatcher] Handler completed: handler=%s event=%s duration=%dms",
                    handler_name,
                    event.event_name,
                    elapsed_ms,
                )
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                failures += 1
                logger.error(
                    "[EventDispatcher] Handler failed: handler=%s event=%s error=%s duration=%dms",
                    handler_name,
                    event.event_name,
                    str(e),
                    elapsed_ms,
                    exc_info=True,
                )

        if failures:
            logger.warning(
                "[EventDispatcher] Event %s completed with %d/%d handler failures request_id=%s",
                event.event_name,
                failures,
                len(all_handlers),
                request_id,
            )

# Central singleton instance
esign_dispatcher = EventDispatcher()

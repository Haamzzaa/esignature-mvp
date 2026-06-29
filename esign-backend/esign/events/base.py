from datetime import datetime

class DomainEvent:
    """
    Abstract base class for all domain events in the E-Signature module.
    """
    def __init__(self, event_name: str, payload: dict):
        self.event_name = event_name
        self.payload = payload
        self.timestamp = datetime.utcnow().isoformat()

    def __str__(self):
        return f"Event {self.event_name} generated at {self.timestamp}"

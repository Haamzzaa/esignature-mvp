import time
import logging
from esign.config import esign_config
from esign.events.base import DomainEvent

logger = logging.getLogger("esign.events.handlers")

def handle_envelope_sent(event: DomainEvent):
    """
    Built-in handler to dispatch package sent email notification.
    """
    from services.email_dispatch import dispatch_package_sent_notification
    envelope_id = event.payload.get("envelope_id")
    base_api_url = event.payload.get("base_api_url")
    logger.info("[Handler] handle_envelope_sent: envelope_id=%s", envelope_id)
    try:
        dispatch_package_sent_notification(envelope_id, base_api_url)
    except Exception:
        logger.exception("[Handler] Failed to dispatch package sent notification for envelope %s", envelope_id)

def handle_envelope_completed(event: DomainEvent):
    """
    Built-in handler to generate completion certificate and dispatch final completion email.
    """
    from esign.models import Envelope
    from services.certificate_service import generate_certificate
    from services.email_dispatch import dispatch_completion_email
    from esign.timing import timed_operation

    envelope_id = event.payload.get("envelope_id")
    base_api_url = event.payload.get("base_api_url")

    try:
        envelope = Envelope.objects.get(id=envelope_id)
    except Envelope.DoesNotExist:
        logger.error("[Handler] Envelope %s not found for completion handler.", envelope_id)
        return

    cert_id = None
    try:
        with timed_operation("certificate_generation", logger, envelope_id=envelope_id):
            cert_obj = generate_certificate(envelope)
            cert_id = cert_obj.certificate_id
        logger.info("[Handler] Certificate generated: cert_id=%s envelope_id=%s", cert_id, envelope_id)
    except Exception:
        logger.exception("[Handler] Failed to generate certificate for envelope %s", envelope_id)

    try:
        logger.info("[Handler] Dispatching completion email: envelope_id=%s cert_id=%s", envelope_id, cert_id)
        dispatch_completion_email(envelope_id, cert_id, base_api_url)
    except Exception:
        logger.exception("[Handler] Failed to dispatch completion email for envelope %s", envelope_id)

def handle_next_workflow_step(event: DomainEvent):
    """
    Built-in handler to send email notification to the active signer of the next step.
    """
    from services.email_dispatch import dispatch_next_step_notification
    envelope_id = event.payload.get("envelope_id")
    step_number = event.payload.get("step_number")
    base_api_url = event.payload.get("base_api_url")
    if step_number is not None:
        logger.info("[Handler] handle_next_workflow_step: envelope_id=%s step=%s", envelope_id, step_number)
        try:
            dispatch_next_step_notification(envelope_id, step_number, base_api_url)
        except Exception:
            logger.exception("[Handler] Failed to dispatch next step notification for envelope %s", envelope_id)

def handle_audit_logging(event: DomainEvent):
    """
    Built-in handler for logging events to audit trail logs.
    """
    from esign.models import AuditLog, Envelope
    envelope_id = event.payload.get("envelope_id")
    if envelope_id:
        try:
            envelope = Envelope.objects.get(id=envelope_id)
            event_action = event.event_name.split('.')[-1]
            AuditLog.objects.create(
                envelope=envelope,
                event=event_action,
                ip_address=event.payload.get("ip_address"),
                user_agent=event.payload.get("user_agent")
            )
            logger.info("[Handler] Saved audit log: envelope_id=%s action=%s", envelope_id, event_action)
        except Envelope.DoesNotExist:
            pass

def handle_webhooks(event: DomainEvent):
    """
    Built-in handler to deliver webhooks to registered endpoints.
    Logs destination host, HTTP status, delivery duration, and failure reason.
    """
    if not esign_config.webhooks_enabled:
        return

    from esign.models import WebhookSubscription
    subscriptions = WebhookSubscription.objects.filter(is_active=True)
    if not subscriptions.exists():
        return

    import requests
    import json
    from urllib.parse import urlparse

    payload = {
        "event": event.event_name,
        "timestamp": event.timestamp,
        "data": event.payload
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"{esign_config.module_name.capitalize()}-Webhook-Dispatcher/{esign_config.api_version}"
    }

    for sub in subscriptions:
        if "*" in sub.events or event.event_name in sub.events:
            host = urlparse(sub.url).netloc
            start = time.perf_counter()
            try:
                response = requests.post(
                    sub.url,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=esign_config.webhook_timeout
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info(
                    "[Webhook] Delivered: event=%s host=%s status=%d duration=%dms",
                    event.event_name,
                    host,
                    response.status_code,
                    elapsed_ms,
                )
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.error(
                    "[Webhook] Delivery failed: event=%s host=%s error=%s duration=%dms",
                    event.event_name,
                    host,
                    str(e),
                    elapsed_ms,
                )

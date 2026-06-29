import logging
from esign.config import esign_config
from esign.models import Envelope

logger = logging.getLogger(__name__)

def dispatch_package_sent_notification(envelope_id, base_api_url=None):
    if esign_config.use_celery:
        from services.tasks import send_package_sent_notifications_task
        send_package_sent_notifications_task.delay(envelope_id, base_api_url)
    else:
        from services.notification_service import send_package_sent_notifications
        try:
            envelope = Envelope.objects.get(id=envelope_id)
            send_package_sent_notifications(envelope, base_api_url)
        except Envelope.DoesNotExist:
            logger.error(f"Envelope {envelope_id} not found for package sent notification.")

def dispatch_next_step_notification(envelope_id, step_number, base_api_url=None):
    if esign_config.use_celery:
        from services.tasks import send_next_step_notifications_task
        send_next_step_notifications_task.delay(envelope_id, step_number, base_api_url)
    else:
        from services.notification_service import send_next_step_notifications
        try:
            envelope = Envelope.objects.get(id=envelope_id)
            send_next_step_notifications(envelope, step_number, base_api_url)
        except Envelope.DoesNotExist:
            logger.error(f"Envelope {envelope_id} not found for next step notification.")

def dispatch_completion_email(envelope_id, certificate_id=None, base_api_url=None):
    if esign_config.use_celery:
        from services.tasks import send_completion_email_task
        send_completion_email_task.delay(envelope_id, certificate_id, base_api_url)
    else:
        from services.notification_service import send_completion_email
        try:
            envelope = Envelope.objects.get(id=envelope_id)
            send_completion_email(envelope, certificate_id, base_api_url)
        except Envelope.DoesNotExist:
            logger.error(f"Envelope {envelope_id} not found for completion email.")

import logging

from celery import shared_task

from esign.models import Envelope
from services.notification_service import (send_completion_email,
                                           send_next_step_notifications,
                                           send_package_sent_notifications)

logger = logging.getLogger(__name__)

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_package_sent_notifications_task(envelope_id, base_api_url=None):
    try:
        envelope = Envelope.objects.get(id=envelope_id)
        send_package_sent_notifications(envelope, base_api_url)
    except Envelope.DoesNotExist:
        logger.error("Envelope %s not found for package sent notifications.", envelope_id)

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_next_step_notifications_task(envelope_id, step_number, base_api_url=None):
    try:
        envelope = Envelope.objects.get(id=envelope_id)
        send_next_step_notifications(envelope, step_number, base_api_url)
    except Envelope.DoesNotExist:
        logger.error("Envelope %s not found for next step notifications.", envelope_id)

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_completion_email_task(envelope_id, certificate_id=None, base_api_url=None):
    try:
        envelope = Envelope.objects.get(id=envelope_id)
        send_completion_email(envelope, certificate_id, base_api_url)
    except Envelope.DoesNotExist:
        logger.error("Envelope %s not found for completion email.", envelope_id)

from esign.providers.base import BaseNotificationProvider
from django.core.mail import send_mail
from esign.config import esign_config

class SMTPEmailNotificationProvider(BaseNotificationProvider):
    """
    SMTP Email notification dispatcher wrapping standard django send_mail.
    """
    def send_notification(self, recipient: str, subject: str, body: str) -> bool:
        send_mail(
            subject=subject,
            message=body,
            from_email=esign_config.default_from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True

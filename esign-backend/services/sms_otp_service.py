"""
SMS OTP Service — Architectural Foundation

This module defines the interface contract for SMS OTP providers.
No external provider is integrated at this stage.

Future Saudi SMS integrations (Unifonic, Infobip, etc.) should implement
SMSOTPProvider and be registered via a concrete subclass.
"""


class SMSOTPProvider:
    """
    Abstract interface for SMS OTP delivery providers.

    Concrete implementations must override send_otp().
    """

    def send_otp(self, phone_number: str, otp: str) -> None:
        """
        Sends the given OTP to the specified phone number.

        Args:
            phone_number: E.164 formatted phone number (e.g. "+966501234567").
            otp: The one-time password string to deliver.

        Raises:
            NotImplementedError: Always, until a provider is implemented.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement send_otp()."
        )

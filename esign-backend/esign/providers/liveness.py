from esign.providers.base import BaseLivenessProvider
from services.liveness_service import LivenessResult

class PlaceholderLivenessProvider(BaseLivenessProvider):
    """
    Placeholder check verifying selfie liveness checks.
    """
    def check_liveness(self, selfie_image_bytes: bytes) -> LivenessResult:
        import services.liveness_service
        return services.liveness_service.perform_liveness_check(selfie_image_bytes)

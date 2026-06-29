from esign.providers.base import BaseFaceMatchingProvider

class InsightFaceMatchingProvider(BaseFaceMatchingProvider):
    """
    Facial recognition similarity using the InsightFace buffalo_l engine.
    """
    def calculate_similarity(self, image1_bytes: bytes, image2_bytes: bytes) -> float:
        import services.face_matching_service
        return services.face_matching_service.calculate_face_similarity(image1_bytes, image2_bytes)

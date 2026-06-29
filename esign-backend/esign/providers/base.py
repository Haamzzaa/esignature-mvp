from abc import ABC, abstractmethod
from services.liveness_service import LivenessResult

class BaseOCRProvider(ABC):
    @abstractmethod
    def extract_text(self, pdf_bytes: bytes) -> dict:
        pass

class BaseFaceMatchingProvider(ABC):
    @abstractmethod
    def calculate_similarity(self, image1_bytes: bytes, image2_bytes: bytes) -> float:
        pass

class BaseLivenessProvider(ABC):
    @abstractmethod
    def check_liveness(self, selfie_image_bytes: bytes) -> LivenessResult:
        pass

class BaseNotificationProvider(ABC):
    @abstractmethod
    def send_notification(self, recipient: str, subject: str, body: str) -> bool:
        pass

class BaseStorageProvider(ABC):
    @abstractmethod
    def save(self, name: str, content: bytes) -> str:
        pass
    
    @abstractmethod
    def exists(self, name: str) -> bool:
        pass

class BaseCertificateProvider(ABC):
    @abstractmethod
    def generate_certificate(self, envelope_id: int) -> bytes:
        pass

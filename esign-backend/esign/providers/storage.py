from esign.providers.base import BaseStorageProvider
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

class DjangoStorageProvider(BaseStorageProvider):
    """
    Standard django default_storage engine abstraction.
    """
    def save(self, name: str, content: bytes) -> str:
        return default_storage.save(name, ContentFile(content))
        
    def exists(self, name: str) -> bool:
        return default_storage.exists(name)

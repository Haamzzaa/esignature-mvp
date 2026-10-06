import logging
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from services.upload_service import validate_pdf_upload
from esign.serializers import DocumentUploadSerializer

logger = logging.getLogger(__name__)

class DocumentUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        file = request.data.get('file')
        try:
            validate_pdf_upload(file)
        except ValidationError as e:
            return Response({"file": e.detail}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DocumentUploadSerializer(data=request.data)
        if serializer.is_valid():
            document = serializer.save(owner=request.user)
            try:
                from services.gemini_contract_ocr import \
                    extract_contract_authorization
                extract_contract_authorization(document.file.path, document=document)
            except Exception as e:
                logger.warning(f"Auto contract OCR failed on upload: {e}")
            return Response(
                {
                    "document_id": document.id,
                    "file_hash": document.file_hash
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

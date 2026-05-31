# pyrefly: ignore [missing-import]
from rest_framework import serializers
import hashlib
from .models import Document, Signer, Envelope

class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['file']

    def create(self, validated_data):
        file = validated_data['file']
        hasher = hashlib.sha256()
        for chunk in file.chunks():
            hasher.update(chunk)
        file_hash = hasher.hexdigest()
        document = Document.objects.create(file=file, file_hash=file_hash)
        return document
        
class SignerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signer
        fields = ['name', 'email']

class EnvelopeCreateSerializer(serializers.Serializer):
    document_id       = serializers.IntegerField()
    signer            = SignerSerializer()
    signature_page    = serializers.IntegerField(default=1)
    # Ratio-based placement (0.0–1.0).  Optional — omitted when no position selected.
    signature_x_ratio = serializers.FloatField(allow_null=True, required=False, default=None)
    signature_y_ratio = serializers.FloatField(allow_null=True, required=False, default=None)

    def create(self, validated_data):
        document_id       = validated_data['document_id']
        signer_data       = validated_data['signer']
        signature_page    = validated_data.get('signature_page', 1)
        signature_x_ratio = validated_data.get('signature_x_ratio')
        signature_y_ratio = validated_data.get('signature_y_ratio')

        document = Document.objects.get(id=document_id)
        envelope = Envelope.objects.create(
            document=document,
            signature_page=signature_page,
            signature_x_ratio=signature_x_ratio,
            signature_y_ratio=signature_y_ratio,
        )
        Signer.objects.create(envelope=envelope, **signer_data)
        return envelope

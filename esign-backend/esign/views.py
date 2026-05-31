from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from rest_framework.generics import get_object_or_404  # pyright: ignore[reportMissingImports]
from django.urls import reverse
import hashlib
from django.core.files.base import ContentFile
from django.db import transaction
from .models import Envelope, Signer, SigningToken, AuditLog, SignedDocument
from .serializers import DocumentUploadSerializer, EnvelopeCreateSerializer
from django.http import FileResponse, Http404
import os
import fitz
from io import BytesIO

class DocumentUploadView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = DocumentUploadSerializer(data=request.data)
        if serializer.is_valid():
            document = serializer.save()
            return Response(
                {
                    "document_id": document.id,
                    "file_hash": document.file_hash
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EnvelopeCreateView(APIView):
    def post(self, request, *args, **kwargs):
        # ── Mandatory Placement Validation ───────────────────────────────────
        sig_page = request.data.get('signature_page')
        sig_x = request.data.get('signature_x_ratio')
        sig_y = request.data.get('signature_y_ratio')
        
        if sig_page is None or sig_x is None or sig_y is None:
            return Response(
                {"detail": "Signature placement is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = EnvelopeCreateSerializer(data=request.data)
        if serializer.is_valid():
            envelope = serializer.save()
            return Response(
                {
                    "envelope_id": envelope.id,
                    "status": envelope.status
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SendEnvelopeView(APIView):
    def post(self, request, envelope_id, *args, **kwargs):
        envelope = get_object_or_404(Envelope, id=envelope_id)
        signer = get_object_or_404(Signer, envelope=envelope)
        expires_at = timezone.now() + timedelta(hours=24)

        signing_token, created = SigningToken.objects.get_or_create(
            signer=signer,
            defaults={
                "expires_at": expires_at,
                "is_used": False,
            },
        )
        if not created:
            signing_token.expires_at = expires_at
            signing_token.is_used = False
            signing_token.save()

        envelope.status = "sent"
        envelope.save()

        AuditLog.objects.create(
            envelope=envelope,
            event="sent",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        from django.conf import settings
        signing_url = f"{settings.FRONTEND_URL}/sign/{signing_token.token}"

        
        return Response(
            {
                "message": "Envelope sent to signer.",
                "signing_url": signing_url,
                "expires_at": expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )

class SigningDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        signing_token = get_object_or_404(SigningToken, token=token)
        if signing_token.expires_at < timezone.now():
            return Response({'detail': 'Token expired.'}, status=status.HTTP_400_BAD_REQUEST)
        
        signer = signing_token.signer
        envelope = signer.envelope
        document = envelope.document
        
        if not document.file:
            raise Http404("Document file not found.")
            
        return FileResponse(document.file.open('rb'), content_type='application/pdf')

class SigningSignedDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        signing_token = get_object_or_404(SigningToken, token=token)
        signer = signing_token.signer
        envelope = signer.envelope
        
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        return FileResponse(signed_doc.file.open('rb'), content_type='application/pdf')

class SigningDownloadView(APIView):
    def get(self, request, token, *args, **kwargs):
        signing_token = get_object_or_404(SigningToken, token=token)
        signer = signing_token.signer
        envelope = signer.envelope
        
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        original_name = os.path.basename(signed_doc.file.name) or "signed.pdf"
        
        return FileResponse(
            signed_doc.file.open('rb'),
            as_attachment=True,
            filename=original_name,
            content_type='application/pdf'
        )
   
class SigningView(APIView):
    def get(self, request, token, *args, **kwargs):
        signing_token = SigningToken.objects.filter(token=token).select_related(
            "signer__envelope__document"
        ).first()
        if not signing_token:
            return Response({'detail': 'Invalid token.'}, status=status.HTTP_404_NOT_FOUND)
        if signing_token.expires_at < timezone.now():
            return Response({'detail': 'Token expired.'}, status=status.HTTP_400_BAD_REQUEST)
        signer = signing_token.signer
        envelope = signer.envelope
        document = envelope.document
        try:
            print("TOKEN RECEIVED:", token)
            print("TOKENS IN DB:", list(SigningToken.objects.values_list("token", flat=True)))
        except Exception as e:
            print("DEBUG ERROR:", str(e))
            raise

        # Check if completed/signed
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" and signed_doc:
            AuditLog.objects.create(
                envelope=envelope,
                event="viewed",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )
            
            return Response({
                "signer_name": signer.name,
                "signer_email": signer.email,
                "document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "signed_document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                
                "envelope_id": envelope.id,
                "status": "completed"
            })
        
        AuditLog.objects.create(
            envelope=envelope,
            event="viewed",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )
        if envelope.status != "viewed":
            envelope.status = "viewed"
            envelope.save(update_fields=["status"])

        return Response({
            "signer_name": signer.name,
            "signer_email": signer.email,
            "document_url": request.build_absolute_uri(
                reverse('signing-document', kwargs={'token': token})
            ),
            "envelope_id": envelope.id,
            "status": envelope.status,
        })

    # ── PDF embedding helper ───────────────────────────────────────────────────

    def _embed_signature(
        self, page, sig_type,
        x_ratio=None, y_ratio=None,
        signature_text=None, signature_image_b64=None,
        signer_name=None,
    ):
        """
        Embed the signature onto *page* (a fitz.Page).

        x_ratio / y_ratio — placement ratios in [0.0, 1.0] computed by the
                            frontend as:  click_px / rendered_page_dimension.
                            Multiplied against actual PDF dimensions to get
                            the final PDF coordinate.  No Y-inversion needed
                            because react-pdf and PyMuPDF share a top-left
                            origin in the coordinate space we work in.

        Typed  → inserts a text block at the normalised position.
        Upload / Draw → decodes the base64 image and inserts it centred on
                         the marker.
        """
        import base64

        pdf_h = page.rect.height
        pdf_w = page.rect.width

        # ── Coordinate resolution ────────────────────────────────────────────
        if x_ratio is not None and y_ratio is not None:
            origin_x = float(x_ratio) * pdf_w
            origin_y = float(y_ratio) * pdf_h
        else:
            # No position selected — fall back to bottom-left area of the page
            origin_x = 50
            origin_y = pdf_h - 120

        if sig_type == "typed":
            # Just the signature text itself where they clicked
            text_width_estimate = fitz.get_text_length(
                signature_text,
                fontsize=12,
                fontname="helv",
            )
            centered_x = origin_x - (text_width_estimate / 2)

            page.insert_text(
                (centered_x, origin_y),
                signature_text,
                fontsize=12,
                fontname="helv",
            )

        elif sig_type in ("upload", "draw"):
            # Strip the data-URL prefix if present (e.g. "data:image/png;base64,...")
            if "," in signature_image_b64:
                signature_image_b64 = signature_image_b64.split(",", 1)[1]

            raw_bytes = base64.b64decode(signature_image_b64)

            # ── Pre-process: crop → darken → sharpen ─────────────────────────
            image_bytes = self._preprocess_signature_image(raw_bytes)

            # ── Get processed image dimensions ───────────────────────────────
            from PIL import Image
            from io import BytesIO as _BytesIO
            
            with Image.open(_BytesIO(image_bytes)) as img:
                orig_w, orig_h = img.size

            # ── Proportional scaling ─────────────────────────────────────────
            max_width = 120.0
            max_height = 45.0
            
            # Prevent division by zero
            if orig_w == 0 or orig_h == 0:
                scale_ratio = 1.0
            else:
                scale_ratio = min(max_width / orig_w, max_height / orig_h)

            img_w = orig_w * scale_ratio
            img_h = orig_h * scale_ratio

            # Centred on the marker point so the visual midpoint matches the click.
            x0    = origin_x - img_w / 2
            y0    = origin_y - img_h / 2
            rect  = fitz.Rect(x0, y0, x0 + img_w, y0 + img_h)

            page.insert_image(rect, stream=image_bytes)

        # ── Footer Metadata ──────────────────────────────────────────────────
        # Render metadata separately near the lower left area of the page.
        footer_text = (
            f"Digitally signed by {signer_name or 'Unknown'}\n"
            f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Position at the bottom-left corner
        footer_x = 40
        footer_y = pdf_h - 40
        
        page.insert_text(
            (footer_x, footer_y),
            footer_text,
            fontsize=8,
            color=(0.3, 0.3, 0.3), # subtle dark grey
        )

    # ── Signature image preprocessing ─────────────────────────────────────────

    @staticmethod
    def _preprocess_signature_image(image_bytes: bytes) -> bytes:
        """
        Clean up a signature PNG/JPG before embedding it in the PDF.

        Pipeline
        --------
        1. Remove white / near-white background pixels (drawn sigs on white
           canvas, or uploaded sigs with white surrounds) — pure Pillow, no
           external deps beyond what Django already requires.
        2. Crop tightly to the bounding box of remaining opaque pixels.
        3. Darken and boost contrast on the RGB channels ONLY — alpha is
           split out before any colour transform and only recombined at the
           very end, so transparency is never touched.
        4. Resize to a sensible thumbnail.

        Returns a transparent PNG (no background fill, ink strokes only).
        """
        from PIL import Image, ImageEnhance
        from io import BytesIO as _BytesIO

        img = Image.open(_BytesIO(image_bytes)).convert("RGBA")

        # ── Step 1: Remove white / near-white background ──────────────────────
        # We iterate pixel data once using Pillow's own getdata/putdata.
        # A pixel is "white background" when R, G, B are all > 240 and the
        # pixel is already (mostly) opaque.
        pixels = list(img.getdata())
        cleaned = []
        for r, g, b, a in pixels:
            if r > 240 and g > 240 and b > 240 and a > 128:
                cleaned.append((r, g, b, 0))   # make transparent
            else:
                cleaned.append((r, g, b, a))
        img.putdata(cleaned)

        # ── Step 2: Tight crop around remaining opaque content ────────────────
        _, _, _, alpha_ch = img.split()
        bbox = alpha_ch.getbbox()              # None when fully transparent
        if bbox:
            img = img.crop(bbox)
        else:
            # Nothing visible after whitespace removal — return as-is
            out = _BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()

        # ── Step 3: Darken / contrast — RGB channels only ─────────────────────
        # Extract alpha BEFORE any colour operation so it is never modified.
        r_ch, g_ch, b_ch, a_ch = img.split()
        rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))

        # Boost contrast so faint strokes become solid.
        rgb = ImageEnhance.Contrast(rgb).enhance(2.0)

        # Darken the ink so it reads as deep black on the page.
        rgb = ImageEnhance.Brightness(rgb).enhance(0.4)

        # Reconstruct RGBA — alpha channel is completely untouched.
        r2, g2, b2 = rgb.split()
        img = Image.merge("RGBA", (r2, g2, b2, a_ch))

        # ── Step 4: Resize to a sensible thumbnail ────────────────────────────
        img.thumbnail((180, 80), Image.LANCZOS)

        # ── Output: transparent PNG ───────────────────────────────────────────
        out = _BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()





    def post(self, request, token, *args, **kwargs):
        # ── Token validation (unchanged) ──────────────────────────────────────
        signing_token = SigningToken.objects.filter(token=token).select_related(
            "signer__envelope__document"
        ).first()
        if not signing_token:
            return Response({"detail": "Invalid token."}, status=status.HTTP_404_NOT_FOUND)
        if signing_token.expires_at < timezone.now():
            return Response({"detail": "Token expired."}, status=status.HTTP_400_BAD_REQUEST)

        signer   = signing_token.signer
        envelope = signer.envelope
        document = envelope.document

        # ── Re-signing guard (unchanged) ──────────────────────────────────────
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" or signed_doc:
            return Response(
                {
                    "detail": "Envelope already signed.",
                    "status": "completed",
                    "signed_document_url": request.build_absolute_uri(
                        reverse('signing-download', kwargs={'token': token})
                    ) if signed_doc else None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not document.file:
            return Response(
                {"detail": "Original document file is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")

        # ── Payload extraction & per-type validation ──────────────────────────
        sig_type = request.data.get("signature_type", "typed")

        if sig_type == "typed":
            signature_text = request.data.get("signature_text", "").strip()
            if not signature_text:
                return Response(
                    {"detail": "signature_text is required for typed signatures."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            signature_image_b64 = None

        elif sig_type in ("upload", "draw"):
            signature_image_b64 = request.data.get("signature_image", "").strip()
            if not signature_image_b64:
                return Response(
                    {"detail": "signature_image (base64) is required for upload/draw signatures."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            signature_text = None

        else:
            return Response(
                {"detail": f"Unsupported signature_type: '{sig_type}'. Use 'typed', 'upload', or 'draw'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Signing transaction (lifecycle unchanged) ─────────────────────────
        with transaction.atomic():
            document.file.open("rb")
            try:
                original_bytes = document.file.read()
            finally:
                document.file.close()

            final_hash    = hashlib.sha256(original_bytes).hexdigest()
            original_name = document.file.name.rsplit("/", 1)[-1] or "signed.pdf"

            pdf_document = fitz.open(stream=original_bytes, filetype="pdf")

            # ── Page selection ────────────────────────────────────────────────
            # envelope.signature_page is 1-based (frontend convention).
            # PyMuPDF uses 0-based indexing.  Clamp to valid range.
            target_page_idx = max(0, envelope.signature_page - 1)
            target_page_idx = min(target_page_idx, len(pdf_document) - 1)
            page = pdf_document[target_page_idx]

            # Delegate embedding — pass stored ratios (may be None)
            self._embed_signature(
                page,
                sig_type,
                x_ratio=envelope.signature_x_ratio,
                y_ratio=envelope.signature_y_ratio,
                signature_text=signature_text,
                signature_image_b64=signature_image_b64,
                signer_name=signer.name,
            )

            pdf_bytes = pdf_document.tobytes()
            pdf_document.close()

            signed_doc = SignedDocument(envelope=envelope, final_hash=final_hash)
            signed_doc.file.save(original_name, ContentFile(pdf_bytes), save=True)
            import os

            print("SIGNED FILE URL:", signed_doc.file.url)
            print("SIGNED FILE PATH:", signed_doc.file.path)
            print("EXISTS:", os.path.exists(signed_doc.file.path))

            # Invalidate token (unchanged)
            signing_token.is_used   = True
            signing_token.expires_at = timezone.now() + timedelta(minutes=15)
            signing_token.save(update_fields=["is_used", "expires_at"])

            # Update envelope status (unchanged)
            envelope.status = "completed"
            envelope.save(update_fields=["status"])

            # Audit logging (unchanged)
            AuditLog.objects.create(
                envelope=envelope,
                event="signed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return Response(
            {
                "message": "Document signed successfully.",
                "envelope_id": envelope.id,
                "signed_document_id": signed_doc.id,
                "signed_document_url": request.build_absolute_uri(
                    reverse('signing-download', kwargs={'token': token})
                ),
            },
            status=status.HTTP_201_CREATED,
        )

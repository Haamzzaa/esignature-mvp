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
from .models import Envelope, Signer, SigningToken, AuditLog, SignedDocument, Participant, ParticipantToken
from .serializers import DocumentUploadSerializer, EnvelopeCreateSerializer
from django.http import FileResponse, Http404
import os
import fitz
from io import BytesIO

def activate_workflow_step(envelope, step_number):
    """
    Activates all participants in the specified step_number for the envelope,
    generating/regenerating their ParticipantToken.
    Also updates legacy Signer/SigningToken dynamically if a signer participant is activated.
    """
    # Transition all participants in this step to active
    step_participants = envelope.participants.filter(step_number=step_number)
    for p in step_participants:
        p.status = 'active'
        p.save(update_fields=['status'])
        
        # Spawn unique ParticipantToken
        ParticipantToken.objects.filter(participant=p).delete()
        ParticipantToken.objects.create(
            participant=p,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )
        
        # Keep legacy Signer/SigningToken synced for compatibility
        if p.role == 'signer':
            signer_rec = Signer.objects.filter(envelope=envelope).first()
            if signer_rec:
                signer_rec.name = p.name
                signer_rec.email = p.email
                signer_rec.save()
                
                # Provision signing token
                SigningToken.objects.filter(signer=signer_rec).delete()
                SigningToken.objects.create(
                    signer=signer_rec,
                    expires_at=timezone.now() + timedelta(hours=24),
                    is_used=False
                )

def get_token_signer_or_participant(token_str, allow_used=False):
    """
    Resolves token string to either a ParticipantToken or legacy SigningToken,
    validating expiration and use.
    Returns (token_obj, error_msg).
    """
    # 1. Look up ParticipantToken
    pt = ParticipantToken.objects.filter(token=token_str).first()
    if pt:
        if pt.is_used and not allow_used:
            return None, "Token already used."
        if pt.expires_at < timezone.now():
            return None, "Token expired."
        return pt, None

    # 2. Look up legacy SigningToken
    st = SigningToken.objects.filter(token=token_str).first()
    if st:
        if st.is_used and not allow_used:
            return None, "Token already used."
        if st.expires_at < timezone.now():
            return None, "Token expired."
        return st, None

    return None, "Invalid token."

def check_and_advance_step(envelope, current_step, request=None):
    """
    Checks if all participants in current_step have completed their actions.
    If so, transitions step, activates the next step participants, and advances the workflow.
    """
    ip_address = request.META.get("REMOTE_ADDR") if request else None
    user_agent = request.META.get("HTTP_USER_AGENT") if request else None

    step_participants = envelope.participants.filter(step_number=current_step)
    
    all_step_completed = True
    for p in step_participants:
        if p.status != 'completed':
            all_step_completed = False
            break

    if all_step_completed:
        # Check if Step Completed audit has already been logged to avoid double entries
        completed_event = f"Step {current_step} Completed"
        if not AuditLog.objects.filter(envelope=envelope, event=completed_event).exists():
            AuditLog.objects.create(
                envelope=envelope,
                event=completed_event,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Check for next step in sequential routing
        next_participants = envelope.participants.filter(step_number__gt=current_step).order_by('step_number')
        if next_participants.exists():
            next_step = next_participants.first().step_number
            
            # Activate next step participants
            activate_workflow_step(envelope, next_step)
            
            AuditLog.objects.create(
                envelope=envelope,
                event="Workflow Advanced",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event=f"Step {next_step} Activated",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            # Keep/reset envelope status to sent so the next participants can perform actions
            envelope.status = "sent"
            envelope.save(update_fields=["status"])
        else:
            # Final workflow step completed! Mark envelope as completed
            envelope.status = "completed"
            envelope.save(update_fields=["status"])

            AuditLog.objects.create(
                envelope=envelope,
                event="Workflow Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            # Legacy "completed" audit event
            AuditLog.objects.create(
                envelope=envelope,
                event="completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

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
                    "status": envelope.status,
                    "send_reminders": envelope.send_reminders,
                    "send_final_email": envelope.send_final_email,
                    "allow_printing": envelope.allow_printing,
                    "additional_recipients": envelope.additional_recipients,
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
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
            
        document = envelope.document
        if not document.file:
            raise Http404("Document file not found.")
            
        return FileResponse(document.file.open('rb'), content_type='application/pdf')

class SigningSignedDocumentView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
            
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
        
        signed_doc = get_object_or_404(SignedDocument, envelope=envelope)
        if not signed_doc.file:
            raise Http404("Signed document file not found.")
            
        return FileResponse(signed_doc.file.open('rb'), content_type='application/pdf')

class SigningDownloadView(APIView):
    def get(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token, allow_used=True)
        if error_msg:
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
            
        if hasattr(token_obj, 'participant'):
            envelope = token_obj.participant.envelope
        else:
            envelope = token_obj.signer.envelope
        
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
        token_obj, error_msg = get_token_signer_or_participant(token)
        if error_msg:
            return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        is_participant = hasattr(token_obj, 'participant')
        if is_participant:
            participant = token_obj.participant
            envelope = participant.envelope
            role = participant.role
            name = participant.name
            email = participant.email
            p_status = participant.status
        else:
            signer = token_obj.signer
            envelope = signer.envelope
            role = "signer"
            name = signer.name
            email = signer.email
            if envelope.status in ("signed", "completed"):
                p_status = "completed"
            elif envelope.status == "viewed":
                p_status = "viewed"
            else:
                p_status = "active"

        # Check if completed/signed
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" and signed_doc:
            if is_participant and participant.status == 'active':
                participant.status = 'viewed'
                participant.save(update_fields=['status'])
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Participant Viewed",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
                
            return Response({
                "signer_name": name,
                "signer_email": email,
                "participant_role": role,
                "participant_status": p_status if not is_participant else participant.status,
                "document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "signed_document_url": request.build_absolute_uri(
                    reverse('signing-signed', kwargs={'token': token})
                ),
                "envelope_id": envelope.id,
                "status": "completed"
            })

        # Process viewing transition
        if is_participant:
            if participant.status == 'active':
                participant.status = 'viewed'
                participant.save(update_fields=["status"])
                AuditLog.objects.create(
                    envelope=envelope,
                    event="Participant Viewed",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
        else:
            # Legacy signer viewed
            AuditLog.objects.create(
                envelope=envelope,
                event="viewed",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )
            if envelope.status != "viewed":
                envelope.status = "viewed"
                envelope.save(update_fields=["status"])
                
            # If a participant record exists for this legacy signer's email, mark it viewed too
            p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
            if p_rec and p_rec.status == 'active':
                p_rec.status = 'viewed'
                p_rec.save(update_fields=["status"])

        return Response({
            "signer_name": name,
            "signer_email": email,
            "participant_role": role,
            "participant_status": p_status if not is_participant else participant.status,
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

        # 1. Immediately resize the image on load to prevent OOM on large phone resolutions
        # Use context manager to open the image safely and keep memory footprints minimal
        with _BytesIO(image_bytes) as in_stream:
            with Image.open(in_stream) as original_img:
                # Downsize immediately to at most 800x400
                original_img.thumbnail((800, 400), Image.LANCZOS)
                img = original_img.convert("RGBA")

        # ── Step 1: Remove white / near-white background ──────────────────────
        # getdata() now processes at most 320,000 pixels, which requires almost zero memory!
        pixels = list(img.getdata())
        cleaned = []
        for r, g, b, a in pixels:
            if r > 240 and g > 240 and b > 240 and a > 128:
                cleaned.append((r, g, b, 0))   # make transparent
            else:
                cleaned.append((r, g, b, a))
        img.putdata(cleaned)

        # ── Step 2: Tight crop around remaining opaque content ────────────────
        r_ch, g_ch, b_ch, a_ch = img.split()
        bbox = a_ch.getbbox()              # None when fully transparent
        if bbox:
            img_cropped = img.crop(bbox)
            img.close()
            img = img_cropped
            # Re-split channels after crop
            r_ch, g_ch, b_ch, a_ch = img.split()
        else:
            # Nothing visible after whitespace removal — return as-is
            with _BytesIO() as out:
                img.save(out, format="PNG", optimize=True)
                img.close()
                return out.getvalue()

        # ── Step 3: Darken / contrast — RGB channels only ─────────────────────
        # Merge R, G, B channels and apply enhancement transforms
        rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))
        
        # Boost contrast so faint strokes become solid.
        rgb_contrast = ImageEnhance.Contrast(rgb).enhance(2.0)
        rgb.close()
        
        # Darken the ink so it reads as deep black on the page.
        rgb_dark = ImageEnhance.Brightness(rgb_contrast).enhance(0.4)
        rgb_contrast.close()

        # Reconstruct RGBA — alpha channel is completely untouched.
        r2, g2, b2 = rgb_dark.split()
        img_enhanced = Image.merge("RGBA", (r2, g2, b2, a_ch))
        rgb_dark.close()
        img.close()

        # ── Step 4: Resize to a sensible thumbnail ────────────────────────────
        img_enhanced.thumbnail((180, 80), Image.LANCZOS)

        # ── Output: transparent PNG ───────────────────────────────────────────
        with _BytesIO() as out:
            img_enhanced.save(out, format="PNG", optimize=True)
            img_enhanced.close()
            return out.getvalue()





    def post(self, request, token, *args, **kwargs):
        token_obj, error_msg = get_token_signer_or_participant(token)
        if error_msg:
            return Response({"detail": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        is_participant = hasattr(token_obj, 'participant')
        if is_participant:
            participant = token_obj.participant
            envelope = participant.envelope
            role = participant.role
            name = participant.name
            email = participant.email
            p_status = participant.status
        else:
            signer   = token_obj.signer
            envelope = signer.envelope
            role     = "signer"
            name     = signer.name
            email    = signer.email
            p_status = "active"

        # Check if already completed/signed
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        if envelope.status == "completed" or signed_doc or envelope.status == "declined":
            return Response(
                {
                    "detail": "Envelope already processed or declined.",
                    "status": envelope.status,
                    "signed_document_url": request.build_absolute_uri(
                        reverse('signing-download', kwargs={'token': token})
                    ) if signed_doc else None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce that only active/viewed participants can act
        if is_participant and p_status not in ('active', 'viewed'):
            return Response({"detail": "Only active step participants may perform actions."}, status=status.HTTP_400_BAD_REQUEST)

        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")
        action = request.data.get("action")

        # ── Role Actions handling ───────────────────────────────────────────
        if role != "signer":
            allowed_actions = ("approve", "return", "reject")
            if role == "cc":
                allowed_actions = ("acknowledge",)
                
            if action not in allowed_actions:
                return Response({"detail": f"Invalid action '{action}' for role '{role}'."}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                if role == "reviewer":
                    if action == "approve":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Reviewer Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                    elif action == "return":
                        participant.status = "returned"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        envelope.status = "declined"
                        envelope.save(update_fields=["status"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Reviewer Returned",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Returned",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                elif role == "approver":
                    if action == "approve":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Approver Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Approved",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                    elif action == "reject":
                        participant.status = "declined"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        envelope.status = "declined"
                        envelope.save(update_fields=["status"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Approver Rejected",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="Participant Rejected",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                elif role == "cc":
                    if action == "acknowledge":
                        participant.status = "completed"
                        participant.completed_at = timezone.now()
                        participant.save(update_fields=["status", "completed_at"])
                        
                        AuditLog.objects.create(
                            envelope=envelope,
                            event="CC Acknowledged",
                            ip_address=ip_address,
                            user_agent=user_agent,
                        )
                
                # Invalidate token
                token_obj.is_used = True
                token_obj.save(update_fields=["is_used"])

                # Check and advance step if not declined
                if envelope.status != "declined":
                    check_and_advance_step(envelope, participant.step_number, request)

            return Response(
                {
                    "message": f"Action {action} processed successfully.",
                    "envelope_id": envelope.id,
                    "status": envelope.status,
                },
                status=status.HTTP_200_OK,
            )

        # ── Signer Role logic (unchanged PDF embedding) ──────────────────────
        document = envelope.document
        if not document.file:
            return Response(
                {"detail": "Original document file is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            
            if sig_type == "upload":
                try:
                    b64_data = signature_image_b64
                    if "," in b64_data:
                        b64_data = b64_data.split(",", 1)[1]
                    
                    import base64
                    decoded_bytes = base64.b64decode(b64_data)
                    
                    if len(decoded_bytes) > 2 * 1024 * 1024:
                        return Response(
                            {"detail": "Signature image exceeds maximum allowed size (2MB)."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    
                    from PIL import Image
                    import io
                    try:
                        with Image.open(io.BytesIO(decoded_bytes)) as img:
                            img_format = img.format
                    except Exception:
                        return Response(
                            {"detail": "Unable to parse signature image format."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    
                    if not img_format or img_format.upper() not in ("PNG", "JPEG", "WEBP"):
                        return Response(
                            {"detail": "Unsupported image format. Allowed formats: PNG, JPG, JPEG, WEBP."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except Exception:
                    return Response(
                        {"detail": "Invalid base64 signature image data."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            signature_text = None

        else:
            return Response(
                {"detail": f"Unsupported signature_type: '{sig_type}'. Use 'typed', 'upload', or 'draw'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            document.file.open("rb")
            try:
                original_bytes = document.file.read()
            finally:
                document.file.close()

            final_hash    = hashlib.sha256(original_bytes).hexdigest()
            original_name = document.file.name.rsplit("/", 1)[-1] or "signed.pdf"

            pdf_document = fitz.open(stream=original_bytes, filetype="pdf")

            target_page_idx = max(0, envelope.signature_page - 1)
            target_page_idx = min(target_page_idx, len(pdf_document) - 1)
            page = pdf_document[target_page_idx]

            try:
                self._embed_signature(
                    page,
                    sig_type,
                    x_ratio=envelope.signature_x_ratio,
                    y_ratio=envelope.signature_y_ratio,
                    signature_text=signature_text,
                    signature_image_b64=signature_image_b64,
                    signer_name=name,
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Image processing failed: {str(e)}", exc_info=True)
                return Response(
                    {"detail": "Unable to process uploaded signature image."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pdf_bytes = pdf_document.tobytes()
            pdf_document.close()

            signed_doc = SignedDocument(envelope=envelope, final_hash=final_hash)
            signed_doc.file.save(original_name, ContentFile(pdf_bytes), save=True)

            token_obj.is_used   = True
            token_obj.expires_at = timezone.now() + timedelta(minutes=15)
            token_obj.save(update_fields=["is_used", "expires_at"])

            if is_participant:
                participant.has_completed = True
                participant.status = 'completed'
                participant.completed_at = timezone.now()
                participant.save(update_fields=["has_completed", "status", "completed_at"])
                current_step = participant.step_number
            else:
                p_rec = Participant.objects.filter(envelope=envelope, email=email).first()
                current_step = 1
                if p_rec:
                    p_rec.has_completed = True
                    p_rec.status = 'completed'
                    p_rec.completed_at = timezone.now()
                    p_rec.save(update_fields=["has_completed", "status", "completed_at"])
                    current_step = p_rec.step_number

            AuditLog.objects.create(
                envelope=envelope,
                event="signed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Signer Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Participant Signed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            p_name = participant.name if is_participant else (p_rec.name if p_rec else name)
            AuditLog.objects.create(
                envelope=envelope,
                event=f"Participant {p_name} Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            check_and_advance_step(envelope, current_step, request)

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

class DashboardView(APIView):
    def get(self, request, *args, **kwargs):
        from django.db.models import Count, Q
        import os

        stats = Envelope.objects.aggregate(
            total_packages=Count('id'),
            draft=Count('id', filter=Q(status='draft')),
            sent=Count('id', filter=Q(status='sent')),
            viewed=Count('id', filter=Q(status='viewed')),
            completed=Count('id', filter=Q(status='completed')),
        )

        recent_packages = []
        envelopes = Envelope.objects.select_related('document').annotate(
            p_count=Count('participants')
        ).order_by('-created_at')[:10]
        
        for env in envelopes:
            recent_packages.append({
                "id": env.id,
                "title": env.title or (os.path.basename(env.document.file.name) if env.document.file else f"Envelope #{env.id}"),
                "status": env.status,
                "participants_count": env.p_count,
                "created_at": env.created_at.isoformat(),
            })

        recent_activity = []
        logs = AuditLog.objects.select_related('envelope__document').order_by('-timestamp')[:10]
        for log in logs:
            title = log.envelope.title or (os.path.basename(log.envelope.document.file.name) if log.envelope.document.file else f"Envelope #{log.envelope.id}")
            event_desc = f"{log.event.capitalize()} - {title}"
            recent_activity.append({
                "event": event_desc,
                "timestamp": log.timestamp.isoformat(),
            })

        return Response({
            "stats": stats,
            "recent_packages": recent_packages,
            "recent_activity": recent_activity,
        }, status=status.HTTP_200_OK)

class PackageDetailView(APIView):
    def get(self, request, pk, *args, **kwargs):
        import os
        envelope = get_object_or_404(Envelope, id=pk)
        
        doc_data = {
            "id": envelope.document.id,
            "filename": os.path.basename(envelope.document.file.name) if envelope.document.file else "document.pdf"
        }
        
        participants_list = []
        participants = envelope.participants.all().order_by('step_number', 'order', 'id')
        if participants.exists():
            for p in participants:
                action_url = ""
                token_val = None
                try:
                    if p.token:
                        token_val = p.token.token
                except ParticipantToken.DoesNotExist:
                    pass
                
                if token_val:
                    from django.conf import settings
                    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
                    action_url = f"{frontend_base}/sign/{token_val}"

                participants_list.append({
                    "id": p.id,
                    "name": p.name,
                    "email": p.email,
                    "role": p.role,
                    "order": p.order,
                    "step_number": p.step_number,
                    "has_completed": p.has_completed,
                    "status": p.status,
                    "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                    "action_url": action_url,
                })
        else:
            signer = Signer.objects.filter(envelope=envelope).first()
            if signer:
                if envelope.status in ("signed", "completed"):
                    status_val = "completed"
                elif envelope.status == "viewed":
                    status_val = "viewed"
                else:
                    status_val = "pending"

                token_val = None
                token_obj = SigningToken.objects.filter(signer=signer).first()
                if token_obj:
                    token_val = token_obj.token

                action_url = ""
                if token_val:
                    from django.conf import settings
                    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
                    action_url = f"{frontend_base}/sign/{token_val}"

                participants_list.append({
                    "id": signer.id,
                    "name": signer.name,
                    "email": signer.email,
                    "role": "signer",
                    "step_number": 1,
                    "has_completed": envelope.status in ("signed", "completed"),
                    "status": status_val,
                    "completed_at": None,
                    "action_url": action_url,
                })

        audit_trail = []
        logs = AuditLog.objects.filter(envelope=envelope).order_by('-timestamp')
        for log in logs:
            audit_trail.append({
                "event": log.event.capitalize() if log.event else "Activity",
                "timestamp": log.timestamp.isoformat(),
            })
            
        signed_doc = SignedDocument.objects.filter(envelope=envelope).first()
        signed_doc_data = {
            "available": False,
            "url": ""
        }
        if signed_doc and signed_doc.file:
            token_obj = SigningToken.objects.filter(signer__envelope=envelope).first()
            token = token_obj.token if token_obj else None
            
            if token:
                signed_doc_data = {
                    "available": True,
                    "url": request.build_absolute_uri(
                        reverse('signing-download', kwargs={'token': token})
                    )
                }
            else:
                signed_doc_data = {
                    "available": True,
                    "url": request.build_absolute_uri(signed_doc.file.url)
                }

        title = envelope.title or (os.path.basename(envelope.document.file.name) if envelope.document.file else f"Package #{envelope.id}")

        return Response({
            "id": envelope.id,
            "title": title,
            "description": envelope.description or "",
            "status": envelope.status,
            "created_at": envelope.created_at.isoformat(),
            "document": doc_data,
            "participants": participants_list,
            "audit_trail": audit_trail,
            "signed_document": signed_doc_data,
            "send_reminders": envelope.send_reminders,
            "send_final_email": envelope.send_final_email,
            "allow_printing": envelope.allow_printing,
            "additional_recipients": envelope.additional_recipients,
        }, status=status.HTTP_200_OK)

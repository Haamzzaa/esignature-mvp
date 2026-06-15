import base64
import fitz
from PIL import Image, ImageEnhance
from io import BytesIO
from django.utils import timezone

def preprocess_signature_image(image_bytes: bytes) -> bytes:
    """
    Clean up a signature PNG/JPG before embedding it in the PDF.
    Pipeline:
    1. Remove white / near-white background pixels.
    2. Crop tightly to the bounding box of remaining opaque pixels.
    3. Darken and boost contrast on the RGB channels ONLY.
    4. Resize to a sensible thumbnail.
    """
    # Downsize immediately to prevent memory overhead
    with BytesIO(image_bytes) as in_stream:
        with Image.open(in_stream) as original_img:
            original_img.thumbnail((800, 400), Image.LANCZOS)
            img = original_img.convert("RGBA")

    # 1. Remove white / near-white background
    pixels = list(img.getdata())
    cleaned = []
    for r, g, b, a in pixels:
        if r > 240 and g > 240 and b > 240 and a > 128:
            cleaned.append((r, g, b, 0))
        else:
            cleaned.append((r, g, b, a))
    img.putdata(cleaned)

    # 2. Crop tightly to bounding box
    r_ch, g_ch, b_ch, a_ch = img.split()
    bbox = a_ch.getbbox()
    if bbox:
        img_cropped = img.crop(bbox)
        img.close()
        img = img_cropped
        r_ch, g_ch, b_ch, a_ch = img.split()
    else:
        # Transparent canvas
        with BytesIO() as out:
            img.save(out, format="PNG", optimize=True)
            img.close()
            return out.getvalue()

    # 3. Darken / contrast
    rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))
    rgb_contrast = ImageEnhance.Contrast(rgb).enhance(2.0)
    rgb.close()
    
    rgb_dark = ImageEnhance.Brightness(rgb_contrast).enhance(0.4)
    rgb_contrast.close()

    r2, g2, b2 = rgb_dark.split()
    img_enhanced = Image.merge("RGBA", (r2, g2, b2, a_ch))
    rgb_dark.close()
    img.close()

    # 4. Resize to thumbnail
    img_enhanced.thumbnail((180, 80), Image.LANCZOS)

    with BytesIO() as out:
        img_enhanced.save(out, format="PNG", optimize=True)
        img_enhanced.close()
        return out.getvalue()


def embed_signature(
    page, sig_type,
    x_ratio=None, y_ratio=None,
    signature_text=None, signature_image_b64=None,
    signer_name=None,
    add_footer=True,
):
    """
    Embed signature drawing on the specified fitz Page using ratio-based positions.
    """
    pdf_h = page.rect.height
    pdf_w = page.rect.width

    if x_ratio is not None and y_ratio is not None:
        origin_x = float(x_ratio) * pdf_w
        origin_y = float(y_ratio) * pdf_h
    else:
        origin_x = 50
        origin_y = pdf_h - 120

    if sig_type == "typed":
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
        if "," in signature_image_b64:
            signature_image_b64 = signature_image_b64.split(",", 1)[1]

        raw_bytes = base64.b64decode(signature_image_b64)
        image_bytes = preprocess_signature_image(raw_bytes)

        with Image.open(BytesIO(image_bytes)) as img:
            orig_w, orig_h = img.size

        max_width = 120.0
        max_height = 45.0
        
        if orig_w == 0 or orig_h == 0:
            scale_ratio = 1.0
        else:
            scale_ratio = min(max_width / orig_w, max_height / orig_h)

        img_w = orig_w * scale_ratio
        img_h = orig_h * scale_ratio

        x0 = origin_x - img_w / 2
        y0 = origin_y - img_h / 2
        rect = fitz.Rect(x0, y0, x0 + img_w, y0 + img_h)

        page.insert_image(rect, stream=image_bytes)

    if add_footer:
        footer_text = (
            f"Digitally signed by {signer_name or 'Unknown'}\n"
            f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        )
        page.insert_text(
            (40, pdf_h - 40),
            footer_text,
            fontsize=8,
            color=(0.3, 0.3, 0.3),
        )


def sign_document(envelope, participant_rec, name, sig_type, signature_text, signature_image_b64, fields_payload, original_bytes):
    """
    Applies the signature, fields, and footer metadata onto the PDF document bytes.
    Returns the signed PDF bytes.
    """
    from services.field_service import get_fields_for_participant
    from esign.models import DocumentField
    
    pdf_document = fitz.open(stream=original_bytes, filetype="pdf")

    target_page_idx = max(0, envelope.signature_page - 1)
    target_page_idx = min(target_page_idx, len(pdf_document) - 1)
    page = pdf_document[target_page_idx]

    fields_qs = get_fields_for_participant(participant_rec) if participant_rec else DocumentField.objects.none()

    if not fields_qs.exists():
        embed_signature(
            page,
            sig_type,
            x_ratio=envelope.signature_x_ratio,
            y_ratio=envelope.signature_y_ratio,
            signature_text=signature_text,
            signature_image_b64=signature_image_b64,
            signer_name=name,
        )
    else:
        for f in fields_qs:
            f_page_idx = max(0, f.page - 1)
            f_page_idx = min(f_page_idx, len(pdf_document) - 1)
            f_page = pdf_document[f_page_idx]

            if f.field_type == 'signature':
                embed_signature(
                    f_page,
                    sig_type,
                    x_ratio=f.x_ratio,
                    y_ratio=f.y_ratio,
                    signature_text=signature_text,
                    signature_image_b64=signature_image_b64,
                    signer_name=name,
                    add_footer=False
                )
            elif f.field_type == 'date':
                date_str = timezone.now().strftime('%Y-%m-%d')
                pdf_h = f_page.rect.height
                pdf_w = f_page.rect.width
                origin_x = float(f.x_ratio) * pdf_w
                origin_y = float(f.y_ratio) * pdf_h
                f_page.insert_text(
                    (origin_x, origin_y),
                    date_str,
                    fontsize=12,
                    fontname="helv",
                )
            elif f.field_type == 'text':
                val = fields_payload.get(str(f.id), name) if fields_payload else name
                pdf_h = f_page.rect.height
                pdf_w = f_page.rect.width
                origin_x = float(f.x_ratio) * pdf_w
                origin_y = float(f.y_ratio) * pdf_h
                f_page.insert_text(
                    (origin_x, origin_y),
                    str(val),
                    fontsize=12,
                    fontname="helv",
                )
            elif f.field_type == 'checkbox':
                val = fields_payload.get(str(f.id), True) if fields_payload else True
                box_str = "[X]" if val else "[ ]"
                pdf_h = f_page.rect.height
                pdf_w = f_page.rect.width
                origin_x = float(f.x_ratio) * pdf_w
                origin_y = float(f.y_ratio) * pdf_h
                f_page.insert_text(
                    (origin_x, origin_y),
                    box_str,
                    fontsize=12,
                    fontname="helv",
                )

        # Add a single footer metadata to the page of the first signature or page
        footer_text = (
            f"Digitally signed by {name or 'Unknown'}\n"
            f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        )
        pdf_h = page.rect.height
        page.insert_text(
            (40, pdf_h - 40),
            footer_text,
            fontsize=8,
            color=(0.3, 0.3, 0.3),
        )

    pdf_bytes = pdf_document.tobytes()
    pdf_document.close()
    return pdf_bytes

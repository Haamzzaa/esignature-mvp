import base64
import os
import fitz
from PIL import Image, ImageEnhance
from io import BytesIO
from django.utils import timezone
from datetime import timedelta

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


def generate_certificate_pdf(data):
    """
    Generates a Certificate of Completion PDF.
    - data dict structure:
      {
          'package_id': int,
          'package_title': str,
          'completion_date': str,
          'owner_email': str,
          'document_hash': str,
          'participants': [
              {
                  'name': str,
                  'email': str,
                  'role': str,
                  'completed_at': str,
                  'ip_address': str,
                  'user_agent': str,
              }, ...
          ],
          'timeline': [
              {
                  'timestamp': str,
                  'event': str,
                  'ip_address': str,
                  'user_agent': str,
              }, ...
          ],
          'generation_timestamp': str
      }
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842) # A4
    
    # Primary theme colors (vibrant but professional dark slate/blue)
    primary_color = (0.12, 0.23, 0.35)
    text_color = (0.2, 0.2, 0.2)
    secondary_text_color = (0.4, 0.4, 0.4)
    line_color = (0.8, 0.8, 0.8)

    def draw_page_border(p):
        p.draw_rect(fitz.Rect(20, 20, 575, 822), color=primary_color, width=1.5)
        # Draw small decorative corner lines
        p.draw_rect(fitz.Rect(25, 25, 570, 817), color=primary_color, width=0.5)

    # Initial page border
    draw_page_border(page)

    current_y = 60

    def check_page_break(y_pos, needed):
        nonlocal page
        if y_pos + needed > 790:
            page = doc.new_page(width=595, height=842)
            draw_page_border(page)
            # Add a running page header
            page.insert_text(
                (40, 40),
                f"Certificate of Completion - ID: {data['certificate_id']}",
                fontsize=8,
                fontname="hebo",
                color=secondary_text_color,
            )
            page.draw_line((40, 45), (555, 45), color=line_color, width=0.5)
            return 70
        return y_pos

    # Document Title & Certificate ID
    page.insert_text((40, current_y), "CERTIFICATE OF COMPLETION", fontsize=18, fontname="hebo", color=primary_color)
    page.insert_text((370, current_y + 4), f"ID: {data['certificate_id']}", fontsize=10, fontname="hebo", color=secondary_text_color)
    current_y += 30

    # Package Information Section
    page.insert_text((40, current_y), "Package Information", fontsize=12, fontname="hebo", color=primary_color)
    current_y += 18
    page.draw_line((40, current_y), (555, current_y), color=primary_color, width=1)
    current_y += 18

    # Package details key-values
    details = [
        ("Certificate ID:", data['certificate_id']),
        ("Package ID:", str(data['package_id'])),
        ("Package Name:", data['package_title']),
        ("Owner:", data['owner_email']),
        ("Completion Date:", data['completion_date']),
        ("Document SHA-256:", data['document_hash']),
    ]
    for key, val in details:
        current_y = check_page_break(current_y, 18)
        page.insert_text((40, current_y), key, fontsize=10, fontname="hebo", color=text_color)
        if key == "Document SHA-256:" and len(val) > 32:
            # Split the hash into multiple lines of 32 characters to prevent overflow
            hash_lines = [val[i:i+32] for i in range(0, len(val), 32)]
            for line in hash_lines:
                page.insert_text((160, current_y), line, fontsize=10, fontname="helv", color=text_color)
                if line != hash_lines[-1]:
                    current_y += 12
        else:
            page.insert_text((160, current_y), val, fontsize=10, fontname="helv", color=text_color)
        current_y += 16

    current_y += 14

    # Signer / Participant Events Section
    current_y = check_page_break(current_y, 40)
    page.insert_text((40, current_y), "Participant Activity Summary", fontsize=12, fontname="hebo", color=primary_color)
    current_y += 18
    page.draw_line((40, current_y), (555, current_y), color=primary_color, width=1)
    current_y += 18

    for p in data['participants']:
        current_y = check_page_break(current_y, 75)
        # Participant Name and Email
        page.insert_text((40, current_y), f"{p['name']} ({p['email']})", fontsize=10, fontname="hebo", color=text_color)
        current_y += 14
        
        # Detail line
        page.insert_text((50, current_y), f"Role: {p['role']}", fontsize=9, fontname="helv", color=text_color)
        page.insert_text((160, current_y), f"Completed: {p['completed_at']}", fontsize=9, fontname="helv", color=text_color)
        current_y += 14
        
        # Security footprint
        page.insert_text((50, current_y), f"IP Address: {p['ip_address'] or 'N/A'}", fontsize=9, fontname="helv", color=secondary_text_color)
        current_y += 12
        ua = p['user_agent'] or 'N/A'
        # Truncate user agent if it's too long
        if len(ua) > 95:
            ua = ua[:92] + "..."
        page.insert_text((50, current_y), f"Device: {ua}", fontsize=8, fontname="heit", color=secondary_text_color)
        current_y += 18

    current_y += 10

    # Audit Log Timeline Section
    current_y = check_page_break(current_y, 40)
    page.insert_text((40, current_y), "Detailed Audit Log Timeline", fontsize=12, fontname="hebo", color=primary_color)
    current_y += 18
    page.draw_line((40, current_y), (555, current_y), color=primary_color, width=1)
    current_y += 18

    for log in data['timeline']:
        current_y = check_page_break(current_y, 45)
        # Event time & description
        page.insert_text((40, current_y), log['timestamp'], fontsize=9, fontname="hebo", color=text_color)
        page.insert_text((150, current_y), log['event'], fontsize=9, fontname="helv", color=text_color)
        current_y += 12
        
        # IP and UA details
        ip_ua_info = f"IP: {log['ip_address'] or 'N/A'}"
        if log['user_agent']:
            log_ua = log['user_agent']
            if len(log_ua) > 65:
                log_ua = log_ua[:62] + "..."
            ip_ua_info += f"  |  Device: {log_ua}"
        page.insert_text((50, current_y), ip_ua_info, fontsize=8, fontname="heit", color=secondary_text_color)
        current_y += 18

    # Final footer detailing when certificate was generated
    current_y = check_page_break(current_y, 35)
    current_y += 10
    page.draw_line((40, current_y), (555, current_y), color=line_color, width=0.5)
    current_y += 12
    page.insert_text(
        (40, current_y),
        f"This certificate was generated on {data['generation_timestamp']} (UTC) and is cryptographically locked to the SHA-256 hash of the signed document.",
        fontsize=7.5,
        fontname="heit",
        color=secondary_text_color,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

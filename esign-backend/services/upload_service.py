from rest_framework.exceptions import ValidationError
import os
import fitz

def validate_pdf_extension(file):
    """
    Validates that the file has a .pdf extension (case-insensitive).
    """
    if not file or not file.name:
        raise ValidationError("Invalid file type. Only PDF documents are supported.")
    
    ext = os.path.splitext(file.name)[1].lower()
    if ext != '.pdf':
        raise ValidationError("Invalid file type. Only PDF documents are supported.")

def validate_pdf_mime_type(file):
    """
    Validates that the file has application/pdf MIME type.
    """
    # 1. Check Django's uploaded file content type if available
    content_type = getattr(file, 'content_type', None)
    if content_type and content_type != 'application/pdf':
        raise ValidationError("Invalid file type. Only PDF documents are supported.")
    
    # 2. Check the magic bytes to ensure it's not a spoofed extension/MIME type
    try:
        file.seek(0)
        header = file.read(4)
        file.seek(0)
    except Exception:
        raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")
        
    if header != b'%PDF':
        raise ValidationError("Invalid file type. Only PDF documents are supported.")

def validate_pdf_size(file):
    """
    Validates that the file size does not exceed 10 MB (10 * 1024 * 1024 bytes) and is not empty.
    """
    if not file:
        raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")
        
    # Check if empty
    if file.size == 0:
        raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")
        
    max_size = 10 * 1024 * 1024 # 10 MB
    if file.size > max_size:
        raise ValidationError("File too large. Maximum allowed size is 10 MB.")

def validate_pdf_upload(file):
    """
    Performs comprehensive validation on the uploaded PDF file:
    1. Size and Empty check
    2. Extension check
    3. MIME type check
    4. Integrity / Corruption check using PyMuPDF (fitz)
    """
    if not file:
        raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")

    # 1. Size & Empty check
    validate_pdf_size(file)

    # 2. Extension check
    validate_pdf_extension(file)

    # 3. MIME Type check
    validate_pdf_mime_type(file)

    # 4. Integrity / Corruption check using PyMuPDF
    try:
        file.seek(0)
        content = file.read()
        file.seek(0)
        
        # Try opening with fitz
        doc = fitz.open(stream=content, filetype="pdf")
        if doc.page_count < 1:
            raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")
        doc.close()
    except Exception:
        raise ValidationError("Invalid PDF upload. Please upload a valid PDF document.")

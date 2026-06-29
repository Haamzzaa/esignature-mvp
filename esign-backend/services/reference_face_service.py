import logging
import cv2
import numpy as np
from services.face_matching_service import get_face_analysis_app

logger = logging.getLogger(__name__)

def extract_reference_face(document_image_bytes):
    """
    Decodes the document image, detects the face using InsightFace,
    crops it, and returns the cropped face JPG bytes.
    Raises ValueError on empty or invalid images, or if no face is detected.
    """
    if not document_image_bytes:
        raise ValueError("Empty document image bytes provided.")

    nparr = np.frombuffer(document_image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode document image bytes.")

    app = get_face_analysis_app()
    faces = app.get(img)
    if not faces:
        raise ValueError("no_face_detected")

    # Crop the first detected face using the bbox coordinates with padding
    bbox = faces[0].bbox  # [x1, y1, x2, y2]
    h, w, _ = img.shape

    # Calculate original clamped coordinates and dimensions
    orig_x1 = max(0, int(bbox[0]))
    orig_y1 = max(0, int(bbox[1]))
    orig_x2 = min(w, int(bbox[2]))
    orig_y2 = min(h, int(bbox[3]))
    orig_h, orig_w = orig_y2 - orig_y1, orig_x2 - orig_x1

    # Calculate padding (25% of face width/height)
    bbox_w = bbox[2] - bbox[0]
    bbox_h = bbox[3] - bbox[1]
    pad_w = 0.25 * bbox_w
    pad_h = 0.25 * bbox_h

    # Calculate expanded and clamped coordinates
    x1 = max(0, int(bbox[0] - pad_w))
    y1 = max(0, int(bbox[1] - pad_h))
    x2 = min(w, int(bbox[2] + pad_w))
    y2 = min(h, int(bbox[3] + pad_h))
    exp_h, exp_w = y2 - y1, x2 - x1

    logger.debug(
        "Reference face crop: original=%dx%d expanded=%dx%d",
        orig_w, orig_h, exp_w, exp_h
    )

    cropped_face = img[y1:y2, x1:x2]
    if cropped_face.size == 0:
        raise ValueError("Invalid cropped face bounding box.")

    success, face_barr = cv2.imencode('.jpg', cropped_face)
    if not success:
        raise ValueError("Failed to encode cropped face to JPEG format.")

    return face_barr.tobytes()

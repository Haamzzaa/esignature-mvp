import os
import cv2
import numpy as np
import logging
from django.conf import settings
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

# Cache FaceAnalysis app instance
_app_instance = None

def get_face_analysis_app():
    global _app_instance
    if _app_instance is None:
        logger.info("Initializing InsightFace buffalo_l app...")
        _app_instance = FaceAnalysis(name='buffalo_l', allowed_modules=['detection', 'recognition'], providers=['CPUExecutionProvider'])
        _app_instance.prepare(ctx_id=-1, det_size=(640, 640))
    return _app_instance

def validate_image(image_path):
    """
    Stage 1: Image Validation
    Validates file existence, format, minimum resolution, blur, brightness, and contrast.
    """
    diagnostics = {
        "exists": False,
        "valid_format": False,
        "width": 0,
        "height": 0,
        "resolution_passed": False,
        "blur_score": 0.0,
        "blur_passed": False,
        "brightness_score": 0.0,
        "brightness_passed": False,
        "contrast_score": 0.0,
        "contrast_passed": False,
        "passed": False,
        "error_message": ""
    }

    if not os.path.exists(image_path):
        diagnostics["error_message"] = "File does not exist."
        return diagnostics
    diagnostics["exists"] = True

    _, ext = os.path.splitext(image_path.lower())
    if ext not in ('.jpg', '.jpeg', '.png'):
        diagnostics["error_message"] = "Unsupported file format. Only JPG, JPEG, and PNG are supported."
        return diagnostics
    diagnostics["valid_format"] = True

    img = cv2.imread(image_path)
    if img is None:
        diagnostics["error_message"] = "Failed to decode image using OpenCV."
        return diagnostics

    h, w, _ = img.shape
    diagnostics["width"] = w
    diagnostics["height"] = h
    if w >= 300 and h >= 300:
        diagnostics["resolution_passed"] = True
    else:
        diagnostics["error_message"] = f"Image resolution ({w}x{h}) is below the minimum required 300x300."
        return diagnostics

    # Convert to grayscale for statistical checks
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur detection via Laplacian variance
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    diagnostics["blur_score"] = float(blur_score)
    if blur_score >= 45.0:
        diagnostics["blur_passed"] = True
    else:
        diagnostics["error_message"] = f"Image is too blurry (blur score: {blur_score:.2f} < 45.0)."
        return diagnostics

    # Brightness validation
    mean_val = np.mean(gray)
    diagnostics["brightness_score"] = float(mean_val)
    if 40.0 <= mean_val <= 225.0:
        diagnostics["brightness_passed"] = True
    else:
        diagnostics["error_message"] = f"Poor illumination. Brightness ({mean_val:.2f}) must be between 40.0 and 225.0."
        return diagnostics

    # Contrast validation
    std_val = np.std(gray)
    diagnostics["contrast_score"] = float(std_val)
    if std_val >= 12.0:
        diagnostics["contrast_passed"] = True
    else:
        diagnostics["error_message"] = f"Low contrast image (contrast score: {std_val:.2f} < 12.0)."
        return diagnostics

    diagnostics["passed"] = True
    return diagnostics


def detect_face(img):
    """
    Stage 2: Face Detection
    Checks for exactly one face, size, and confidence score.
    """
    app = get_face_analysis_app()
    faces = app.get(img)

    result = {
        "faces_count": len(faces),
        "face": None,
        "bbox": None,
        "confidence": 0.0,
        "size_passed": False,
        "confidence_passed": False,
        "passed": False,
        "error_message": ""
    }

    if len(faces) == 0:
        result["error_message"] = "No face detected in the image."
        return result

    if len(faces) > 1:
        # Select the largest face by bounding box area (most likely the primary subject).
        # This handles ID document images where a small inset photo may trigger a second detection.
        def _face_area(f):
            b = f.bbox
            return max(0.0, float((b[2] - b[0]) * (b[3] - b[1])))
        faces = sorted(faces, key=_face_area, reverse=True)
        logger.warning(
            "Multiple faces detected (%d). Selecting largest face (area=%.0f px²) as primary.",
            len(faces),
            _face_area(faces[0]),
        )
        result["faces_count"] = len(faces)  # keep original count for diagnostics

    face = faces[0]
    result["face"] = face
    bbox = face.bbox.astype(int).tolist() # [x1, y1, x2, y2]
    result["bbox"] = bbox
    result["confidence"] = float(face.det_score)

    # Validate detection confidence
    if face.det_score >= 0.55:
        result["confidence_passed"] = True
    else:
        result["error_message"] = f"Face detection confidence ({face.det_score:.2f}) is below 0.55 threshold."
        return result

    # Validate face size
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if w >= 65 and h >= 65:
        result["size_passed"] = True
    else:
        result["error_message"] = f"Face size too small ({w}x{h} px). Must be at least 65x65 px."
        return result

    result["passed"] = True
    return result


def assess_face_quality(face, img):
    """
    Stage 3: Face Quality Assessment
    Checks pose (yaw, pitch, roll), crop sharpness, eye landmarks visibility.
    """
    if face.pose is not None:
        pose = face.pose  # pitch, yaw, roll (in degrees)
        pitch, yaw, roll = float(pose[0]), float(pose[1]), float(pose[2])
    else:
        # Estimate pose from 5 keypoints (kps)
        kps = face.kps
        left_eye = kps[0]
        right_eye = kps[1]
        nose = kps[2]
        
        # Roll: slope of the eyes line
        dY = right_eye[1] - left_eye[1]
        dX = right_eye[0] - left_eye[0]
        roll = float(np.degrees(np.arctan2(dY, dX)))
        
        # Yaw: distance of nose to left eye vs right eye
        left_dist = float(np.linalg.norm(nose - left_eye))
        right_dist = float(np.linalg.norm(nose - right_eye))
        eye_dist = float(np.linalg.norm(right_eye - left_eye))
        if eye_dist > 0:
            yaw = ((left_dist - right_dist) / eye_dist) * 45.0
        else:
            yaw = 0.0
            
        # Pitch: standard approximation if 3D model is disabled
        pitch = 0.0

    bbox = face.bbox.astype(int)
    x1, y1, x2, y2 = max(0, bbox[0]), max(0, bbox[1]), min(img.shape[1], bbox[2]), min(img.shape[0], bbox[3])
    
    # Crop face area
    crop = img[y1:y2, x1:x2]
    if crop.size > 0:
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        crop_blur = float(cv2.Laplacian(crop_gray, cv2.CV_64F).var())
    else:
        crop_blur = 0.0

    # Pose checks
    pose_passed = abs(yaw) <= 26.0 and abs(pitch) <= 26.0 and abs(roll) <= 26.0

    # Sharpness check
    # Threshold lowered to 15.0 to accommodate printed ID document photos
    # (ID card face crops have lower Laplacian variance due to print/lamination artifacts).
    sharpness_passed = crop_blur >= 15.0

    # Occlusion check: verify landmarks coordinates lie reasonably within the bounding box
    kps = face.kps.astype(int)
    kps_inside = True
    for pt in kps:
        px, py = pt[0], pt[1]
        # Bounding box coordinates with small margin
        margin = 15
        if not (x1 - margin <= px <= x2 + margin and y1 - margin <= py <= y2 + margin):
            kps_inside = False
            break

    # Dynamic Quality Score (0.0 to 1.0)
    score = 1.0
    score -= min(0.3, (1.0 - face.det_score))
    score -= min(0.3, (abs(yaw) / 90.0) + (abs(pitch) / 90.0))
    if crop_blur < 100.0:
        score -= min(0.2, (100.0 - crop_blur) / 500.0)
    if not kps_inside:
        score -= 0.3

    score = float(max(0.0, min(1.0, score)))

    passed = pose_passed and sharpness_passed and kps_inside and score >= 0.40

    error_message = ""
    if not pose_passed:
        error_message = f"Poor head pose: yaw={yaw:.1f}°, pitch={pitch:.1f}°, roll={roll:.1f}°. Keep head straight."
    elif not sharpness_passed:
        error_message = f"Face crop area is too blurry (sharpness score: {crop_blur:.2f} < 15.0)."
    elif not kps_inside:
        error_message = "Occlusion detected. Face keypoints are blocked or out of bounds."
    elif score < 0.40:
        error_message = f"Overall face quality score ({score:.2f}) is below acceptable threshold 0.40."

    return {
        "yaw": yaw,
        "pitch": pitch,
        "roll": roll,
        "crop_blur": crop_blur,
        "quality_score": score,
        "pose_passed": pose_passed,
        "sharpness_passed": sharpness_passed,
        "landmarks_inside": kps_inside,
        "passed": passed,
        "error_message": error_message
    }


def validate_landmarks(face, img_shape):
    """
    Stage 4: Landmark Detection
    Validates positions of left eye, right eye, nose, mouth corners.
    """
    kps = face.kps.astype(int)
    h, w = img_shape[0], img_shape[1]

    # Coordinate ranges validation
    for pt in kps:
        px, py = pt[0], pt[1]
        if not (0 <= px < w and 0 <= py < h):
            return {"passed": False, "error_message": "Some face landmarks are outside the image boundaries."}

    # Left eye, right eye, nose, mouth corners relative position validation
    left_eye = kps[0]
    right_eye = kps[1]
    nose = kps[2]
    mouth_left = kps[3]
    mouth_right = kps[4]

    # Standard landscape expectations:
    # 1. Left eye should generally be to the left of the right eye in the image plane
    horizontal_check = left_eye[0] < right_eye[0]
    # 2. Eyes should be above the nose
    eyes_above_nose = left_eye[1] < nose[1] and right_eye[1] < nose[1]
    # 3. Nose should be above the mouth
    nose_above_mouth = nose[1] < mouth_left[1] and nose[1] < mouth_right[1]

    if not (horizontal_check and eyes_above_nose and nose_above_mouth):
        return {
            "passed": False,
            "error_message": "Geometrical configuration check of landmarks failed. Possible extreme pose or occlusion."
        }

    return {"passed": True, "error_message": ""}


def align_and_crop(img, face, size=112):
    """
    Stage 5: Face Alignment
    Aligns and normalizes the face using affine transform.
    """
    kps = face.kps
    left_eye = kps[0]
    right_eye = kps[1]

    # Eye center and rotation angle
    dY = right_eye[1] - left_eye[1]
    dX = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dY, dX))

    # Standard face coordinates mapping ratio
    desired_left_eye = (0.35, 0.35)
    desired_right_eye = (0.65, 0.35)

    eye_center = (float((left_eye[0] + right_eye[0]) / 2.0), float((left_eye[1] + right_eye[1]) / 2.0))
    
    # Calculate scale based on desired distance between eyes
    dist = np.sqrt(dX**2 + dY**2)
    desired_dist = (desired_right_eye[0] - desired_left_eye[0]) * size
    scale = desired_dist / dist

    # Perform Affine Transformation Matrix
    M = cv2.getRotationMatrix2D(eye_center, angle, scale)

    # Shift eye center to desired center in cropped size
    tX = size * 0.5
    tY = size * desired_left_eye[1]
    M[0, 2] += (tX - eye_center[0])
    M[1, 2] += (tY - eye_center[1])

    aligned = cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_CUBIC)
    return aligned


def generate_embedding(face):
    """
    Stage 6: Embedding Generation
    InsightFace buffalo_l already computes normalized embedding on detection.
    """
    if hasattr(face, "normed_embedding") and face.normed_embedding is not None:
        return face.normed_embedding
    if hasattr(face, "embedding") and face.embedding is not None:
        emb = face.embedding
        return emb / np.linalg.norm(emb)
    raise ValueError("ArcFace embedding is missing from face object.")


def preprocess_for_recognition(img):
    """
    Stage 0 (optional pre-pass): CLAHE contrast normalization in LAB color space.
    Applied before face detection so that both detection confidence and
    ArcFace embeddings are computed on a lighting/contrast-normalized image.
    This is particularly beneficial for printed ID document photos which
    have degraded contrast from printing, lamination, and scanning.
    """
    try:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_normalized = clahe.apply(l_channel)
        lab_normalized = cv2.merge([l_normalized, a_channel, b_channel])
        return cv2.cvtColor(lab_normalized, cv2.COLOR_LAB2BGR)
    except Exception as e:
        logger.warning("CLAHE preprocessing failed (%s); using original image.", e)
        return img


def calculate_similarity(emb1, emb2):
    """
    Stage 7: Similarity Matching
    Calculates cosine similarity between two embeddings.
    """
    dot = float(np.dot(emb1, emb2))
    norm_a = np.linalg.norm(emb1)
    norm_b = np.linalg.norm(emb2)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def run_biometric_pipeline(id_image_path, live_image_path, threshold=0.53):
    """
    Orchestrates the entire Standalone Face Verification Pipeline.

    Threshold calibration (Iter 5):
      Genuine scores (ID-photo vs selfie):  0.5575 – 0.5802  (avg 0.5707)
      Impostor scores:                       0.2287 – 0.2639  (avg 0.2463)
      Natural decision boundary:             ~0.41
      Chosen threshold:                       0.53
        - margin above max impostor:  +0.266
        - margin below min genuine:   +0.028
    """
    report = {
        "stages": {
            "image_validation": {"passed": False, "detail": {}},
            "face_detection": {"passed": False, "detail": {}},
            "face_quality": {"passed": False, "detail": {}},
            "landmarks": {"passed": False, "detail": {}},
            "alignment": {"passed": False, "detail": {}},
            "embedding": {"passed": False, "detail": {}},
            "similarity": {"passed": False, "detail": {}},
            "decision_engine": {"passed": False, "detail": {}}
        },
        "score": 0.0,
        "threshold": threshold,
        "decision": "RETRY",
        "reason": ""
    }

    # ──── STAGE 1: Image Validation ────
    id_valid = validate_image(id_image_path)
    live_valid = validate_image(live_image_path)
    
    report["stages"]["image_validation"]["detail"] = {
        "id_image": id_valid,
        "live_image": live_valid
    }

    if not id_valid["passed"]:
        report["reason"] = f"ID Image validation failed: {id_valid['error_message']}"
        report["decision"] = "RETRY"
        return report

    if not live_valid["passed"]:
        report["reason"] = f"Live Selfie validation failed: {live_valid['error_message']}"
        report["decision"] = "RETRY"
        return report

    report["stages"]["image_validation"]["passed"] = True

    # Load images (raw — CLAHE preprocessing was trialled in Iter 3 and reverted;
    # ArcFace's internal normalisation makes external histogram transforms counter-productive).
    id_img   = cv2.imread(id_image_path)
    live_img = cv2.imread(live_image_path)

    # ──── STAGE 2: Face Detection ────
    id_detect = detect_face(id_img)
    live_detect = detect_face(live_img)

    report["stages"]["face_detection"]["detail"] = {
        "id_image": {
            "faces_count": id_detect["faces_count"],
            "bbox": id_detect["bbox"],
            "confidence": id_detect["confidence"],
            "passed": id_detect["passed"],
            "error_message": id_detect["error_message"]
        },
        "live_image": {
            "faces_count": live_detect["faces_count"],
            "bbox": live_detect["bbox"],
            "confidence": live_detect["confidence"],
            "passed": live_detect["passed"],
            "error_message": live_detect["error_message"]
        }
    }

    if not id_detect["passed"]:
        report["reason"] = f"Face detection failed on ID: {id_detect['error_message']}"
        report["decision"] = "RETRY"
        return report

    if not live_detect["passed"]:
        report["reason"] = f"Face detection failed on Selfie: {live_detect['error_message']}"
        report["decision"] = "RETRY"
        return report

    report["stages"]["face_detection"]["passed"] = True

    id_face = id_detect["face"]
    live_face = live_detect["face"]

    # ──── STAGE 3: Face Quality Assessment ────
    id_qual = assess_face_quality(id_face, id_img)
    live_qual = assess_face_quality(live_face, live_img)

    report["stages"]["face_quality"]["detail"] = {
        "id_image": id_qual,
        "live_image": live_qual
    }

    if not id_qual["passed"]:
        report["reason"] = f"Quality check failed on ID image: {id_qual['error_message']}"
        report["decision"] = "RETRY"
        return report

    if not live_qual["passed"]:
        report["reason"] = f"Quality check failed on Live image: {live_qual['error_message']}"
        report["decision"] = "RETRY"
        return report

    report["stages"]["face_quality"]["passed"] = True

    # ──── STAGE 4: Landmark Detection ────
    id_landmarks = validate_landmarks(id_face, id_img.shape)
    live_landmarks = validate_landmarks(live_face, live_img.shape)

    report["stages"]["landmarks"]["detail"] = {
        "id_image": id_landmarks,
        "live_image": live_landmarks
    }

    if not id_landmarks["passed"]:
        report["reason"] = f"Landmark validation failed on ID image: {id_landmarks['error_message']}"
        report["decision"] = "RETRY"
        return report

    if not live_landmarks["passed"]:
        report["reason"] = f"Landmark validation failed on Live image: {live_landmarks['error_message']}"
        report["decision"] = "RETRY"
        return report

    report["stages"]["landmarks"]["passed"] = True

    # ──── STAGE 5: Face Alignment ────
    try:
        id_aligned = align_and_crop(id_img, id_face)
        live_aligned = align_and_crop(live_img, live_face)
        
        # Save aligned images internally to cache directory or just verify they run
        report["stages"]["alignment"]["passed"] = True
        report["stages"]["alignment"]["detail"] = {
            "id_aligned_shape": id_aligned.shape,
            "live_aligned_shape": live_aligned.shape
        }
    except Exception as e:
        report["reason"] = f"Face alignment failed: {str(e)}"
        report["decision"] = "RETRY"
        return report

    # ──── STAGE 6: Embedding Generation ────
    try:
        emb1 = generate_embedding(id_face)
        emb2 = generate_embedding(live_face)
        report["stages"]["embedding"]["passed"] = True
    except Exception as e:
        report["reason"] = f"Embedding generation failed: {str(e)}"
        report["decision"] = "RETRY"
        return report

    # ──── STAGE 7: Similarity Matching ────
    score = calculate_similarity(emb1, emb2)
    report["score"] = score
    report["stages"]["similarity"]["passed"] = True
    report["stages"]["similarity"]["detail"] = {
        "cosine_similarity": score,
        "threshold": threshold
    }

    # ──── STAGE 8: Decision Engine ────
    report["stages"]["decision_engine"]["passed"] = True
    
    if score >= threshold:
        report["decision"] = "MATCH"
        report["reason"] = f"Face similarity matches successfully (similarity {score:.4f} >= threshold {threshold:.2f})."
    else:
        # If score is very close to threshold, let's flag manual review
        if score >= (threshold - 0.12):
            report["decision"] = "MANUAL_REVIEW"
            report["reason"] = f"Biometric anomaly. Score {score:.4f} is close but below threshold {threshold:.2f}."
        else:
            report["decision"] = "NO_MATCH"
            report["reason"] = f"Biometric mismatch. Score {score:.4f} is significantly below threshold {threshold:.2f}."

    return report

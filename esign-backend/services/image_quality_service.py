"""
Image Quality Assessment Engine (Foundation) for evaluating document images and selfies.
"""
import logging
import time
import cv2
import numpy as np

from esign.config import esign_config

logger = logging.getLogger(__name__)

class BlurAnalyzer:
    """Measures the sharpness of the image using Laplacian variance."""
    def analyze(self, img: np.ndarray) -> dict:
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return {"variance": float(variance)}

class ResolutionAnalyzer:
    """Measures image dimensions."""
    def analyze(self, img: np.ndarray) -> dict:
        h, w = img.shape[:2]
        return {"width": w, "height": h}

class BrightnessAnalyzer:
    """Measures the average lighting intensity of the image."""
    def analyze(self, img: np.ndarray) -> dict:
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        mean = np.mean(gray)
        return {"brightness": float(mean)}

class ExposureAnalyzer:
    """Measures pixels near extreme ends of the spectrum (overexposure/underexposure ratios)."""
    def analyze(self, img: np.ndarray) -> dict:
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        # Saturated / high pixels (> 240) and dark pixels (< 15) ratios
        overexposed_ratio = float(np.sum(gray > 240) / gray.size)
        underexposed_ratio = float(np.sum(gray < 15) / gray.size)
        return {
            "overexposed_ratio": overexposed_ratio,
            "underexposed_ratio": underexposed_ratio
        }

class RotationAnalyzer:
    """Estimates document skew angle in degrees using OpenCV Canny + Hough Lines."""
    def analyze(self, img: np.ndarray) -> dict:
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        h, w = gray.shape[:2]
        # Downscale for performance
        if max(h, w) > 800:
            scale = 800.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)
        if lines is None:
            return {"rotation_angle": 0.0}
        
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            norm_angle = (angle + 45) % 90 - 45
            angles.append(norm_angle)
        
        if not angles:
            return {"rotation_angle": 0.0}
        
        rotation_angle = float(np.median(angles))
        return {"rotation_angle": abs(rotation_angle)}

class FaceDetectionAnalyzer:
    """Detects faces using the cached InsightFace app singleton."""
    def analyze(self, img: np.ndarray) -> dict:
        from services.enterprise_biometric_service import get_face_analysis_app
        app = get_face_analysis_app()
        faces = app.get(img)
        return {"faces": faces, "faces_count": len(faces)}

class FaceSizeAnalyzer:
    """Determines face size dimensions in pixels based on the primary (largest) face."""
    def analyze(self, faces: list) -> dict:
        if not faces:
            return {"width": 0, "height": 0}
        
        def _face_area(f):
            b = f.bbox
            return max(0.0, float((b[2] - b[0]) * (b[3] - b[1])))
        
        sorted_faces = sorted(faces, key=_face_area, reverse=True)
        bbox = sorted_faces[0].bbox.astype(int).tolist()
        x1, y1, x2, y2 = bbox
        return {"width": x2 - x1, "height": y2 - y1}

class MultipleFaceAnalyzer:
    """Checks the number of faces detected in the image."""
    def analyze(self, faces: list) -> dict:
        return {"faces_count": len(faces)}

class DecisionEngine:
    """Evaluates analyzer measurements against thresholds to determine PASS/FAIL and output recommendations."""
    def decide_document_quality(self, blur_res: dict, resolution_res: dict, brightness_res: dict, exposure_res: dict, rotation_res: dict) -> dict:
        checks = []
        issues = []
        recommendations = []
        
        # Blur check
        blur_val = blur_res["variance"]
        blur_threshold = esign_config.image_quality_blur_threshold
        blur_passed = blur_val >= blur_threshold
        if not blur_passed:
            issues.append("Image is blurry")
            recommendations.append("Hold the document flat and keep the camera still")
        checks.append({
            "name": "blur",
            "measured_val": round(blur_val, 2),
            "passed": blur_passed
        })
        
        # Resolution check
        w = resolution_res["width"]
        h = resolution_res["height"]
        min_res_threshold = esign_config.image_quality_minimum_resolution
        resolution_passed = min(w, h) >= min_res_threshold
        if not resolution_passed:
            issues.append("Image resolution is too low")
            recommendations.append("Use a high-quality camera and capture from a closer distance")
        checks.append({
            "name": "resolution",
            "measured_val": f"{w}x{h}",
            "passed": resolution_passed
        })
        
        # Brightness check
        brightness_val = brightness_res["brightness"]
        min_brightness = esign_config.image_quality_minimum_brightness
        max_brightness = esign_config.image_quality_maximum_brightness
        brightness_passed = min_brightness <= brightness_val <= max_brightness
        if not brightness_passed:
            if brightness_val < min_brightness:
                issues.append("Image is too dark")
                recommendations.append("Improve lighting")
            else:
                issues.append("Image is too bright")
                recommendations.append("Avoid direct light reflection")
        checks.append({
            "name": "brightness",
            "measured_val": round(brightness_val, 2),
            "passed": brightness_passed
        })
        
        # Exposure check
        overexposed = exposure_res["overexposed_ratio"]
        underexposed = exposure_res["underexposed_ratio"]
        # Allow up to 40% saturated or dark pixels
        exposure_passed = overexposed < 0.40 and underexposed < 0.40
        if not exposure_passed:
            issues.append("Image has poor exposure")
            recommendations.append("Adjust lighting conditions or angle of capture")
        checks.append({
            "name": "exposure",
            "measured_val": f"over={round(overexposed, 2)}, under={round(underexposed, 2)}",
            "passed": exposure_passed
        })
        
        # Rotation check
        rotation_val = rotation_res["rotation_angle"]
        max_rotation = esign_config.image_quality_maximum_rotation
        rotation_passed = rotation_val <= max_rotation
        if not rotation_passed:
            issues.append("Image is rotated or skewed")
            recommendations.append("Hold the document flat and align it with the camera guide")
        checks.append({
            "name": "rotation",
            "measured_val": round(rotation_val, 2),
            "passed": rotation_passed
        })
        
        passed_count = sum(1 for c in checks if c["passed"])
        overall_score = float(passed_count) / len(checks)
        status = "PASS" if passed_count == len(checks) else "FAIL"
        
        unique_issues = list(dict.fromkeys(issues))
        unique_recs = list(dict.fromkeys(recommendations))
        
        return {
            "overall_quality_score": round(overall_score, 2),
            "status": status,
            "checks": checks,
            "issues": unique_issues,
            "recommendations": unique_recs
        }

    def decide_face_quality(self, blur_res: dict, resolution_res: dict, brightness_res: dict, exposure_res: dict, detection_res: dict, size_res: dict, multi_res: dict) -> dict:
        checks = []
        issues = []
        recommendations = []
        
        # Blur check
        blur_val = blur_res["variance"]
        blur_threshold = esign_config.image_quality_blur_threshold
        blur_passed = blur_val >= blur_threshold
        if not blur_passed:
            issues.append("Image is blurry")
            recommendations.append("Keep the camera steady and wait for autofocus")
        checks.append({
            "name": "blur",
            "measured_val": round(blur_val, 2),
            "passed": blur_passed
        })
        
        # Resolution check
        w = resolution_res["width"]
        h = resolution_res["height"]
        min_res_threshold = esign_config.image_quality_minimum_resolution
        resolution_passed = min(w, h) >= min_res_threshold
        if not resolution_passed:
            issues.append("Image resolution is too low")
            recommendations.append("Use a high-quality front camera")
        checks.append({
            "name": "resolution",
            "measured_val": f"{w}x{h}",
            "passed": resolution_passed
        })
        
        # Lighting check
        brightness_val = brightness_res["brightness"]
        min_brightness = esign_config.image_quality_minimum_brightness
        max_brightness = esign_config.image_quality_maximum_brightness
        overexposed = exposure_res["overexposed_ratio"]
        underexposed = exposure_res["underexposed_ratio"]
        
        lighting_passed = (min_brightness <= brightness_val <= max_brightness) and (overexposed < 0.40 and underexposed < 0.40)
        if not lighting_passed:
            issues.append("Poor lighting conditions")
            recommendations.append("Improve lighting and avoid strong backlights")
        checks.append({
            "name": "lighting",
            "measured_val": round(brightness_val, 2),
            "passed": lighting_passed
        })
        
        # Face detection check
        faces_count = detection_res["faces_count"]
        detection_passed = faces_count >= 1
        if not detection_passed:
            issues.append("No face detected in the image")
            recommendations.append("Ensure your face is clearly visible and centered")
        checks.append({
            "name": "face_detection",
            "measured_val": faces_count,
            "passed": detection_passed
        })
        
        # Face size check
        face_w = size_res["width"]
        face_h = size_res["height"]
        min_face_size = esign_config.image_quality_minimum_face_size
        if faces_count >= 1:
            size_passed = min(face_w, face_h) >= min_face_size
            if not size_passed:
                issues.append("Face is too small in the frame")
                recommendations.append("Move closer to the camera")
        else:
            size_passed = False
        checks.append({
            "name": "face_size",
            "measured_val": f"{face_w}x{face_h}" if faces_count >= 1 else "N/A",
            "passed": size_passed
        })
        
        # Multiple faces check
        multi_passed = faces_count <= 1
        if faces_count > 1:
            issues.append("Multiple faces detected in the image")
            recommendations.append("Ensure only one person is in the frame")
        checks.append({
            "name": "multiple_faces",
            "measured_val": faces_count,
            "passed": multi_passed
        })
        
        passed_count = sum(1 for c in checks if c["passed"])
        overall_score = float(passed_count) / len(checks)
        status = "PASS" if passed_count == len(checks) else "FAIL"
        
        unique_issues = list(dict.fromkeys(issues))
        unique_recs = list(dict.fromkeys(recommendations))
        
        return {
            "overall_quality_score": round(overall_score, 2),
            "status": status,
            "checks": checks,
            "issues": unique_issues,
            "recommendations": unique_recs
        }

def _decode_image(image) -> np.ndarray:
    if isinstance(image, bytes):
        nparr = np.frombuffer(image, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes.")
        return img
    elif hasattr(image, 'read'):
        image.seek(0)
        data = image.read()
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes.")
        return img
    elif isinstance(image, str):
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"Could not load image from path: {image}")
        return img
    else:
        if isinstance(image, np.ndarray):
            return image
        raise ValueError("Unsupported image parameter type.")

def assess_document_quality(image) -> dict:
    t_start = time.perf_counter()
    logger.info("Assessment Started: type=document")
    
    try:
        img = _decode_image(image)
        
        blur_analyzer = BlurAnalyzer()
        resolution_analyzer = ResolutionAnalyzer()
        brightness_analyzer = BrightnessAnalyzer()
        exposure_analyzer = ExposureAnalyzer()
        rotation_analyzer = RotationAnalyzer()
        
        blur_res = blur_analyzer.analyze(img)
        resolution_res = resolution_analyzer.analyze(img)
        brightness_res = brightness_analyzer.analyze(img)
        exposure_res = exposure_analyzer.analyze(img)
        rotation_res = rotation_analyzer.analyze(img)
        
        engine = DecisionEngine()
        quality_report = engine.decide_document_quality(
            blur_res=blur_res,
            resolution_res=resolution_res,
            brightness_res=brightness_res,
            exposure_res=exposure_res,
            rotation_res=rotation_res
        )
    except Exception as e:
        logger.exception("Error during document quality assessment")
        quality_report = {
            "overall_quality_score": 0.0,
            "status": "FAIL",
            "checks": [],
            "issues": [f"Image processing failed: {str(e)}"],
            "recommendations": ["Ensure file is a valid image and try again"]
        }
    
    duration = time.perf_counter() - t_start
    status = quality_report["status"]
    score = quality_report["overall_quality_score"]
    num_issues = len(quality_report["issues"])
    
    logger.info(
        "Assessment Completed: type=document status=%s overall_quality_score=%.2f number_of_issues=%d duration=%.4fs",
        status, score, num_issues, duration
    )
    
    return {
        "failure_code": "image_quality_check_failed" if status == "FAIL" else None,
        "retry_allowed": True,
        "quality_report": quality_report
    }

def assess_face_quality(image) -> dict:
    t_start = time.perf_counter()
    logger.info("Assessment Started: type=face")
    
    try:
        img = _decode_image(image)
        
        blur_analyzer = BlurAnalyzer()
        resolution_analyzer = ResolutionAnalyzer()
        brightness_analyzer = BrightnessAnalyzer()
        exposure_analyzer = ExposureAnalyzer()
        face_det_analyzer = FaceDetectionAnalyzer()
        face_size_analyzer = FaceSizeAnalyzer()
        multi_face_analyzer = MultipleFaceAnalyzer()
        
        blur_res = blur_analyzer.analyze(img)
        resolution_res = resolution_analyzer.analyze(img)
        brightness_res = brightness_analyzer.analyze(img)
        exposure_res = exposure_analyzer.analyze(img)
        
        det_res = face_det_analyzer.analyze(img)
        faces = det_res["faces"]
        
        size_res = face_size_analyzer.analyze(faces)
        multi_res = multi_face_analyzer.analyze(faces)
        
        engine = DecisionEngine()
        quality_report = engine.decide_face_quality(
            blur_res=blur_res,
            resolution_res=resolution_res,
            brightness_res=brightness_res,
            exposure_res=exposure_res,
            detection_res=det_res,
            size_res=size_res,
            multi_res=multi_res
        )
    except Exception as e:
        logger.exception("Error during face quality assessment")
        quality_report = {
            "overall_quality_score": 0.0,
            "status": "FAIL",
            "checks": [],
            "issues": [f"Image processing failed: {str(e)}"],
            "recommendations": ["Ensure selfie is a valid image and try again"]
        }
    
    duration = time.perf_counter() - t_start
    status = quality_report["status"]
    score = quality_report["overall_quality_score"]
    num_issues = len(quality_report["issues"])
    
    logger.info(
        "Assessment Completed: type=face status=%s overall_quality_score=%.2f number_of_issues=%d duration=%.4fs",
        status, score, num_issues, duration
    )
    
    return {
        "failure_code": "image_quality_check_failed" if status == "FAIL" else None,
        "retry_allowed": True,
        "quality_report": quality_report
    }

import os
import sys
import json
import argparse
import cv2
import numpy as np

# Ensure django is set up so we can import services and settings correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from services.enterprise_biometric_service import run_biometric_pipeline, get_face_analysis_app

def annotate_image(image_path, out_path, detection_detail, quality_detail):
    """
    Loads the image, draws the face box, landmarks, confidence, and quality score,
    and writes it to the output path.
    """
    img = cv2.imread(image_path)
    if img is None:
        return

    if detection_detail and detection_detail.get("passed") and detection_detail.get("bbox"):
        bbox = detection_detail["bbox"]
        x1, y1, x2, y2 = bbox
        
        # Draw bounding box (Green)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Retrieve keypoints if available from quality detail or detect face again
        # To avoid re-detecting, we query quality details
        conf = detection_detail.get("confidence", 0.0)
        q_score = quality_detail.get("quality_score", 0.0)
        
        # Draw text label above box
        label = f"Conf: {conf:.2f} Q: {q_score:.2f}"
        cv2.putText(img, label, (x1, max(y1 - 10, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

        # Draw landmarks if face has them
        # Let's run a quick query of the app to draw the keypoints
        try:
            app = get_face_analysis_app()
            faces = app.get(cv2.imread(image_path))
            if faces:
                for pt in faces[0].kps.astype(int):
                    cv2.circle(img, (pt[0], pt[1]), 4, (0, 0, 255), -1)
        except Exception:
            pass
    else:
        # Draw red alert warning if face detection failed
        h, w, _ = img.shape
        label = "REJECTED: Face Verification Failed"
        if detection_detail and detection_detail.get("error_message"):
            label += f" ({detection_detail['error_message']})"
        cv2.putText(img, label, (20, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

    # Ensure results directory exists
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)

def main():
    parser = argparse.ArgumentParser(description="Enterprise Face Verification Pipeline Standalone CLI")
    parser.add_argument("--id-image", help="Path to the National ID / Passport image")
    parser.add_argument("--live-image", help="Path to the Live Selfie image")
    parser.add_argument("--threshold", type=float, default=0.60, help="Face matching similarity threshold (default: 0.60)")
    args = parser.parse_args()

    id_image = args.id_image
    live_image = args.live_image

    # Interactive input fallback if no args are supplied
    if not id_image:
        id_image = input("Enter path to National ID image: ").strip()
    if not live_image:
        live_image = input("Enter path to Live Selfie image: ").strip()

    if not id_image or not live_image:
        print("Error: Both ID image and Live Selfie image are required.")
        sys.exit(1)

    print("\n" + "="*50)
    print("  Enterprise Standalone Biometric Verification Pipeline")
    print("="*50)
    print(f"ID Image:   {id_image}")
    print(f"Live Image: {live_image}")
    print(f"Threshold:  {args.threshold}")
    print("="*50 + "\n")

    # Run the pipeline
    report = run_biometric_pipeline(id_image, live_image, threshold=args.threshold)

    # Print clean phase reports
    stages = report["stages"]
    
    # 1. Image Validation
    print("Image Validation")
    if stages["image_validation"]["passed"]:
        print("PASS")
    else:
        print("FAIL")
        id_msg = stages["image_validation"]["detail"].get("id_image", {}).get("error_message", "")
        live_msg = stages["image_validation"]["detail"].get("live_image", {}).get("error_message", "")
        if id_msg:
            print(f"ID Image: {id_msg}")
        if live_msg:
            print(f"Live Selfie: {live_msg}")
    print()

    # 2. Face Detection
    print("Face Detection")
    if stages["face_detection"]["passed"]:
        print("PASS")
        id_conf = stages["face_detection"]["detail"]["id_image"]["confidence"]
        live_conf = stages["face_detection"]["detail"]["live_image"]["confidence"]
        print(f"Confidence (ID): {id_conf:.2f}")
        print(f"Confidence (Live): {live_conf:.2f}")
    else:
        print("FAIL")
        id_msg = stages["face_detection"]["detail"]["id_image"].get("error_message", "")
        live_msg = stages["face_detection"]["detail"]["live_image"].get("error_message", "")
        if id_msg:
            print(f"ID Image: {id_msg}")
        if live_msg:
            print(f"Live Selfie: {live_msg}")
    print()

    # 3. Face Quality & Pose
    print("Face Quality & Pose")
    if stages["face_quality"]["passed"]:
        print("PASS")
        id_q = stages["face_quality"]["detail"]["id_image"]["quality_score"]
        live_q = stages["face_quality"]["detail"]["live_image"]["quality_score"]
        print(f"Quality Score (ID): {id_q:.2f}")
        print(f"Quality Score (Live): {live_q:.2f}")
    else:
        print("FAIL")
        id_msg = stages["face_quality"]["detail"]["id_image"].get("error_message", "")
        live_msg = stages["face_quality"]["detail"]["live_image"].get("error_message", "")
        if id_msg:
            print(f"ID Image: {id_msg}")
        if live_msg:
            print(f"Live Selfie: {live_msg}")
    print()

    # 4. Landmarks
    print("Landmarks")
    if stages["landmarks"]["passed"]:
        print("PASS")
    else:
        print("FAIL")
        id_msg = stages["landmarks"]["detail"]["id_image"].get("error_message", "")
        live_msg = stages["landmarks"]["detail"]["live_image"].get("error_message", "")
        if id_msg:
            print(f"ID Image: {id_msg}")
        if live_msg:
            print(f"Live Selfie: {live_msg}")
    print()

    # 5. Alignment
    print("Alignment")
    if stages["alignment"]["passed"]:
        print("PASS")
    else:
        print("FAIL")
    print()

    # 6. Embedding
    print("Embedding")
    if stages["embedding"]["passed"]:
        print("PASS")
    else:
        print("FAIL")
    print()

    # 7 & 8. Similarity & Decision
    print("Similarity")
    print(f"{report['score']:.4f}")
    print()

    print("Threshold")
    print(f"{report['threshold']:.2f}")
    print()

    print("Decision")
    print(report["decision"])
    if report.get("reason"):
        print(f"Reason: {report['reason']}")
    print("="*50 + "\n")

    # Generate debug artifacts in results/
    os.makedirs("results", exist_ok=True)
    
    # Save JSON report
    # Strip non-serializable objects (such as the Face object reference)
    cleaned_stages = {}
    for stg_name, stg_val in report["stages"].items():
        cleaned_stages[stg_name] = {
            "passed": stg_val["passed"],
            "detail": stg_val["detail"]
        }
    
    output_json = {
        "score": report["score"],
        "threshold": report["threshold"],
        "decision": report["decision"],
        "reason": report["reason"],
        "stages": cleaned_stages
    }
    
    with open("results/verification_result.json", "w") as f:
        json.dump(output_json, f, indent=4)
    print("Saved results/verification_result.json")

    # Generate annotated images
    id_detect_detail = stages["face_detection"]["detail"].get("id_image")
    id_quality_detail = stages["face_quality"]["detail"].get("id_image")
    annotate_image(id_image, "results/id_detected.jpg", id_detect_detail, id_quality_detail)
    print("Saved results/id_detected.jpg")

    live_detect_detail = stages["face_detection"]["detail"].get("live_image")
    live_quality_detail = stages["face_quality"]["detail"].get("live_image")
    annotate_image(live_image, "results/live_detected.jpg", live_detect_detail, live_quality_detail)
    print("Saved results/live_detected.jpg")
    print("\nFace Verification Pipeline completed successfully.")

if __name__ == "__main__":
    main()

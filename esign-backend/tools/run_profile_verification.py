import os
import sys

# Django setup
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "esign_service.settings")
try:
    import django
    django.setup()
except Exception as e:
    print(f"Django setup error: {e}")
    sys.exit(1)

from esign.models import Participant
from services.gemini_ocr_service import extract_identity_data
from services.identity_verification_service import \
    perform_identity_verification


def main():
    id_image_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tests', 'biometric', 'genuine', 'id.jpeg'))
    if not os.path.exists(id_image_path):
        print(f"Error: Genuine ID image not found at {id_image_path}")
        sys.exit(1)

    with open(id_image_path, "rb") as f:
        document_image_bytes = f.read()

    # Determine extracted name first to ensure identity matching passes
    print("Pre-fetching OCR result to get matching name...")
    ocr_res = extract_identity_data(id_image_path)
    extracted_name = ocr_res.get("full_name_en") or ocr_res.get("full_name_ar") or ocr_res.get("full_name") or "Sample Name"
    print(f"Extracted name from ID card: '{extracted_name}'")

    # Get participant and update name
    participant = Participant.objects.first()
    if not participant:
        print("Error: No participants found in the database.")
        sys.exit(1)
        
    original_name = participant.name
    participant.name = extracted_name
    participant.save()
    print(f"Temporarily updated participant ID {participant.id} name to '{extracted_name}'")

    try:
        for i in range(1, 4):
            print(f"\n===================================================")
            print(f"                  RUN #{i}")
            print(f"===================================================")
            perform_identity_verification(participant, document_image_bytes)
    except Exception as e:
        print(f"Error during run: {e}")
    finally:
        # Restore original participant name
        participant.name = original_name
        participant.save()
        print(f"\nRestored participant name to '{original_name}'")

if __name__ == "__main__":
    main()

import logging
from esign.models import RepresentativeCandidate, Participant, ParticipantToken
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

# Title mapping for matching bilingual representatives
TITLE_MAP_EN_TO_AR = {
    "General Manager": "المدير العام",
    "Chief Executive Officer": "الرئيس التنفيذي",
    "CEO": "الرئيس التنفيذي",
    "Managing Director": "العضو المنتدب",
    "Operations Manager": "مدير العمليات",
    "Finance Manager": "مدير المالية",
    "Executive Director": "المدير التنفيذي",
    "Administrative Manager": "المدير الإداري",
    "HR Manager": "مدير الموارد البشرية",
    "Chief Financial Officer": "المدير المالي",
    "CFO": "المدير المالي",
    "Procurement Manager": "مدير المشتريات",
    "IT Manager": "مدير تقنية المعلومات",
    "Office Manager": "مدير المكتب",
    "Project Manager": "مدير المشروع",
    "Hospital Director": "مدير المستشفى",
    "Legal Counsel": "المستشار القانوني",
    "Branch Manager": "مدير الفرع",
    "School Principal": "مدير المدرسة",
}

def generate_candidates(envelope, analysis_result):
    """
    Receives authority extraction results, generates representative candidates,
    deduplicates them, and saves them to the database for the given envelope.
    """
    # Clean existing candidates for this envelope to avoid duplicates on re-runs
    # Delete candidates that are 'pending' or 'ignored'. We do not want to delete
    # candidates that have already been converted to recipients.
    RepresentativeCandidate.objects.filter(envelope=envelope).exclude(status='converted').delete()

    name_en = analysis_result.get("representative_name_en", "").strip()
    name_ar = analysis_result.get("representative_name_ar", "").strip()
    title_en = analysis_result.get("title_en", "").strip()
    title_ar = analysis_result.get("title_ar", "").strip()
    clause_en = analysis_result.get("authority_clause_en", "").strip()
    clause_ar = analysis_result.get("authority_clause_ar", "").strip()

    candidates = []

    # Check if they represent the same person
    is_same = False
    if name_en and name_ar:
        mapped_ar_title = TITLE_MAP_EN_TO_AR.get(title_en)
        if mapped_ar_title == title_ar or (title_en.lower() == "ceo" and title_ar == "الرئيس التنفيذي"):
            is_same = True
        else:
            known_en_titles = list(TITLE_MAP_EN_TO_AR.keys())
            known_ar_titles = list(TITLE_MAP_EN_TO_AR.values())
            if title_en in known_en_titles and title_ar in known_ar_titles:
                is_same = False
            else:
                is_same = True

    if is_same:
        # Merge into a single candidate
        candidates.append({
            "name_en": name_en,
            "name_ar": name_ar,
            "title_en": title_en,
            "title_ar": title_ar,
            "authority_clause": clause_en or clause_ar,
        })
    else:
        # Add separately
        if name_en:
            candidates.append({
                "name_en": name_en,
                "name_ar": "",
                "title_en": title_en,
                "title_ar": "",
                "authority_clause": clause_en,
            })
        if name_ar:
            candidates.append({
                "name_en": "",
                "name_ar": name_ar,
                "title_en": "",
                "title_ar": title_ar,
                "authority_clause": clause_ar,
            })

    db_candidates = []
    for c in candidates:
        # Avoid creating duplicate candidates that already exist and are converted
        if RepresentativeCandidate.objects.filter(
            envelope=envelope,
            name_en=c["name_en"],
            name_ar=c["name_ar"],
            status='converted'
        ).exists():
            continue

        cand = RepresentativeCandidate.objects.create(
            envelope=envelope,
            name_en=c["name_en"],
            name_ar=c["name_ar"],
            title_en=c["title_en"],
            title_ar=c["title_ar"],
            authority_clause=c["authority_clause"],
            status='pending'
        )
        db_candidates.append(cand)

    # Case 1: Single representative found -> Automatically add as recipient
    # (Only auto-convert if no participants already exist for this envelope)
    if len(db_candidates) == 1 and not envelope.participants.exists():
        convert_candidate_to_recipient(db_candidates[0])

    # Combine active db_candidates and already converted ones to return complete list
    all_candidates = list(envelope.representative_candidates.all())
    return all_candidates

def convert_candidate_to_recipient(candidate):
    """
    Converts a representative candidate into a Participant (recipient)
    attached to the candidate's envelope.
    """
    envelope = candidate.envelope
    name = candidate.name_en or candidate.name_ar
    if not name:
        return None

    # Avoid adding duplicate participants with the same name
    participant = envelope.participants.filter(name=name).first()
    if not participant:
        # Determine next order and step number
        step_number = 1
        existing_participants = envelope.participants.all()
        order = existing_participants.count() + 1

        participant = Participant.objects.create(
            envelope=envelope,
            name=name,
            email="",  # Starts blank, user fills it in
            role="signer",
            step_number=step_number,
            order=order,
            status="pending"
        )

        ParticipantToken.objects.create(
            participant=participant,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )

    # Update candidate status
    candidate.status = 'converted'
    candidate.converted_at = timezone.now()
    candidate.save(update_fields=['status', 'converted_at'])

    return participant

def ignore_candidate(candidate):
    """
    Transitions a candidate status to ignored and setsignored_at.
    """
    candidate.status = 'ignored'
    candidate.ignored_at = timezone.now()
    candidate.save(update_fields=['status', 'ignored_at'])
    return candidate


def perform_contract_analysis(filename, file_size, file_bytes, envelope=None):
    """
    Orchestrates the contract analysis: validates PDF pages, runs OCR,
    extracts authority info, generates candidates, and updates audit records.
    """
    import fitz
    import time
    from rest_framework.exceptions import ValidationError
    from services.ocr_service import extract_text_from_image
    from esign.providers.registry import esign_provider_registry
    from services.authority_extraction_service import analyze_contract_authority

    # 1. Size Validation
    from esign.config import esign_config
    if file_size > esign_config.max_upload_size:
        raise ValidationError(f"File size exceeds the {esign_config.max_upload_size // (1024 * 1024)}MB limit.")

    start_time = time.perf_counter()

    # Determine logic based on file type
    if filename.endswith('.pdf'):
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(doc)
            doc.close()
        except Exception as e:
            raise ValidationError(f"Failed to parse PDF pages: {str(e)}")

        if page_count > 20:
            raise ValidationError(f"PDF exceeds the maximum limit of 20 pages (found {page_count}).")

        ocr_result = esign_provider_registry.ocr_provider.extract_text(file_bytes)
        raw_text = ocr_result["raw_text"]
        english_text = ocr_result.get("english_text", raw_text)
        arabic_text = ocr_result.get("arabic_text", raw_text)
        ocr_confidence = ocr_result["ocr_confidence"]
        source = ocr_result["extraction_source"]
        page_count = ocr_result.get("page_count", page_count)
        digital_extraction_ms = ocr_result.get("digital_extraction_ms", 0.0)
        ocr_ms = ocr_result.get("ocr_ms", 0.0)
        dominant_strategy = ocr_result.get("dominant_strategy", source)
        page_strategies = ocr_result.get("page_strategies", {1: source})
        page_quality_scores = ocr_result.get("page_quality_scores", {1: 1.0})
        dominant_arabic_region = ocr_result.get("dominant_arabic_region", "right")
        page_regions = ocr_result.get("page_regions", {1: "right"})
    else:
        # Image processing
        logger.info("Processing image upload using OCR")
        t_ocr_start = time.perf_counter()
        raw_text, ocr_confidence = extract_text_from_image(file_bytes)
        ocr_ms = (time.perf_counter() - t_ocr_start) * 1000
        digital_extraction_ms = 0.0
        english_text = raw_text
        arabic_text = raw_text
        source = "paddleocr"
        page_count = 1
        dominant_strategy = "full_page_ocr"
        page_strategies = {1: "full_page_ocr"}
        page_quality_scores = {1: 0.0}
        dominant_arabic_region = "right"
        page_regions = {1: "right"}
        ocr_result = {
            "ocr_provider": "paddle",
            "ocr_confidence": ocr_confidence,
            "fallback_used": False,
            "ocr_ms": ocr_ms
        }

    # Extract Authority Information
    t_auth_start = time.perf_counter()
    analysis = analyze_contract_authority(raw_text, english_text=english_text, arabic_text=arabic_text)
    authority_extraction_ms = (time.perf_counter() - t_auth_start) * 1000

    end_time = time.perf_counter()
    total_processing_ms = (end_time - start_time) * 1000

    extraction_result = ocr_result

    # ── Generate candidates ──────────────────────────────────────────
    candidates_data = []
    if envelope:
        candidates = generate_candidates(envelope, analysis)
        for cand in candidates:
            candidates_data.append({
                "id": cand.id,
                "name_en": cand.name_en,
                "name_ar": cand.name_ar,
                "title_en": cand.title_en,
                "title_ar": cand.title_ar,
                "status": cand.status,
                "converted_at": cand.converted_at.isoformat() if cand.converted_at else None,
                "ignored_at": cand.ignored_at.isoformat() if cand.ignored_at else None,
                "authority_clause": cand.authority_clause
            })
        
        # Create compliance audit log record
        from esign.models import ContractAnalysisAudit
        ContractAnalysisAudit.objects.update_or_create(
            envelope=envelope,
            defaults={
                "representative_name": f"{analysis.get('representative_name_en', '')} / {analysis.get('representative_name_ar', '')}".strip(" /"),
                "representative_title": f"{analysis.get('title_en', '')} / {analysis.get('title_ar', '')}".strip(" /"),
                "authority_clause": f"{analysis.get('authority_clause_en', '')} / {analysis.get('authority_clause_ar', '')}".strip(" /"),
                "authority_detected": bool(analysis.get("representative_name_en") or analysis.get("representative_name_ar")),
                "ocr_provider": extraction_result.get("ocr_provider", ""),
                "ocr_confidence": extraction_result.get("ocr_confidence"),
            }
        )
    else:
        # In-memory candidate generation (e.g. for ContractAnalysisPage demo)
        name_en = analysis.get("representative_name_en", "").strip()
        name_ar = analysis.get("representative_name_ar", "").strip()
        title_en = analysis.get("title_en", "").strip()
        title_ar = analysis.get("title_ar", "").strip()
        clause_en = analysis.get("authority_clause_en", "").strip()
        clause_ar = analysis.get("authority_clause_ar", "").strip()

        is_same = False
        if name_en and name_ar:
            mapped_ar_title = TITLE_MAP_EN_TO_AR.get(title_en)
            if mapped_ar_title == title_ar or (title_en.lower() == "ceo" and title_ar == "الرئيس التنفيذي"):
                is_same = True
            else:
                is_same = True

        if is_same:
            candidates_data.append({
                "id": "temp-1",
                "name_en": name_en,
                "name_ar": name_ar,
                "title_en": title_en,
                "title_ar": title_ar,
                "status": "pending",
                "converted_at": None,
                "ignored_at": None,
                "authority_clause": clause_en or clause_ar
            })
        else:
            if name_en:
                candidates_data.append({
                    "id": "temp-1",
                    "name_en": name_en,
                    "name_ar": "",
                    "title_en": title_en,
                    "title_ar": "",
                    "status": "pending",
                    "converted_at": None,
                    "ignored_at": None,
                    "authority_clause": clause_en
                })
            if name_ar:
                candidates_data.append({
                    "id": "temp-2",
                    "name_en": "",
                    "name_ar": name_ar,
                    "title_en": "",
                    "title_ar": title_ar,
                    "status": "pending",
                    "converted_at": None,
                    "ignored_at": None,
                    "authority_clause": clause_ar
                })

    representatives_found = len(candidates_data) > 0
    return {
        "representative_name_en": analysis.get("representative_name_en", ""),
        "representative_name_ar": analysis.get("representative_name_ar", ""),
        "title_en": analysis.get("title_en", ""),
        "title_ar": analysis.get("title_ar", ""),
        "authority_clause_en": analysis.get("authority_clause_en", ""),
        "authority_clause_ar": analysis.get("authority_clause_ar", ""),
        "representatives_found": representatives_found,
        "authority_detected": representatives_found,
        "count": len(candidates_data),
        "candidates": candidates_data
    }

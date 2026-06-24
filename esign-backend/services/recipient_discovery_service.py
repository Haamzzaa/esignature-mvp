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

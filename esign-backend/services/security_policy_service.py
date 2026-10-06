from esign.models import (ContractAnalysis, ParticipantAuthorizationState,
                          SignerIdentityVerification)
from services.authorization_service import authorize_signer


def get_authorization_status(participant):
    """
    Returns full authorization structure detailing which policies are required
    and whether the participant satisfies them.
    """
    # Safely get or create the ParticipantAuthorizationState
    state, _ = ParticipantAuthorizationState.objects.get_or_create(participant=participant)
    envelope = participant.envelope

    email_otp_req = envelope.email_otp_required
    email_otp_sat = state.email_verified

    sms_otp_req = envelope.sms_otp_required
    sms_otp_sat = state.sms_verified

    terms_req = envelope.terms_acceptance_required
    terms_sat = state.accepted_terms

    verification = SignerIdentityVerification.objects.filter(participant=participant).first()
    contract_analysis = ContractAnalysis.objects.filter(document=envelope.document).first()
    if not contract_analysis and envelope.document:
        contract_analysis = ContractAnalysis.objects.filter(file_hash=envelope.document.file_hash).first()
    auth_res = authorize_signer(participant, verification, contract_analysis)

    from esign.models import BiometricVerification, VerificationSession
    biometric = BiometricVerification.objects.filter(participant=participant).first()
    session = VerificationSession.objects.filter(participant=participant).first()

    # Determine Review Status
    review_status = None
    review_reason = None
    resubmit_step = state.manual_review_resubmit_step or None
    review_notes = state.manual_review_notes or None

    is_under_manual_review = (
        (verification is not None and verification.status == "requires_manual_review") or
        (biometric is not None and biometric.status == "requires_manual_review") or
        (session is not None and session.status == "requires_manual_review") or
        (auth_res.get("status") == "MANUAL_REVIEW_REQUIRED")
    )

    if state.manual_review_rejected:
        review_status = "rejected"
        review_reason = state.manual_review_notes or "Verification rejected by administrative review."
    elif state.manual_review_approved:
        review_status = "approved"
        review_reason = None
    elif state.manual_review_resubmit_step:
        review_status = "resubmission_required"
        review_reason = state.manual_review_notes or "Resubmission requested by reviewer."
    elif is_under_manual_review:
        review_status = "under_review"
        if verification and verification.status == "requires_manual_review":
            review_reason = verification.failure_reason or "Identity verification requires review."
        elif biometric and biometric.status == "requires_manual_review":
            review_reason = biometric.failure_reason or "Face biometric verification requires review."
        elif auth_res.get("status") == "MANUAL_REVIEW_REQUIRED":
            review_reason = auth_res.get("reason") or "Representative authorization requires review."
        else:
            review_reason = session.failure_reason if session else "Administrative review required."

    # Compute step satisfaction with manual review approval overrides
    national_id_req = envelope.national_id_required
    if state.manual_review_approved and national_id_req:
        national_id_sat = True
    elif state.manual_review_resubmit_step == "national_id":
        national_id_sat = False
    else:
        national_id_sat = (verification is not None and verification.status == "verified")

    face_biometric_req = envelope.face_biometric_required
    if state.manual_review_approved and face_biometric_req:
        face_biometric_sat = True
    elif state.manual_review_resubmit_step in ["face", "face_biometric"]:
        face_biometric_sat = False
    else:
        face_biometric_sat = (biometric is not None and biometric.status == "matched")

    # Enforce representative match for signers via the Authorization Engine
    if participant.role == "signer":
        representative_match_req = envelope.representative_match_required
        if state.manual_review_approved and representative_match_req:
            representative_match_sat = True
            auth_res["authorized"] = True
            auth_res["status"] = "AUTHORIZED"
        elif state.manual_review_resubmit_step in ["representative", "representative_match"]:
            representative_match_sat = False
            auth_res["authorized"] = False
        else:
            representative_match_sat = auth_res["authorized"]
    else:
        representative_match_req = envelope.representative_match_required
        representative_match_sat = False
        if hasattr(participant, "representative_verification") and participant.representative_verification:
            representative_match_sat = (participant.representative_verification.status == "matched")

    # If rejected by manual review, block authorization
    if state.manual_review_rejected:
        if national_id_req:
            national_id_sat = False
        if face_biometric_req:
            face_biometric_sat = False
        if representative_match_req:
            representative_match_sat = False

    requirements = {
        "email_otp": {"required": email_otp_req, "satisfied": email_otp_sat},
        "sms_otp": {"required": sms_otp_req, "satisfied": sms_otp_sat},
        "national_id": {"required": national_id_req, "satisfied": national_id_sat},
        "face_biometric": {"required": face_biometric_req, "satisfied": face_biometric_sat},
        "representative_match": {"required": representative_match_req, "satisfied": representative_match_sat},
        "terms_acceptance": {"required": terms_req, "satisfied": terms_sat}
    }

    missing_requirements = []
    for code, state_dict in requirements.items():
        if state_dict["required"] and not state_dict["satisfied"]:
            missing_requirements.append(code)

    authorized = (len(missing_requirements) == 0) and not state.manual_review_rejected

    # Secure verification summaries for UI consumption without exposing embeddings, API keys or internal raw data.
    identity_summary = None
    if verification:
        identity_summary = {
            "full_name_en": verification.full_name_en,
            "full_name_ar": verification.full_name_ar,
            "national_id": verification.national_id_number,
            "country": verification.country,
            "document_type": verification.document_type,
            "expiry_date": verification.expiry_date.isoformat() if verification.expiry_date else None,
            "status": verification.status
        }

    biometric_summary = None
    if biometric:
        biometric_summary = {
            "status": biometric.status,
            "similarity_score": biometric.similarity_score,
            "provider": biometric.provider
        }

    derived_status = "NOT_AUTHORIZED"
    if review_status == "under_review":
        derived_status = "requires_manual_review"
    elif review_status == "rejected":
        derived_status = "REJECTED"
    elif authorized:
        derived_status = "AUTHORIZED"
    elif participant.role == "signer":
        derived_status = auth_res.get("status", "NOT_AUTHORIZED")

    return {
        "authorized": authorized,
        "requirements": requirements,
        "missing_requirements": missing_requirements,
        "status": derived_status,
        "reason": review_reason or (auth_res.get("reason") if participant.role == "signer" else None),
        "review_status": review_status,
        "review_reason": review_reason,
        "review_notes": review_notes,
        "resubmit_step": resubmit_step,
        "matched_language": auth_res.get("matched_language") if participant.role == "signer" else None,
        "matched_representative": auth_res.get("matched_representative") if participant.role == "signer" else None,
        "identity_summary": identity_summary,
        "biometric_summary": biometric_summary
    }

def evaluate_signer_requirements(participant):
    """
    Returns simple required flags.
    """
    status = get_authorization_status(participant)
    return {k + "_required": v["required"] for k, v in status["requirements"].items()}

def evaluate_signer_authorization(participant):
    """
    Returns authorized status and missing requirements code list.
    """
    status = get_authorization_status(participant)
    return {
        "authorized": status["authorized"],
        "missing_requirements": status["missing_requirements"]
    }

def can_sign(participant):
    """
    Determines if the participant is fully authorized to sign.
    """
    status = get_authorization_status(participant)
    return status["authorized"]

from services.identity_scores import ScoredCandidateName, ScoredCandidateIdentifier, ScoredCandidateDate

def select_best_name_candidate(scored_candidates: list[ScoredCandidateName]) -> ScoredCandidateName | None:
    if not scored_candidates:
        return None
    sorted_candidates = sorted(
        scored_candidates,
        key=lambda c: (
            c.score,
            int(not c.value.isupper() and not c.value.islower()),
            len(c.value.split()),
            len(c.value)
        ),
        reverse=True
    )
    return sorted_candidates[0]

def select_best_identifier_candidate(scored_candidates: list[ScoredCandidateIdentifier]) -> ScoredCandidateIdentifier | None:
    if not scored_candidates:
        return None
    sorted_candidates = sorted(
        scored_candidates,
        key=lambda c: (
            c.score,
            len(c.value.split()),
            len(c.value)
        ),
        reverse=True
    )
    return sorted_candidates[0]

def select_best_birth_date_candidate(scored_candidates: list[ScoredCandidateDate]) -> ScoredCandidateDate | None:
    if not scored_candidates:
        return None
    # Only consider date_type == "birth_date"
    birth_candidates = [c for c in scored_candidates if c.date_type == "birth_date"]
    if not birth_candidates:
        return None
    sorted_candidates = sorted(
        birth_candidates,
        key=lambda c: (
            c.score,
            len(c.value.split()),
            len(c.value)
        ),
        reverse=True
    )
    return sorted_candidates[0]

def select_best_expiry_date_candidate(scored_candidates: list[ScoredCandidateDate]) -> ScoredCandidateDate | None:
    if not scored_candidates:
        return None
    # Only consider date_type == "expiry_date"
    expiry_candidates = [c for c in scored_candidates if c.date_type == "expiry_date"]
    if not expiry_candidates:
        return None
    sorted_candidates = sorted(
        expiry_candidates,
        key=lambda c: (
            c.score,
            len(c.value.split()),
            len(c.value)
        ),
        reverse=True
    )
    return sorted_candidates[0]

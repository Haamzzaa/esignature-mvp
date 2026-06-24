from services.identity_confidence import FieldConfidence, IdentityConfidenceResult

def calculate_name_confidence(scored_name_candidates, selected_name, layout_name=None, ocr_confidence=None):
    if not selected_name:
        return FieldConfidence(0.0, ["no_name_selected"])
    
    reasons = []
    confidence = 0.5
    
    # 1. High top score
    if selected_name.score >= 8.0:
        confidence += 0.2
        reasons.append("high_candidate_score")
        
    # 2. Agreement with layout parser
    if layout_name:
        from services.national_identity_service import normalize_identity_fields
        norm_selected = normalize_identity_fields(selected_name.value).lower()
        norm_layout = normalize_identity_fields(layout_name).lower()
        if norm_selected == norm_layout:
            confidence += 0.2
            reasons.append("layout_agreement")
            
    # 3. Single candidate
    if scored_name_candidates and len(scored_name_candidates) == 1:
        confidence += 0.1
        reasons.append("single_candidate")
        
    # 4. Clear winner / Multiple close competitors
    if scored_name_candidates and len(scored_name_candidates) > 1:
        top = scored_name_candidates[0]
        second = scored_name_candidates[1]
        
        if (top.score - second.score) >= 2.0:
            confidence += 0.15
            reasons.append("clear_winner")
            
        close_competitors = [c for c in scored_name_candidates[1:] if (top.score - c.score) <= 1.0]
        if close_competitors:
            confidence -= 0.2
            reasons.append("multiple_close_candidates")
            
    confidence = max(0.0, min(1.0, confidence))
    return FieldConfidence(round(confidence, 2), reasons)

def calculate_identifier_confidence(scored_identifier_candidates, selected_identifier):
    if not selected_identifier:
        return FieldConfidence(0.0, ["no_identifier_selected"])
        
    reasons = []
    confidence = 0.5
    
    # 1. Expected identifier length
    if any(r in selected_identifier.reasons for r in ["expected_identifier_length", "passport_pattern"]):
        confidence += 0.2
        reasons.append("expected_identifier_length")
        
    # 2. Normalized identifier
    if "normalized_successfully" in selected_identifier.reasons:
        confidence += 0.1
        reasons.append("normalized_identifier")
        
    # 3. Clear winner
    if scored_identifier_candidates:
        if len(scored_identifier_candidates) == 1:
            confidence += 0.2
            reasons.append("clear_winner")
        elif len(scored_identifier_candidates) > 1:
            top = scored_identifier_candidates[0]
            second = scored_identifier_candidates[1]
            if (top.score - second.score) >= 2.0:
                confidence += 0.2
                reasons.append("clear_winner")
                
    confidence = max(0.0, min(1.0, confidence))
    return FieldConfidence(round(confidence, 2), reasons)

def calculate_birth_date_confidence(scored_date_candidates, selected_birth_date):
    if not selected_birth_date:
        return FieldConfidence(0.0, ["no_birth_date_selected"])
        
    reasons = []
    confidence = 0.5
    
    # 1. Adult age range
    if "adult_age_range" in selected_birth_date.reasons:
        confidence += 0.35
        reasons.append("adult_age_range")
        
    # 2. Clear winner
    birth_candidates = [c for c in (scored_date_candidates or []) if c.date_type == "birth_date"]
    if birth_candidates:
        if len(birth_candidates) == 1:
            confidence += 0.15
            reasons.append("clear_winner")
        elif len(birth_candidates) > 1:
            top = birth_candidates[0]
            second = birth_candidates[1]
            if (top.score - second.score) >= 2.0:
                confidence += 0.15
                reasons.append("clear_winner")
                
    confidence = max(0.0, min(1.0, confidence))
    return FieldConfidence(round(confidence, 2), reasons)

def calculate_expiry_date_confidence(scored_date_candidates, selected_expiry_date):
    if not selected_expiry_date:
        return None
        
    reasons = []
    confidence = 0.5
    
    # 1. Future expiry
    if "future_expiry" in selected_expiry_date.reasons:
        confidence += 0.35
        reasons.append("future_expiry")
        
    # 2. Clear winner
    expiry_candidates = [c for c in (scored_date_candidates or []) if c.date_type == "expiry_date"]
    if expiry_candidates:
        if len(expiry_candidates) == 1:
            confidence += 0.15
            reasons.append("clear_winner")
        elif len(expiry_candidates) > 1:
            top = expiry_candidates[0]
            second = expiry_candidates[1]
            if (top.score - second.score) >= 2.0:
                confidence += 0.15
                reasons.append("clear_winner")
                
    confidence = max(0.0, min(1.0, confidence))
    return FieldConfidence(round(confidence, 2), reasons)

def calculate_overall_confidence(name_confidence, identifier_confidence, birth_date_confidence, expiry_date_confidence):
    weights = {
        "name": 0.40,
        "identifier": 0.30,
        "birth_date": 0.20,
        "expiry_date": 0.10
    }
    values = {
        "name": name_confidence.confidence if name_confidence else None,
        "identifier": identifier_confidence.confidence if identifier_confidence else None,
        "birth_date": birth_date_confidence.confidence if birth_date_confidence else None,
        "expiry_date": expiry_date_confidence.confidence if expiry_date_confidence else None
    }
    
    active_weights = 0.0
    weighted_sum = 0.0
    for key, val in values.items():
        if val is not None:
            active_weights += weights[key]
            weighted_sum += weights[key] * val
            
    if active_weights == 0.0:
        return 0.0
        
    overall = weighted_sum / active_weights
    return round(max(0.0, min(1.0, overall)), 2)

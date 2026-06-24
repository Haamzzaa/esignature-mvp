import re
import datetime
from datetime import date
from services.identity_scores import ScoredCandidateName, ScoredCandidateIdentifier, ScoredCandidateDate

# --- Module-Level Scoring Constants ---

# Name Scoring
MULTI_WORD_BONUS = 1.0
STANDARD_LENGTH_WORDS_BONUS = 1.5
STANDARD_CHAR_LENGTH_BONUS = 1.0
PROXIMITY_BONUS = 1.5
ARABIC_NAME_BONUS = 1.0
LATIN_NAME_BONUS = 1.0
ALPHABETIC_BONUS = 1.0
BOUNDARY_CONTEXT_BONUS = 3.0

OCR_ARTIFACT_PENALTY = -2.0
UNREASONABLE_LENGTH_PENALTY = -2.0
NON_NAME_KEYWORD_PENALTY = -3.0
NON_LETTER_SYMBOLS_PENALTY = -1.5

# Identifier Scoring
EXPECTED_IDENTIFIER_LENGTH_BONUS = 2.0
PASSPORT_PATTERN_BONUS = 2.0
NUMERIC_SEQUENCE_BONUS = 1.0
NORMALIZATION_SUCCESS_BONUS = 1.0

UNUSUAL_IDENTIFIER_LENGTH_PENALTY = -2.0
EXCESSIVE_SEPARATORS_PENALTY = -1.5

# Date Scoring
VALID_GREGORIAN_BONUS = 1.0
VALID_HIJRI_BONUS = 1.5
ADULT_AGE_BONUS = 2.5
FUTURE_EXPIRY_BONUS = 2.0

IMPOSSIBLE_YEAR_PENALTY = -3.0
MINOR_UNDER_FIVE_PENALTY = -3.0
UNREASONABLE_AGE_PENALTY = -3.0


# --- OCR Noise Detector Helper ---

def contains_ocr_artifacts(candidate) -> tuple[bool, list[str]]:
    """
    Checks if the candidate value contains OCR noise or artifacts:
    - excessive punctuation (more than 2 special symbols)
    - high symbol density (less than 80% letters or spaces)
    - repeated separators (consecutive spaces/dashes/slashes)
    - unusual characters (characters outside standard Latin/Arabic letters, spaces, dot, dash, quote)
    Returns (has_artifacts, reasons_found).
    """
    reasons = []
    val = candidate.value if hasattr(candidate, 'value') else str(candidate)

    # 1. Excessive punctuation
    punctuation_chars = [c for c in val if c in '.,!?;:()\'"-+=\[\]{}/\\<>#@$%^&*`~|_']
    if len(punctuation_chars) > 2:
        reasons.append("excessive_punctuation")

    # 2. Symbol density
    letters_and_spaces = len(re.findall(r'[a-zA-Z\u0600-\u06FF\s]', val))
    total_len = len(val)
    if total_len > 0:
        density = letters_and_spaces / total_len
        if density < 0.8:
            reasons.append("high_symbol_density")

    # 3. Repeated separators
    if re.search(r'\s{2,}|-{2,}|/{2,}', val):
        reasons.append("repeated_separators")

    # 4. Unusual characters
    # e.g., 'Ñ', 'ñ', or '<'
    unusual_char_pattern = re.compile(r'[^\w\s\u0600-\u06FF.\'-]')
    if unusual_char_pattern.search(val) or 'Ñ' in val or 'ñ' in val or '<' in val or '_' in val:
        reasons.append("unusual_characters")

    return len(reasons) > 0, reasons


# --- Scoring Services ---

def compute_boundary_bonus(candidate_value: str, source_line: str) -> tuple[float, list[str]]:
    """
    Examines whether the candidate appears immediately before identity-related markers
    inside the original OCR source line.
    """
    boundary_markers = [
        "DOB", "Date of Birth", "Birth Date", "Gender", "Male", "Female", "Nationality",
        "تاريخ الميلاد", "الجنس", "ذكر", "أنثى", "الجنسية"
    ]
    
    line_lower = source_line.lower()
    val_lower = candidate_value.lower()
    
    # Find all occurrences of candidate_value in source_line
    start_indices = []
    idx = line_lower.find(val_lower)
    while idx != -1:
        start_indices.append(idx)
        idx = line_lower.find(val_lower, idx + 1)
        
    if not start_indices:
        return 0.0, []
        
    for val_idx in start_indices:
        val_end_idx = val_idx + len(candidate_value)
        
        for marker in boundary_markers:
            marker_lower = marker.lower()
            marker_idx = line_lower.find(marker_lower, val_end_idx)
            if marker_idx != -1:
                intermediate_text = source_line[val_end_idx:marker_idx]
                cleaned_intermediate = re.sub(r'[^\w]', '', intermediate_text)
                
                # If intermediate text length is small (allowing spaces, slashes, or short OCR junk)
                if len(cleaned_intermediate) <= 12:
                    # Verify candidate starts at the beginning of the name (allow small label/OCR prefix noise)
                    text_before = source_line[:val_idx]
                    text_before_clean = re.sub(r'(?i)\b(?:full\s+)?name\b|\bالاسم\b|\bالكامل\b', '', text_before)
                    text_before_clean = re.sub(r'[^\w]', '', text_before_clean)
                    if len(text_before_clean) <= 5:
                        return BOUNDARY_CONTEXT_BONUS, ["boundary_context"]
                        
    return 0.0, []

def score_name_candidates(candidates, raw_text) -> list[ScoredCandidateName]:
    """
    Evaluate candidate names using positive and negative heuristic signals.
    Returns scored candidates sorted by descending score.
    """
    if not candidates:
        return []

    scored = []
    for c in candidates:
        score = 0.0
        reasons = []

        # 1. Multi-word bonus
        word_count = len(c.value.split())
        if word_count > 1:
            score += MULTI_WORD_BONUS
            reasons.append("multi_word")

        # 2. Standard word count bonus
        if 2 <= word_count <= 5:
            score += STANDARD_LENGTH_WORDS_BONUS
            reasons.append("standard_name_length_words")

        # 3. Character length standard check
        char_len = len(c.value)
        if 5 <= char_len <= 50:
            score += STANDARD_CHAR_LENGTH_BONUS
            reasons.append("standard_char_length")
        elif char_len < 3 or char_len > 60:
            score += UNREASONABLE_LENGTH_PENALTY
            reasons.append("unreasonable_length")

        # 4. Proximity to DOB or gender keywords in the source line
        proximity_keywords = ["birth", "dob", "d.o.b", "yob", "ولد", "ميلاد", "gender", "male", "female", "ذكر", "أنثى"]
        if any(k in c.source_line.lower() for k in proximity_keywords):
            score += PROXIMITY_BONUS
            reasons.append("near_identity_keywords")

        # 5. Alphabetic ratio
        letters_count = len(re.findall(r'[a-zA-Z\u0600-\u06FF]', c.value))
        if char_len > 0:
            ratio = letters_count / char_len
            if ratio > 0.90:
                score += ALPHABETIC_BONUS
                reasons.append("mostly_alphabetic")
            elif ratio < 0.50:
                score += NON_LETTER_SYMBOLS_PENALTY
                reasons.append("non_letter_symbols")

        # 6. Language checks
        if "arabic_name" in c.reasons or any('\u0600' <= char <= '\u06FF' for char in c.value):
            score += ARABIC_NAME_BONUS
            reasons.append("arabic_name")
        if "latin_name" in c.reasons or any(char.isalpha() and char.isascii() for char in c.value):
            score += LATIN_NAME_BONUS
            reasons.append("latin_name")

        # 7. OCR Artifact checks (using isolated helper)
        has_artifacts, artifact_reasons = contains_ocr_artifacts(c)
        if has_artifacts:
            score += OCR_ARTIFACT_PENALTY
            reasons.extend(artifact_reasons)

        # 8. Non-name metadata keywords check
        non_name_keywords = [
            "government", "passport", "identity", "kingdom", "ministry", "card", "india", "saudi", "permit", "residence",
            "number", "no.", "num",
            "الهوية", "الوطنية", "إقامة", "جواز", "السفر", "رقم", "الرقم",
            "الهويه", "الوطنيه", "اقامه"
        ]
        if any(kw in c.value.lower() for kw in non_name_keywords):
            score += NON_NAME_KEYWORD_PENALTY
            reasons.append("non_name_metadata_keyword")

        # 9. Boundary context bonus
        boundary_bonus, boundary_reasons = compute_boundary_bonus(
            c.value,
            c.source_line
        )
        score += boundary_bonus
        reasons.extend(boundary_reasons)

        scored.append(ScoredCandidateName(
            value=c.value,
            score=round(score, 2),
            reasons=reasons,
            source_line=c.source_line
        ))

    # Sort in descending order
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def score_identifier_candidates(candidates, raw_text) -> list[ScoredCandidateIdentifier]:
    """
    Evaluate candidate identifiers.
    Returns scored candidates sorted by descending score.
    """
    if not candidates:
        return []

    scored = []
    for c in candidates:
        score = 0.0
        reasons = []

        normalized = re.sub(r'[\s-]', '', c.value)

        # 1. Expected length (10 or 12 digits)
        if len(normalized) in (10, 12):
            score += EXPECTED_IDENTIFIER_LENGTH_BONUS
            reasons.append("expected_identifier_length")
        elif c.identifier_type != "passport":
            score += UNUSUAL_IDENTIFIER_LENGTH_PENALTY
            reasons.append("unusual_identifier_length")

        # 2. Passport pattern check
        if c.identifier_type == "passport":
            score += PASSPORT_PATTERN_BONUS
            reasons.append("passport_pattern")

        # 3. Purely numeric check (for non-passports)
        if normalized.isdigit() and c.identifier_type != "passport":
            score += NUMERIC_SEQUENCE_BONUS
            reasons.append("numeric_sequence")

        # 4. Normalization success
        if normalized:
            score += NORMALIZATION_SUCCESS_BONUS
            reasons.append("normalized_successfully")

        # 5. Excessive separators
        separators_count = len(re.findall(r'[\s-]', c.value))
        if separators_count > 3:
            score += EXCESSIVE_SEPARATORS_PENALTY
            reasons.append("excessive_separators")

        scored.append(ScoredCandidateIdentifier(
            value=c.value,
            score=round(score, 2),
            reasons=reasons,
            source_line=c.source_line,
            normalized_value=c.normalized_value
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def score_date_candidates(candidates, raw_text) -> list[ScoredCandidateDate]:
    """
    Evaluate candidate dates.
    Returns scored candidates sorted by descending score.
    """
    if not candidates:
        return []

    scored = []
    for c in candidates:
        score = 0.0
        reasons = []

        # Current reference year (2026)
        current_year = 2026

        # 1. Gregorian date check
        if 1900 <= c.value.year <= 2100:
            score += VALID_GREGORIAN_BONUS
            reasons.append("valid_gregorian")
        else:
            score += IMPOSSIBLE_YEAR_PENALTY
            reasons.append("impossible_year")

        # 2. Hijri conversion check
        # Check if the year range was Hijri based on the source line (typically contains Hijri years like 14xx)
        is_hijri_source = False
        for yr in range(1300, 1501):
            if str(yr) in c.source_line:
                is_hijri_source = True
                break
        
        if is_hijri_source:
            score += VALID_HIJRI_BONUS
            reasons.append("valid_hijri_conversion")

        # 3. Birth date signal evaluations
        if c.date_type == "birth_date":
            age = current_year - c.value.year
            if 18 <= age <= 100:
                score += ADULT_AGE_BONUS
                reasons.append("adult_age_range")
            elif age < 5:
                score += MINOR_UNDER_FIVE_PENALTY
                reasons.append("minor_under_five")
            elif age > 120:
                score += UNREASONABLE_AGE_PENALTY
                reasons.append("unreasonable_age_over_120")

        # 4. Expiry date signal evaluations
        elif c.date_type == "expiry_date":
            # Expiry in the future relative to current validation date (June 24, 2026)
            reference_date = datetime.date(2026, 6, 24)
            if c.value > reference_date:
                score += FUTURE_EXPIRY_BONUS
                reasons.append("future_expiry")

        scored.append(ScoredCandidateDate(
            value=c.value.isoformat(),
            score=round(score, 2),
            reasons=reasons,
            source_line=c.source_line,
            date_type=c.date_type
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored

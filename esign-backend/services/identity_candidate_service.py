import re
import datetime
from datetime import date
from services.identity_candidates import CandidateName, CandidateIdentifier, CandidateDate

# ---------------------------------------------------------------------------
# Metadata label blocklist
# Candidate values whose *normalized* form exactly matches any entry here
# will never be selected as a person name.
# Normalization: lowercase + collapse whitespace.
# ---------------------------------------------------------------------------
BLOCKED_NAME_CANDIDATES = {
    "national id",
    "national identity",
    "identity card",
    "id card",
    "card",
    "passport",
    "permit",
    "government",
    "kingdom of saudi arabia",
    "saudi arabia",
    "saudi",
    "ministry",
    "authority",
    "republic",
    "india",
    "iqama",
    "residence permit",
    "driving license",
    "driving licence",
    "id",
}


def _is_blocked_name(value: str) -> bool:
    """Return True if *value* normalizes to a blocked metadata label."""
    normalized = " ".join(value.lower().split())
    return normalized in BLOCKED_NAME_CANDIDATES

def generate_name_candidates(raw_text: str) -> list[CandidateName]:
    """
    Generate candidate names by:
    - Splitting OCR text into lines.
    - Removing empty lines.
    - Normalizing whitespace.
    - Applying normalize_identity_fields() to each line to keep Arabic variants consistent.
    - Searching for multi-word alphabetic sequences, Arabic names, Latin names, and mixed-language names.
    Preserves the raw source_line for proximity-based scoring.
    """
    if not raw_text:
        return []

    from services.national_identity_service import normalize_identity_fields

    candidates = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

    # Keyword Boundary Splitting
    MARKERS = [
        "DOB:",
        "Date of Birth",
        "Male",
        "Female",
        "Gender",
        "Expiry",
        "Issue Date",
        "Valid Until",
        "Nationality",
        "الاسم",
        "الجنس",
        "تاريخ الميلاد",
        "تاريخ الانتهاء"
    ]

    patterns = []
    for m in MARKERS:
        pattern = re.escape(m)
        if re.match(r'^\w', m):
            pattern = r'\b' + pattern
        if re.match(r'\w$', m):
            pattern = pattern + r'\b'
        patterns.append(pattern)
    patterns.sort(key=len, reverse=True)
    split_regex = re.compile('|'.join(patterns), re.IGNORECASE)

    # Pattern to find alphabetic word sequences (both Latin and Arabic letters, allowing spaces)
    name_seq_pattern = re.compile(
        r'[^\d_\W]+(?:[\s\'-]+[^\d_\W]+)*'
    )

    for line in lines:
        # Split line around common identity markers
        sub_lines = [p.strip() for p in split_regex.split(line) if p.strip()]

        for sub_line in sub_lines:
            normalized_part = normalize_identity_fields(sub_line)
            if not normalized_part:
                continue

            # Search for candidates in the normalized part
            for match in name_seq_pattern.finditer(normalized_part):
                val = match.group(0).strip()
                
                # Clean label prefixes if they are at the start
                cleaned = re.sub(r'(?i)^(full\s+)?name\s*', '', val)
                cleaned = re.sub(r'^الاسم(\s+الكامل)?\s*', '', cleaned)
                cleaned = cleaned.strip()

                if not cleaned or len(cleaned) < 2:
                    continue

                # Sliding Window Candidate Generation (windows of sizes 5, 4, 3, 2, 1)
                words = cleaned.split()
                N = len(words)
                
                for w in [5, 4, 3, 2, 1]:
                    if w <= N:
                        for i in range(N - w + 1):
                            window_words = words[i:i+w]
                            candidate_val = " ".join(window_words)
                            
                            if not candidate_val or len(candidate_val) < 2:
                                continue

                            # Skip metadata document labels
                            if _is_blocked_name(candidate_val):
                                continue

                            # Populate reasons
                            reasons = []
                            has_arabic = bool(re.search(r'[\u0600-\u06FF]', candidate_val))
                            has_latin = bool(re.search(r'[a-zA-Z]', candidate_val))

                            if has_arabic:
                                reasons.append("arabic_name")
                            if has_latin:
                                reasons.append("latin_name")
                            if has_arabic and has_latin:
                                reasons.append("mixed_language")
                            if len(candidate_val.split()) > 1:
                                reasons.append("multi_word")

                            candidates.append(CandidateName(
                                value=candidate_val,
                                source_line=line,
                                reasons=reasons,
                                normalized_value=candidate_val
                            ))

    # Deduplicate candidates based on (value, source_line)
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c.value, c.source_line)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    return unique_candidates

def generate_identifier_candidates(raw_text: str) -> list[CandidateIdentifier]:
    """
    Generate candidate identifiers generically:
    - national_id: 10-12 digit sequences (Aadhaar, Saudi national ID, Iqama)
    - passport: letter followed by 7-9 digits
    - unknown: other digit sequences (7-9 or 13-15 digits)
    Normalizes by stripping spaces and hyphens.
    Preserves raw source line.
    """
    if not raw_text:
        return []

    candidates = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

    for line in lines:
        # 1. Match national_id: 10-12 digits with optional spaces/hyphens
        for match in re.finditer(r'\b(?:\d[\s-]*){10,12}\b', line):
            val_raw = match.group(0)
            normalized = re.sub(r'[\s-]', '', val_raw)
            if len(normalized) in (10, 11, 12):
                candidates.append(CandidateIdentifier(
                    value=val_raw,
                    source_line=line,
                    identifier_type="national_id",
                    normalized_value=normalized
                ))

        # 2. Match passport: letter followed by 7-9 digits with optional spaces/hyphens
        for match in re.finditer(r'\b[a-zA-Z][\s-]*(?:\d[\s-]*){7,9}\b', line):
            val_raw = match.group(0)
            normalized = re.sub(r'[\s-]', '', val_raw).upper()
            candidates.append(CandidateIdentifier(
                value=val_raw,
                source_line=line,
                identifier_type="passport",
                normalized_value=normalized
            ))

        # 3. Match unknown: other digit sequences of 5-9 digits or 13-15 digits
        for match in re.finditer(r'\b(?:\d[\s-]*){5,9}\b|\b(?:\d[\s-]*){13,15}\b', line):
            val_raw = match.group(0)
            normalized = re.sub(r'[\s-]', '', val_raw)
            # Make sure this isn't already part of a 10-12 digit sequence matched above
            if len(normalized) in (5, 6, 7, 8, 9, 13, 14, 15):
                candidates.append(CandidateIdentifier(
                    value=val_raw,
                    source_line=line,
                    identifier_type="unknown",
                    normalized_value=normalized
                ))

    # Deduplicate candidates based on (value, source_line, identifier_type)
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c.value, c.source_line, c.identifier_type)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    return unique_candidates

def generate_date_candidates(raw_text: str) -> list[CandidateDate]:
    """
    Generate candidate dates from text:
    - Supports space, dash, or slash separators.
    - Converts Hijri years (1300-1500) to Gregorian.
    - Classifies date_type as birth_date, expiry_date, or unknown.
    """
    if not raw_text:
        return []

    candidates = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

    def parse_to_date_obj(y: int, m: int, d: int) -> date:
        # Check if Hijri year range
        if 1300 <= y <= 1500:
            g_year = int(y * 0.97 + 622)
            g_month = max(1, min(12, m))
            g_day = max(1, min(31, d))
            try:
                return datetime.date(g_year, g_month, g_day)
            except ValueError:
                return datetime.date(g_year, g_month, 1)
        elif 1900 <= y <= 2100:
            try:
                return datetime.date(y, m, d)
            except ValueError:
                return None
        return None

    def determine_date_type(line_str: str) -> str:
        line_lower = line_str.lower()
        if any(k in line_lower for k in ["birth", "dob", "d.o.b", "yob", "ولد", "تاريخ الميلاد", "الميلاد", "ميلاد"]):
            return "birth_date"
        elif any(k in line_lower for k in ["exp", "expiry", "expires", "انتهاء", "تاريخ الانتهاء", "صالح"]):
            return "expiry_date"
        return "unknown"

    for line in lines:
        # Match YYYY-MM-DD, YYYY/MM/DD, YYYY MM DD
        for m in re.finditer(r'\b(\d{4})[\s\-/](\d{1,2})[\s\-/](\d{1,2})\b', line):
            y, m_val, d = map(int, m.groups())
            dt = parse_to_date_obj(y, m_val, d)
            if dt:
                candidates.append(CandidateDate(
                    value=dt,
                    source_line=line,
                    date_type=determine_date_type(line),
                    normalized_value=dt.isoformat()
                ))

        # Match DD-MM-YYYY, DD/MM/YYYY, DD MM YYYY
        for m in re.finditer(r'\b(\d{1,2})[\s\-/](\d{1,2})[\s\-/](\d{4})\b', line):
            d, m_val, y = map(int, m.groups())
            dt = parse_to_date_obj(y, m_val, d)
            if dt:
                candidates.append(CandidateDate(
                    value=dt,
                    source_line=line,
                    date_type=determine_date_type(line),
                    normalized_value=dt.isoformat()
                ))

    # Deduplicate candidates based on (value, source_line, date_type)
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c.value, c.source_line, c.date_type)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    return unique_candidates

import re
import logging
from rapidfuzz import process, fuzz
from services.authority_extraction_patterns import (
    ENGLISH_AUTHORITY_KEYWORDS,
    ARABIC_AUTHORITY_KEYWORDS,
    ENGLISH_CAPACITY_PHRASES,
    ARABIC_CAPACITY_PHRASES,
    ENGLISH_PREFIXES,
    ARABIC_PREFIXES,
    ENGLISH_TITLES,
    ARABIC_TITLES,
)

logger = logging.getLogger(__name__)

REATTACH_PREFIXES_EN = {
    "dr": "Dr.",
    "eng": "Eng.",
    "prof": "Prof."
}

REATTACH_PREFIXES_AR = {
    "الدكتور": "الدكتور/",
    "المهندس": "المهندس/",
    "البروفيسور": "البروفيسور/"
}

def safe_print(val):
    if isinstance(val, str):
        print(val.encode('ascii', errors='backslashreplace').decode('ascii'))
    else:
        print(val)

def normalize_text(text: str) -> str:
    """
    Standardizes whitespace, newlines, zero-width spaces, and punctuation.
    Also normalizes character variants to make extraction provider-agnostic:
    - NFC normalization
    - Normalize Yeh: ی (U+06CC) to ي (U+064A)
    - Normalize Alef Maksura: ى (U+0649) to ي (U+064A)
    - Normalize Persian Keheh: ک (U+06A9) to ك (U+0643)
    - Remove Tatweel: ـ (U+0640)
    - Remove Zero Width Characters
    """
    import unicodedata
    if not text:
        return ""
        
    # 1. NFC Normalize
    text = unicodedata.normalize("NFC", text)
    
    # 2. Strip zero-width characters (U+200B, U+200C, U+200D, U+FEFF)
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    
    # 3. Normalize Arabic character variants
    text = text.replace('\u06cc', '\u064a')  # ی -> ي
    text = text.replace('\u0649', '\u064a')  # ى -> ي
    text = text.replace('\u06a9', '\u0643')  # ک -> ك
    text = text.replace('\u0640', '')        # ـ -> removed
    
    # Convert newlines and tabs to spaces
    text = re.sub(r'[\r\n\t]', ' ', text)
    # Normalize Arabic punctuation: comma
    text = text.replace('،', ' ')
    # Collapse multiple spaces to single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_best_title_match(candidate_text: str, title_list: list) -> tuple:
    """
    Given candidate text and a list of titles, uses RapidFuzz to find the best match.
    Returns: (matched_title, score, match_method, penalty)
    """
    if not candidate_text or not candidate_text.strip():
        return None, 0.0, "none", 0.0

    best_match = process.extractOne(
        candidate_text,
        title_list,
        scorer=fuzz.partial_ratio
    )
    if not best_match:
        return None, 0.0, "none", 0.0

    matched_title, score, _ = best_match

    # Apply thresholds
    if score >= 95:
        return matched_title, score, "exact", 0.0
    elif score >= 90:
        return matched_title, score, "fuzzy", -0.02
    elif score >= 85:
        return matched_title, score, "fuzzy", -0.05
    else:
        return None, score, "none", 0.0

def validate_representative_name(name: str, lang: str) -> bool:
    """
    Sanity checks for extracted representative names.
    Rejects names too short (< 2 words) or containing prefix/title/capacity tokens.
    """
    if not name:
        return False
    words = [w.strip() for w in name.split() if w.strip()]
    if len(words) < 2:
        return False
        
    name_lower = name.lower()
    
    if lang == "en":
        # Prefix terms
        reject_terms = ["mr", "mrs", "ms", "dr", "prof", "eng"]
        for term in reject_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', name_lower):
                return False
        # Capacity phrases
        for phrase in ENGLISH_CAPACITY_PHRASES:
            if phrase.lower() in name_lower:
                return False
        # Title words and full titles
        reject_title_words = ["manager", "officer", "director", "executive", "president", "chief", "cfo", "ceo"]
        for word in reject_title_words:
            if re.search(r'\b' + re.escape(word) + r'\b', name_lower):
                return False
        for title in ENGLISH_TITLES:
            if title.lower() in name_lower:
                return False
    else:
        # Arabic rejects
        reject_terms = ["السيد", "السيدة", "الأستاذ", "الدكتور", "م.", "بصفته", "بصفتها", "المدير", "الرئيس", "المفوض", "مدير", "رئيس"]
        for term in reject_terms:
            if term in name:
                return False
        for title in ARABIC_TITLES:
            if title in name:
                return False
                
    return True

def canonicalize_name(name: str, lang: str | None = None) -> str:
    """
    Algorithmic cleaning of names:
    - Collapses repeated spaces
    - Normalizes hyphen spacing
    - Normalizes commas and slashes to spaces
    - Strips leading and trailing punctuation and spaces
    - Arabic specific: collapses compound names starting with 'عبد ' and removes tatweel.
    """
    if not name:
        return ""
    
    # 1. Strip zero-width/hidden characters
    name = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', name)
    
    # 2. Collapse spacing around hyphens
    name = re.sub(r'-\s+', '-', name)
    name = re.sub(r'\s+-', '-', name)
    
    # 3. Normalize slashes, commas, and repeated punctuation
    name = re.sub(r'[\\/:\;,.\(\)،]', ' ', name)
    
    # 4. Collapse repeated spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # 5. Language-specific handling
    is_ar = False
    if lang == "ar":
        is_ar = True
    elif lang is None:
        # Auto-detect Arabic if any Arabic character is present
        if re.search(r'[\u0600-\u06FF]', name):
            is_ar = True
            
    if is_ar:
        # Remove tatweel
        name = name.replace("ـ", "")
        # Collapse compound names starting with 'عبد' (e.g., عبد الرحمن -> عبدالرحمن)
        name = re.sub(r'\bعبد\s+(\w+)', r'عبد\1', name)
        # Collapse multiple spaces again
        name = re.sub(r'\s+', ' ', name).strip()
        
    # 5b. Strip trailing stop words/common contract words
    words = name.split()
    if words:
        stop_words_en = {"who", "is", "signing", "this", "contract", "hereinafter", "referred", "acting", "represented", "to", "the", "of", "and", "first", "second", "party", "on", "behalf", "for", "in", "its"}
        stop_words_ar = {"الذي", "التي", "التوقيع", "يوقع", "هذا", "العقد", "الطرف", "الأول", "الثاني", "نيابة", "عن", "في", "من", "على"}
        stop_words = stop_words_ar if is_ar else stop_words_en
        
        while words and words[-1].lower() in stop_words:
            words.pop()
        name = " ".join(words)

    # 6. Remove leading and trailing punctuation/noise
    # Keep stripping characters that shouldn't be at the edges
    name = re.sub(r'^[\\/:\;,.\(\)،\-\s]+', '', name)
    name = re.sub(r'[\\/:\;,.\(\)،\-\s]+$', '', name)
    
    return name.strip()

def collapse_duplicate_prefixes(name: str, lang: str = None) -> str:
    """
    Collapses duplicate professional prefixes.
    Restricted to the beginning of the string or immediately following an authority keyword.
    """
    if not name:
        return ""
    
    name = name.strip()
    
    # Process English prefixes if lang is None or "en"
    if lang == "en" or lang is None:
        prefixes_en = ["Dr", "Eng", "Prof", "Mr", "Mrs", "Ms"]
        # Match authority keywords or start of string (capturing group 1)
        lead_pattern_en = r'((?:^|\b(?:' + '|'.join(re.escape(kw) for kw in ENGLISH_AUTHORITY_KEYWORDS) + r')\b))'
        
        for p in prefixes_en:
            pref_pattern_en = r'\b(?:' + re.escape(p) + r'\.?(?:\s+' + re.escape(p) + r'\.?)+)\b\.?'
            full_pattern_en = lead_pattern_en + r'\s*' + pref_pattern_en
            canonical = REATTACH_PREFIXES_EN.get(p.lower(), p + ".")
            
            def replace_match(m):
                lead = m.group(1)
                return (lead + " " if lead else "") + canonical
                
            name = re.sub(full_pattern_en, replace_match, name, flags=re.IGNORECASE)
            
    # Process Arabic prefixes if lang is None or "ar"
    if lang == "ar" or lang is None:
        prefixes_ar = ["الدكتور", "المهندس", "البروفيسور", "الأستاذ", "السيد", "السيدة"]
        lead_pattern_ar = r'((?:^|' + '|'.join(re.escape(kw) for kw in ARABIC_AUTHORITY_KEYWORDS) + r'))'
        
        for p in prefixes_ar:
            pref_pattern_ar = r'(?:' + re.escape(p) + r'/?(?:\s+' + re.escape(p) + r'/?)+)/?'
            full_pattern_ar = lead_pattern_ar + r'\s*' + pref_pattern_ar
            canonical = REATTACH_PREFIXES_AR.get(p, p + "/")
            
            def replace_match(m):
                lead = m.group(1)
                return (lead + " " if lead else "") + canonical
                
            name = re.sub(full_pattern_ar, replace_match, name)
            
        # Clean up spacing around slashes for Arabic
        name = name.replace("/ ", "/").replace("/", "/ ")
        name = re.sub(r'\s+', ' ', name).strip()
        
    return name

def restore_prefix(prefix: str, name: str, lang: str = None) -> str:
    """
    Safely restores a prefix to a representative name, ensuring no duplication occurs.
    """
    if not prefix or not name:
        return name or ""
        
    prefix = prefix.strip()
    name = name.strip()
    
    # 1. First collapse any duplicates already in the name
    name = collapse_duplicate_prefixes(name, lang)
    
    if lang == "en":
        clean_pref_key = prefix.rstrip('.').lower()
        if clean_pref_key not in REATTACH_PREFIXES_EN:
            return name
        canonical_pref = REATTACH_PREFIXES_EN[clean_pref_key]
        
        # Check if name already starts with any form of the prefix
        words = name.split()
        if words:
            first_word_clean = words[0].rstrip('.').lower()
            if first_word_clean == clean_pref_key:
                return name
                
        if name.lower().startswith(canonical_pref.lower()):
            return name
            
        return f"{canonical_pref} {name}"
    else:
        clean_pref_key = prefix.rstrip('./ ').strip()
        if clean_pref_key not in REATTACH_PREFIXES_AR:
            return name
        canonical_pref = REATTACH_PREFIXES_AR[clean_pref_key]
        
        # Check if name already starts with the prefix (ignoring punctuation/slashes)
        words = name.split()
        if words:
            first_word_clean = words[0].rstrip('./ ').strip()
            if first_word_clean == clean_pref_key:
                # Re-canonicalize to make sure punctuation is correct
                remaining = " ".join(words[1:])
                formatted = f"{canonical_pref} {remaining}"
                return formatted.replace("/ ", "/").replace("/", "/ ").strip()
                
        # Also check startswith on clean start
        name_clean_start = name.lstrip('./ ')
        if name_clean_start.startswith(clean_pref_key):
            remaining = name_clean_start[len(clean_pref_key):].strip()
            formatted = f"{canonical_pref} {remaining}"
            return formatted.replace("/ ", "/").replace("/", "/ ").strip()
            
        formatted = f"{canonical_pref} {name}"
        return formatted.replace("/ ", "/").replace("/", "/ ").strip()

def clean_extracted_name(name_str: str, lang: str) -> str:
    """
    Cleans name by removing slashes, punctuation, parentheses, prefixes, and titles.
    """
    if not name_str:
        return ""
        
    # Canonicalize first to resolve punctuation collision with prefix stripping
    name_str = canonicalize_name(name_str, lang)
        
    # Strip known titles from the front of the name
    if lang == "en":
        for t in sorted(ENGLISH_TITLES, key=len, reverse=True):
            if name_str.lower().startswith(t.lower()):
                name_str = name_str[len(t):].strip()
                break
    else:
        for t in sorted(ARABIC_TITLES, key=len, reverse=True):
            if name_str.startswith(t):
                name_str = name_str[len(t):].strip()
                break
                
    # Strip prefix words from the start if present (backup check)
    if lang == "en":
        for p in ENGLISH_PREFIXES:
            clean_p = p.rstrip('.').lower()
            words = name_str.split()
            if words and words[0].rstrip('.').lower() == clean_p:
                name_str = " ".join(words[1:])
    else:
        for p in ARABIC_PREFIXES:
            clean_p = p.rstrip('. ')
            words = name_str.split()
            if words and words[0].rstrip('. ') == clean_p:
                name_str = " ".join(words[1:])
                
    # Final algorithmic cleaning via canonicalize_name
    cleaned = canonicalize_name(name_str, lang)
    return collapse_duplicate_prefixes(cleaned, lang)

def extract_english_authority(raw_text: str) -> dict:
    """
    Extracts English representative details using candidate-window scoring.
    """
    norm_text = normalize_text(raw_text)
    candidates = []
    
    for kw in ENGLISH_AUTHORITY_KEYWORDS:
        start = 0
        while True:
            idx = norm_text.lower().find(kw.lower(), start)
            if idx == -1:
                break
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"Authority phrase matched: {kw}")
            candidates.append((idx, kw))
            start = idx + 1
            
    if not candidates:
        return {
            "representative_name": "",
            "title": "",
            "capacity_phrase": "",
            "full_clause": "",
            "confidence_score": 0.0,
            "score": -1,
            "idx": 999999
        }
        
    evaluated_candidates = []
    for idx, kw in candidates:
        window = norm_text[idx : idx + 500]
        
        # Search for prefix
        prefix_pattern = r'\b(' + '|'.join(re.escape(p) for p in ENGLISH_PREFIXES) + r')(?:\s|$|\.|\b)'
        prefix_match = re.search(prefix_pattern, window, re.IGNORECASE)
        prefix_idx = -1
        matched_prefix = ""
        if prefix_match:
            prefix_idx = prefix_match.start(1)
            matched_prefix = prefix_match.group(1)
            
        # Search for capacity phrase
        capacity_pattern = r'\b(' + '|'.join(re.escape(c) for c in ENGLISH_CAPACITY_PHRASES) + r')\b'
        capacity_match = re.search(capacity_pattern, window, re.IGNORECASE)
        capacity_idx = -1
        matched_capacity = ""
        if capacity_match:
            capacity_idx = capacity_match.start()
            matched_capacity = capacity_match.group(1)
            
        # Search for title using RapidFuzz
        title_en = ""
        title_match_score = 0.0
        title_match_method = "none"
        title_penalty = 0.0
        candidate_title_text = ""
        
        if capacity_match:
            suffix = window[capacity_idx + len(matched_capacity):]
            candidate_title_text = re.sub(r'^[\\/:\;,.\(\)，\s]+', '', suffix).strip()
            matched_title, match_score, match_method, penalty = find_best_title_match(candidate_title_text, ENGLISH_TITLES)
            if matched_title:
                title_en = matched_title
            title_match_score = match_score
            title_match_method = match_method
            title_penalty = penalty
        else:
            matched_title, match_score, match_method, penalty = find_best_title_match(window, ENGLISH_TITLES)
            if matched_title:
                title_en = matched_title
            title_match_score = match_score
            title_match_method = match_method
            title_penalty = penalty

        # Log details
        accepted = bool(title_en)
        logger.info(
            f"Candidate title: '{candidate_title_text}' | Best title: '{title_en}' | "
            f"Similarity: {title_match_score} | Accepted: {accepted} | Method: {title_match_method}"
        )
        safe_print(f"Candidate title: {repr(candidate_title_text)}")
        safe_print(f"Best title: {repr(title_en)}")
        safe_print(f"Similarity: {title_match_score}")
        safe_print(f"Accepted: {accepted}")
        safe_print(f"Method: {title_match_method}")

        # Extract and clean name
        clean_name = ""
        raw_name = ""
        if capacity_match:
            if prefix_match and prefix_idx < capacity_idx:
                raw_name = window[prefix_idx + len(matched_prefix) : capacity_idx]
            else:
                raw_name = window[len(kw) : capacity_idx]
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"[PREFIX DEBUG] Candidate before cleaning: {raw_name}")
            clean_name = clean_extracted_name(raw_name, "en")
        else:
            # Fallback when capacity phrase is not matched
            if prefix_match:
                raw_name = window[prefix_idx + len(matched_prefix) : prefix_idx + len(matched_prefix) + 80]
            else:
                raw_name = window[len(kw) : len(kw) + 80]
            # Limit to 5-7 words before cleaning so stop-words stripping runs on the end of the candidate name
            words = raw_name.split()
            if len(words) > 6:
                raw_name = " ".join(words[:6])
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"[PREFIX DEBUG] Candidate before cleaning: {raw_name}")
            clean_name = clean_extracted_name(raw_name, "en")

        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(f"[PREFIX DEBUG] After clean_extracted_name: {clean_name}")

        # Validate name
        name_valid = validate_representative_name(clean_name, "en")
        
        # Re-attach prefix to clean_name if matched (Partial Extraction Protection)
        if name_valid and matched_prefix and clean_name:
            clean_name = restore_prefix(matched_prefix, clean_name, "en")
            
        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(f"[PREFIX DEBUG] Final restored name: {clean_name}")

        # Calculate name_similarity_score internally
        raw_candidate = raw_name.strip() if raw_name else ""
        canonicalized_candidate = canonicalize_name(clean_name, "en")
        prefix_restored_candidate = clean_name
        
        sim_1 = fuzz.token_set_ratio(raw_candidate, canonicalized_candidate)
        sim_2 = fuzz.token_set_ratio(canonicalized_candidate, prefix_restored_candidate)
        sim_3 = fuzz.token_set_ratio(raw_candidate, prefix_restored_candidate)
        name_similarity_score = float((sim_1 + sim_2 + sim_3) / 3.0 / 100.0) if clean_name else 0.0

        # Scoring
        score = 0
        name_found = clean_name and name_valid
        title_found = bool(title_en)
        capacity_found = bool(matched_capacity)
        
        if name_found:
            score += 1
        if title_found:
            score += 1
        if capacity_found:
            score += 1
            
        # Clause Assembly
        full_clause = ""
        if name_found and title_found and capacity_found:
            full_clause = f"{kw} {matched_prefix} {clean_name}, {matched_capacity} {title_en}"
            full_clause = collapse_duplicate_prefixes(full_clause)
            score += 1
            
        # Confidence computation with penalties
        conf = 0
        if clean_name:
            conf += 25
        if title_found:
            conf += 25
        if capacity_found:
            conf += 25
        if score == 4:
            conf += 25
            
        if clean_name and not name_valid:
            conf -= 25
        if not title_found:
            conf -= 10
        if not capacity_found:
            conf -= 10
            
        conf = max(0, min(100, conf))
        base_confidence = conf / 100.0
        confidence_score = max(0.0, min(1.0, base_confidence + title_penalty))
        
        # Boost confidence score based on name similarity score
        # ONLY boost when we don't have a title match penalty and capacity phrase is found
        if name_found and name_similarity_score >= 0.85:
            if title_match_method == "exact" and capacity_found:
                confidence_score = min(1.0, confidence_score + 0.15)
            
        representative_name = clean_name if name_valid else ""
        if not representative_name:
            confidence_score = 0.0
        
        evaluated_candidates.append({
            "representative_name": representative_name,
            "title": title_en,
            "capacity_phrase": matched_capacity,
            "full_clause": full_clause,
            "confidence_score": confidence_score,
            "title_match_score": title_match_score,
            "title_match_method": title_match_method,
            "name_similarity_score": name_similarity_score,
            "score": score,
            "idx": idx
        })
        
        # Log candidate details
        logger.info(
            f"English candidate: keyword selected='{kw}', window score={score}, assembled clause='{full_clause}', confidence={confidence_score}"
        )
        
    # Sort and pick best candidate (by confidence score first)
    best_candidate = max(evaluated_candidates, key=lambda c: (c["confidence_score"], c["score"], len(c["full_clause"]), -c["idx"]))
    return best_candidate

def extract_arabic_authority(raw_text: str) -> dict:
    """
    Extracts Arabic representative details using candidate-window scoring.
    """
    norm_text = normalize_text(raw_text)
    candidates = []
    
    for kw in ARABIC_AUTHORITY_KEYWORDS:
        start = 0
        while True:
            idx = norm_text.find(kw, start)
            if idx == -1:
                break
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"Authority phrase matched: {kw}")
            candidates.append((idx, kw))
            start = idx + 1
            
    if not candidates:
        return {
            "representative_name": "",
            "title": "",
            "capacity_phrase": "",
            "full_clause": "",
            "confidence_score": 0.0,
            "score": -1,
            "idx": 999999
        }
        
    evaluated_candidates = []
    for idx, kw in candidates:
        window = norm_text[idx : idx + 500]
        
        safe_print("\n===== ARABIC CANDIDATE WINDOW =====")
        safe_print(window)
        safe_print("==================================")
        
        # Search for prefix
        prefix_pattern = r'(?:^|[\s/])(' + '|'.join(re.escape(p) for p in ARABIC_PREFIXES) + r')(?:[\s/:]|$)'
        prefix_match = re.search(prefix_pattern, window)
        prefix_idx = -1
        matched_prefix = ""
        if prefix_match:
            prefix_idx = prefix_match.start(1)
            matched_prefix = prefix_match.group(1)

        # Search for capacity phrase
        capacity_pattern = r'(?:^|[\s/])(' + '|'.join(re.escape(c) for c in ARABIC_CAPACITY_PHRASES) + r')(?:[\s/:]|$)'
        capacity_match = re.search(capacity_pattern, window)
        capacity_idx = -1
        matched_capacity = ""
        if capacity_match:
            capacity_idx = capacity_match.start(1)
            matched_capacity = capacity_match.group(1)
            
        # Search for title using RapidFuzz
        title_ar = ""
        title_match_score = 0.0
        title_match_method = "none"
        title_penalty = 0.0
        candidate_title_text = ""
        
        if capacity_match:
            suffix = window[capacity_idx + len(matched_capacity):]
            candidate_title_text = re.sub(r'^[\\/:\;,.\(\)،\s]+', '', suffix).strip()
            matched_title, match_score, match_method, penalty = find_best_title_match(candidate_title_text, ARABIC_TITLES)
            if matched_title:
                title_ar = matched_title
            title_match_score = match_score
            title_match_method = match_method
            title_penalty = penalty
        else:
            matched_title, match_score, match_method, penalty = find_best_title_match(window, ARABIC_TITLES)
            if matched_title:
                title_ar = matched_title
            title_match_score = match_score
            title_match_method = match_method
            title_penalty = penalty

        # Log details
        accepted = bool(title_ar)
        logger.info(
            f"Candidate title: '{candidate_title_text}' | Best title: '{title_ar}' | "
            f"Similarity: {title_match_score} | Accepted: {accepted} | Method: {title_match_method}"
        )
        safe_print(f"Candidate title: {repr(candidate_title_text)}")
        safe_print(f"Best title: {repr(title_ar)}")
        safe_print(f"Similarity: {title_match_score}")
        safe_print(f"Accepted: {accepted}")
        safe_print(f"Method: {title_match_method}")

        # Extract and clean name
        clean_name = ""
        raw_name = ""
        if capacity_match:
            if prefix_match and prefix_idx < capacity_idx:
                raw_name = window[prefix_idx + len(matched_prefix) : capacity_idx]
            else:
                raw_name = window[len(kw) : capacity_idx]
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"[PREFIX DEBUG] Candidate before cleaning: {raw_name}")
            clean_name = clean_extracted_name(raw_name, "ar")
        else:
            # Fallback when capacity phrase is not matched
            if prefix_match:
                raw_name = window[prefix_idx + len(matched_prefix) : prefix_idx + len(matched_prefix) + 80]
            else:
                raw_name = window[len(kw) : len(kw) + 80]
            # Limit to 5-7 words before cleaning so stop-words stripping runs on the end of the candidate name
            words = raw_name.split()
            if len(words) > 6:
                raw_name = " ".join(words[:6])
            # BENCHMARK DEBUG ONLY
            # SAFE TO REMOVE AFTER OCR TUNING
            logger.info(f"[PREFIX DEBUG] Candidate before cleaning: {raw_name}")
            clean_name = clean_extracted_name(raw_name, "ar")

        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(f"[PREFIX DEBUG] After clean_extracted_name: {clean_name}")

        # Validate name
        name_valid = validate_representative_name(clean_name, "ar")
        
        # Re-attach prefix to clean_name if matched (Partial Extraction Protection)
        if name_valid and matched_prefix and clean_name:
            clean_name = restore_prefix(matched_prefix, clean_name, "ar")
            
        # BENCHMARK DEBUG ONLY
        # SAFE TO REMOVE AFTER OCR TUNING
        logger.info(f"[PREFIX DEBUG] Final restored name: {clean_name}")

        # Calculate name_similarity_score internally
        raw_candidate = raw_name.strip() if raw_name else ""
        canonicalized_candidate = canonicalize_name(clean_name, "ar")
        prefix_restored_candidate = clean_name
        
        sim_1 = fuzz.token_set_ratio(raw_candidate, canonicalized_candidate)
        sim_2 = fuzz.token_set_ratio(canonicalized_candidate, prefix_restored_candidate)
        sim_3 = fuzz.token_set_ratio(raw_candidate, prefix_restored_candidate)
        name_similarity_score = float((sim_1 + sim_2 + sim_3) / 3.0 / 100.0) if clean_name else 0.0

        # Scoring
        score = 0
        name_found = clean_name and name_valid
        title_found = bool(title_ar)
        capacity_found = bool(matched_capacity)
        
        if name_found:
            score += 1
        if title_found:
            score += 1
        if capacity_found:
            score += 1
            
        # Clause Assembly
        full_clause = ""
        if name_found and title_found and capacity_found:
            full_clause = f"{kw} {matched_prefix}/ {clean_name} {matched_capacity}/ {title_ar}"
            full_clause = collapse_duplicate_prefixes(full_clause)
            score += 1
            
        # Confidence computation with penalties
        conf = 0
        if clean_name:
            conf += 25
        if title_found:
            conf += 25
        if capacity_found:
            conf += 25
        if score == 4:
            conf += 25
            
        if clean_name and not name_valid:
            conf -= 25
        if not title_found:
            conf -= 10
        if not capacity_found:
            conf -= 10
            
        conf = max(0, min(100, conf))
        base_confidence = conf / 100.0
        confidence_score = max(0.0, min(1.0, base_confidence + title_penalty))
        
        # Boost confidence score based on name similarity score
        # ONLY boost when we don't have a title match penalty and capacity phrase is found
        if name_found and name_similarity_score >= 0.85:
            if title_match_method == "exact" and capacity_found:
                confidence_score = min(1.0, confidence_score + 0.15)
            
        representative_name = clean_name if name_valid else ""
        if not representative_name:
            confidence_score = 0.0
        
        evaluated_candidates.append({
            "representative_name": representative_name,
            "title": title_ar,
            "capacity_phrase": matched_capacity,
            "full_clause": full_clause,
            "confidence_score": confidence_score,
            "title_match_score": title_match_score,
            "title_match_method": title_match_method,
            "name_similarity_score": name_similarity_score,
            "score": score,
            "idx": idx
        })
        
        # Log candidate details
        logger.info(
            f"Arabic candidate: keyword selected='{kw}', window score={score}, assembled clause='{full_clause}', confidence={confidence_score}"
        )
        
    # Sort and pick best candidate (by confidence score first)
    best_candidate = max(evaluated_candidates, key=lambda c: (c["confidence_score"], c["score"], len(c["full_clause"]), -c["idx"]))
    
    safe_print("\n----- ARABIC EXTRACTION RESULT -----")
    safe_print("Name:")
    safe_print(repr(best_candidate["representative_name"]))
    safe_print("Title:")
    safe_print(repr(best_candidate["title"]))
    safe_print("Capacity:")
    safe_print(repr(best_candidate["capacity_phrase"]))
    safe_print("Clause:")
    safe_print(repr(best_candidate["full_clause"]))
    safe_print("Score:")
    safe_print(best_candidate["score"])
    safe_print("-----------------------------------")
    
    return best_candidate

def analyze_contract_authority(raw_text: str, english_text: str = None, arabic_text: str = None) -> dict:
    """
    Extracts representative names, titles, and authority clauses in both English and Arabic.
    Uses separated english_text and arabic_text if provided to prevent contamination.
    """
    en_input = english_text if english_text is not None else raw_text
    ar_input = arabic_text if arabic_text is not None else raw_text

    en_result = extract_english_authority(en_input)
    ar_result = extract_arabic_authority(ar_input)
    
    # Calculate overall confidence as the average of English and Arabic confidences
    authority_confidence = (en_result["confidence_score"] + ar_result["confidence_score"]) / 2.0
    
    # Calculate name_similarity_score based on extracted names
    scores = []
    if en_result["representative_name"]:
        scores.append(en_result.get("name_similarity_score", 0.0))
    if ar_result["representative_name"]:
        scores.append(ar_result.get("name_similarity_score", 0.0))
    name_similarity_score = sum(scores) / len(scores) if scores else 0.0

    safe_print("\n----- CONFIDENCE DEBUG -----")
    safe_print("English confidence: " + str(en_result["confidence_score"]))
    safe_print("Arabic confidence: " + str(ar_result["confidence_score"]))
    safe_print("Overall confidence: " + str(authority_confidence))
    safe_print("Name similarity score: " + str(name_similarity_score))
    safe_print("----------------------------")
    
    return {
        "representative_name_en": en_result["representative_name"],
        "representative_name_ar": ar_result["representative_name"],
        "title_en": en_result["title"],
        "title_ar": ar_result["title"],
        "authority_clause_en": en_result["full_clause"],
        "authority_clause_ar": ar_result["full_clause"],
        "confidence_score": authority_confidence,
        "title_match_score_en": en_result.get("title_match_score", 0.0),
        "title_match_score_ar": ar_result.get("title_match_score", 0.0),
        "title_match_method_en": en_result.get("title_match_method", "none"),
        "title_match_method_ar": ar_result.get("title_match_method", "none"),
        "name_similarity_score": name_similarity_score
    }

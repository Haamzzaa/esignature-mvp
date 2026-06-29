import re
import math
import time
import hashlib
import logging
import sys
from django.conf import settings
from django.core.cache import cache
from esign.request_context import get_request_id
from esign.config import esign_config

logger = logging.getLogger(__name__)

def parse_rate_limit(limit_str):
    """
    Parses rate limit string (e.g. '5/m', '10/30s', '100/h') into (count, period_seconds).
    """
    match = re.match(r'^(\d+)/(\d*)([smhd])$', limit_str.strip().lower())
    if not match:
        raise ValueError(f"Invalid rate limit format: {limit_str}")
    
    count = int(match.group(1))
    multiplier = int(match.group(2)) if match.group(2) else 1
    unit = match.group(3)
    
    seconds_map = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    period = multiplier * seconds_map[unit]
    return count, period

def get_client_ip(request):
    """
    Extracts client IP from HTTP headers, respecting proxies.
    """
    if not request:
        return "unknown-ip"
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or "unknown-ip"

def check_rate_limit(key_prefix, identifier, limit_str, endpoint_name=""):
    """
    Checks sliding window rate limit in cache.
    Fails open if the cache store is unavailable.
    """
    if getattr(settings, "ESIGN_DISABLE_RATE_LIMITS", False) or 'test' in sys.argv or getattr(settings, 'TESTING', False):
        return False, 999, None
        
    request_id = get_request_id() or "unknown-request-id"
    
    try:
        max_requests, period = parse_rate_limit(limit_str)
    except ValueError as exc:
        logger.error(f"[RateLimit] Configuration error parse_rate_limit failed for '{limit_str}': {exc}")
        return False, 1, None

    # Hashing key to ensure privacy (e.g. hash IPs, emails, tokens)
    ident_hash = hashlib.sha256(str(identifier).encode('utf-8')).hexdigest()
    cache_key = f"rate_limit:{key_prefix}:{ident_hash}"

    now = time.time()
    cutoff = now - period

    try:
        # Sliding window logic
        timestamps = cache.get(cache_key) or []
    except Exception as exc:
        logger.critical(
            "[RateLimit] Cache backend is unavailable! Failing open for request. endpoint=%s prefix=%s req_id=%s error=%s",
            endpoint_name, key_prefix, request_id, str(exc), exc_info=True
        )
        return False, 999, None

    timestamps = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= max_requests:
        # Exceeded limit
        first_t = timestamps[0]
        retry_after = int(math.ceil((first_t + period) - now))
        retry_after = max(1, retry_after)
        
        logger.warning(
            "[RateLimit] Limit Hit: endpoint=%s prefix=%s identifier_hash=%s limit=%s retry_after=%ds req_id=%s",
            endpoint_name, key_prefix, ident_hash, limit_str, retry_after, request_id
        )
        return True, 0, retry_after

    # Accept request
    timestamps.append(now)
    try:
        cache.set(cache_key, timestamps, timeout=period)
    except Exception as exc:
        logger.critical(
            "[RateLimit] Cache backend is unavailable during write! Failing open. endpoint=%s prefix=%s req_id=%s error=%s",
            endpoint_name, key_prefix, request_id, str(exc), exc_info=True
        )
        return False, 999, None

    remaining = max_requests - len(timestamps)

    logger.info(
        "[RateLimit] Limit Passed: endpoint=%s prefix=%s identifier_hash=%s limit=%s remaining=%d req_id=%s",
        endpoint_name, key_prefix, ident_hash, limit_str, remaining, request_id
    )
    return False, remaining, None

def check_otp_lockout(participant_id):
    """
    Checks if a participant is locked out of OTP verification.
    Returns (is_locked, remaining_seconds).
    Fails open if cache backend is unavailable.
    """
    if getattr(settings, "ESIGN_DISABLE_RATE_LIMITS", False) or 'test' in sys.argv or getattr(settings, 'TESTING', False):
        return False, None
        
    lock_key = f"otp_lockout:{participant_id}"
    try:
        lock_expire_time = cache.get(lock_key)
    except Exception as exc:
        logger.critical(
            "[OTPBruteForce] Cache backend is unavailable during lockout check! Failing open. participant_id=%s error=%s",
            participant_id, str(exc), exc_info=True
        )
        return False, None
    
    if lock_expire_time:
        now = time.time()
        remaining = int(math.ceil(lock_expire_time - now))
        if remaining > 0:
            return True, remaining
        # If expired but cache key is somehow still returning, clear it
        try:
            cache.delete(lock_key)
        except Exception:
            pass
    return False, None

def register_otp_failed_attempt(participant_id):
    """
    Registers a failed OTP attempt. Triggers lockout if threshold is reached.
    Fails open if cache backend is unavailable.
    """
    if getattr(settings, "ESIGN_DISABLE_RATE_LIMITS", False) or 'test' in sys.argv or getattr(settings, 'TESTING', False):
        return False
        
    request_id = get_request_id() or "unknown-request-id"
    attempts_key = f"otp_failed_attempts:{participant_id}"
    
    try:
        attempts = cache.get(attempts_key) or 0
        attempts += 1
        
        threshold = esign_config.rate_limit_otp_verify_attempts
        lock_duration = esign_config.rate_limit_otp_verify_lockout

        if attempts >= threshold:
            now = time.time()
            lock_expire_time = now + lock_duration
            
            # Set lockout key
            lock_key = f"otp_lockout:{participant_id}"
            cache.set(lock_key, lock_expire_time, timeout=lock_duration)
            
            # Reset attempts
            cache.delete(attempts_key)
            
            logger.warning(
                "[OTPBruteForce] Account Locked: participant_id=%s failed_attempts=%d lockout_duration=%ds req_id=%s",
                participant_id, attempts, lock_duration, request_id
            )
            return True
        
        cache.set(attempts_key, attempts, timeout=86400) # Keep attempts window for 1 day
    except Exception as exc:
        logger.critical(
            "[OTPBruteForce] Cache backend is unavailable during failed attempt registration! Failing open. participant_id=%s error=%s",
            participant_id, str(exc), exc_info=True
        )
        return False

    logger.info(
        "[OTPBruteForce] Failed Attempt: participant_id=%s failed_attempts=%d threshold=%d req_id=%s",
        participant_id, attempts, threshold, request_id
    )
    return False

def reset_otp_failed_attempts(participant_id):
    """
    Resets OTP lockout counters and blocks upon successful OTP verification.
    """
    try:
        cache.delete(f"otp_failed_attempts:{participant_id}")
        cache.delete(f"otp_lockout:{participant_id}")
    except Exception as exc:
        logger.critical(
            "[OTPBruteForce] Cache backend is unavailable during reset! participant_id=%s error=%s",
            participant_id, str(exc), exc_info=True
        )
    logger.info("[OTPBruteForce] Lockout reset for participant_id=%s", participant_id)

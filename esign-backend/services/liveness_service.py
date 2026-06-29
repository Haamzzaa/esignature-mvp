from dataclasses import dataclass

@dataclass
class LivenessResult:
    passed: bool
    score: float | None
    provider: str
    reason: str

def perform_liveness_check(selfie_image_bytes) -> LivenessResult:
    """
    Placeholder implementation for liveness checks.
    Always returns passed=True, score=1.0, provider='local-placeholder'.
    """
    return LivenessResult(
        passed=True,
        score=1.0,
        provider="local-placeholder",
        reason=""
    )

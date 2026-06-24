from dataclasses import dataclass

@dataclass
class FieldConfidence:
    confidence: float
    reasons: list[str]

@dataclass
class IdentityConfidenceResult:
    name_confidence: FieldConfidence
    identifier_confidence: FieldConfidence
    birth_date_confidence: FieldConfidence
    expiry_date_confidence: FieldConfidence | None
    overall_confidence: float

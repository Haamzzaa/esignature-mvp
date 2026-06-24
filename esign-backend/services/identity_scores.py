from dataclasses import dataclass

@dataclass
class ScoredCandidateName:
    value: str
    score: float
    reasons: list[str]
    source_line: str

@dataclass
class ScoredCandidateIdentifier:
    value: str
    score: float
    reasons: list[str]
    source_line: str
    normalized_value: str = ""

@dataclass
class ScoredCandidateDate:
    value: str
    score: float
    reasons: list[str]
    source_line: str
    date_type: str = "unknown"

from dataclasses import dataclass
from datetime import date

@dataclass
class CandidateName:
    value: str
    source_line: str
    reasons: list[str]
    normalized_value: str = ""

@dataclass
class CandidateIdentifier:
    value: str
    source_line: str
    identifier_type: str
    normalized_value: str = ""

@dataclass
class CandidateDate:
    value: date
    source_line: str
    date_type: str
    normalized_value: str = ""

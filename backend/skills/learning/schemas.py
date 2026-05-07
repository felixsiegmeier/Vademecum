from pydantic import BaseModel


class RuleCandidate(BaseModel):
    section: str
    rule_text: str
    reasoning: str = ""
    anchor: str = ""


class TrivialChange(BaseModel):
    section: str = ""
    rule_text: str = ""
    reasoning: str = ""
    anchor: str = ""


class ExtractionResult(BaseModel):
    candidates: list[RuleCandidate]
    trivial_changes: list[TrivialChange] = []


class ConflictResult(BaseModel):
    has_conflict: bool
    explanation: str
    conflicting_rule_id: str = ""


class RebuildResult(BaseModel):
    rule_text: str
    reasoning: str

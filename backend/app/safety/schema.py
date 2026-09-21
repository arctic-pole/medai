from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "moderate", "informational"]
RuleAction = Literal["ESCALATE", "MODIFY"]
SafetyDecision = Literal["PASS", "MODIFY", "BLOCK", "ESCALATE"]
MedicationDecision = Literal["ALLOWED", "BLOCKED", "REQUIRES_REVIEW"]


class SafetyRuleMeta(BaseModel):
    """safety_engine.emergency_triage.rule_schema, verbatim field set. Every instance must cite
    a real, checked source — see app/safety/vital_rules.py for how each one was verified."""

    rule_id: str
    condition: str
    severity: Severity
    action: RuleAction
    source: str
    version: str


class TriggeredRule(BaseModel):
    rule: SafetyRuleMeta
    detail: str


class MedicationCheckResult(BaseModel):
    candidate_name: str
    decision: MedicationDecision
    reasons: list[str] = Field(default_factory=list)
    source_version: str | None = None


class SafetyEvaluation(BaseModel):
    decision: SafetyDecision
    triggered_rules: list[TriggeredRule] = Field(default_factory=list)
    medication_findings: list[MedicationCheckResult] = Field(default_factory=list)

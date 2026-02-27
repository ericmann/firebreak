"""Data models for Firebreak policy enforcement.

Pure data structures — no business logic, no imports beyond stdlib.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class Decision(Enum):
    """Policy decision for a classified prompt."""

    ALLOW = "ALLOW"
    ALLOW_CONSTRAINED = "ALLOW_CONSTRAINED"
    BLOCK = "BLOCK"


class AuditLevel(Enum):
    """Audit logging level for a policy evaluation."""

    STANDARD = "standard"
    ENHANCED = "enhanced"
    CRITICAL = "critical"


@dataclass
class PolicyRule:
    """A single rule within a deployment policy.

    Attributes:
        id: Unique rule identifier (e.g. "allow-analysis").
        description: Human-readable description of the rule.
        match_categories: Intent categories this rule applies to.
        decision: The enforcement decision when this rule matches.
        audit: Audit logging level for matched requests.
        requires_human: Whether a human-in-the-loop flag is set.
        constraints: Operational constraints applied to allowed requests.
        alerts: Notification targets when this rule fires.
        color: Display color for the dashboard (green/yellow/red).
        note: Optional note displayed alongside the decision.
    """

    id: str
    description: str
    match_categories: list[str]
    decision: Decision
    audit: AuditLevel
    requires_human: bool = False
    constraints: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    color: str = "green"
    note: str = ""


@dataclass
class Policy:
    """A complete deployment policy loaded from YAML.

    Attributes:
        name: Policy name (e.g. "defense-standard").
        version: Policy version string.
        effective: Effective date string.
        signatories: Signing parties (e.g. {"ai_provider": "Anthropic"}).
        rules: Ordered list of policy rules.
        categories: Valid intent categories defined by this policy.
    """

    name: str
    version: str
    effective: str
    signatories: dict[str, str]
    rules: list[PolicyRule]
    categories: list[str]


@dataclass
class ClassificationResult:
    """Result of classifying a prompt's intent.

    Attributes:
        intent_category: The classified intent category.
        confidence: Classifier confidence score (0.0-1.0).
        raw_prompt: The original prompt text.
        timestamp: When the classification was performed.
    """

    intent_category: str
    confidence: float
    raw_prompt: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EvaluationResult:
    """Result of evaluating a classified prompt against policy.

    Attributes:
        decision: The enforcement decision.
        matched_rule_id: ID of the rule that matched.
        rule_description: Human-readable description of the matched rule.
        audit_level: Audit logging level for this evaluation.
        alerts: Notification targets triggered by this evaluation.
        constraints: Operational constraints applied to the request.
        color: Display color for the dashboard.
        note: Optional note displayed alongside the decision.
        classification: The classification that triggered this evaluation.
        llm_response: The LLM response text, if the request was forwarded.
    """

    decision: Decision
    matched_rule_id: str
    rule_description: str
    audit_level: AuditLevel
    alerts: list[str]
    constraints: list[str]
    color: str
    note: str
    classification: ClassificationResult
    llm_response: str | None = None


@dataclass
class AuditEntry:
    """An immutable record in the audit log.

    Attributes:
        id: Unique entry identifier (UUID4).
        timestamp: When the entry was created.
        prompt_text: The original prompt text.
        classification: The intent classification result.
        evaluation: The policy evaluation result.
    """

    prompt_text: str
    classification: ClassificationResult
    evaluation: EvaluationResult
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DemoScenario:
    """A scenario used in the demo runner.

    Attributes:
        id: Scenario identifier (e.g. "scenario-1").
        prompt: The prompt text to evaluate.
        expected_category: The expected intent classification.
        narration: Narration text for the demo presenter.
    """

    id: str
    prompt: str
    expected_category: str
    narration: str

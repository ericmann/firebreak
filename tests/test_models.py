"""Tests for Firebreak data models."""

from datetime import datetime

from firebreak.models import (
    AuditEntry,
    AuditLevel,
    ClassificationResult,
    Decision,
    DemoScenario,
    EvaluationResult,
    Policy,
    PolicyRule,
)


class TestDecisionEnum:
    """Tests for the Decision enum."""

    def test_allow_value(self):
        assert Decision.ALLOW.value == "ALLOW"

    def test_allow_constrained_value(self):
        assert Decision.ALLOW_CONSTRAINED.value == "ALLOW_CONSTRAINED"

    def test_block_value(self):
        assert Decision.BLOCK.value == "BLOCK"

    def test_enum_members(self):
        assert set(Decision) == {
            Decision.ALLOW,
            Decision.ALLOW_CONSTRAINED,
            Decision.BLOCK,
        }


class TestAuditLevelEnum:
    """Tests for the AuditLevel enum."""

    def test_standard_value(self):
        assert AuditLevel.STANDARD.value == "standard"

    def test_enhanced_value(self):
        assert AuditLevel.ENHANCED.value == "enhanced"

    def test_critical_value(self):
        assert AuditLevel.CRITICAL.value == "critical"


class TestPolicyRule:
    """Tests for the PolicyRule dataclass."""

    def test_required_fields(self):
        rule = PolicyRule(
            id="test-rule",
            description="A test rule",
            match_categories=["summarization"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        assert rule.id == "test-rule"
        assert rule.description == "A test rule"
        assert rule.match_categories == ["summarization"]
        assert rule.decision == Decision.ALLOW
        assert rule.audit == AuditLevel.STANDARD
        assert rule.color == "green"

    def test_default_requires_human(self):
        rule = PolicyRule(
            id="r1",
            description="d",
            match_categories=["x"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        assert rule.requires_human is False

    def test_default_constraints(self):
        rule = PolicyRule(
            id="r1",
            description="d",
            match_categories=["x"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        assert rule.constraints == []

    def test_default_alerts(self):
        rule = PolicyRule(
            id="r1",
            description="d",
            match_categories=["x"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        assert rule.alerts == []

    def test_default_note(self):
        rule = PolicyRule(
            id="r1",
            description="d",
            match_categories=["x"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        assert rule.note == ""

    def test_explicit_optional_fields(self):
        rule = PolicyRule(
            id="block-rule",
            description="Block rule",
            match_categories=["surveillance"],
            decision=Decision.BLOCK,
            audit=AuditLevel.CRITICAL,
            requires_human=True,
            constraints=["no domestic targets"],
            alerts=["trust_safety", "inspector_general"],
            color="red",
            note="Hard block",
        )
        assert rule.requires_human is True
        assert rule.constraints == ["no domestic targets"]
        assert rule.alerts == ["trust_safety", "inspector_general"]
        assert rule.note == "Hard block"


class TestPolicy:
    """Tests for the Policy dataclass."""

    def test_instantiation(self):
        rule = PolicyRule(
            id="r1",
            description="d",
            match_categories=["x"],
            decision=Decision.ALLOW,
            audit=AuditLevel.STANDARD,
            color="green",
        )
        policy = Policy(
            name="test-policy",
            version="1.0",
            effective="2026-02-28",
            signatories={"ai_provider": "Anthropic", "deploying_org": "DoD"},
            rules=[rule],
            categories=["x"],
        )
        assert policy.name == "test-policy"
        assert policy.version == "1.0"
        assert policy.effective == "2026-02-28"
        assert len(policy.rules) == 1
        assert policy.categories == ["x"]
        assert policy.signatories["ai_provider"] == "Anthropic"


class TestClassificationResult:
    """Tests for the ClassificationResult dataclass."""

    def test_instantiation(self):
        result = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="Summarize this.",
        )
        assert result.intent_category == "summarization"
        assert result.confidence == 0.95
        assert result.raw_prompt == "Summarize this."

    def test_default_timestamp(self):
        before = datetime.now()
        result = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
        )
        after = datetime.now()
        assert before <= result.timestamp <= after

    def test_explicit_timestamp(self):
        ts = datetime(2026, 1, 1, 12, 0, 0)
        result = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
            timestamp=ts,
        )
        assert result.timestamp == ts


class TestEvaluationResult:
    """Tests for the EvaluationResult dataclass."""

    def test_with_embedded_classification(self):
        classification = ClassificationResult(
            intent_category="bulk_surveillance",
            confidence=0.98,
            raw_prompt="Cross-reference phone records",
        )
        evaluation = EvaluationResult(
            decision=Decision.BLOCK,
            matched_rule_id="block-surveillance",
            rule_description="Mass domestic surveillance — hard block",
            audit_level=AuditLevel.CRITICAL,
            alerts=["trust_safety", "inspector_general"],
            constraints=[],
            color="red",
            note="",
            classification=classification,
        )
        assert evaluation.decision == Decision.BLOCK
        assert evaluation.classification.intent_category == "bulk_surveillance"
        assert evaluation.matched_rule_id == "block-surveillance"
        assert evaluation.audit_level == AuditLevel.CRITICAL
        assert "trust_safety" in evaluation.alerts

    def test_default_llm_response(self):
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test",
        )
        evaluation = EvaluationResult(
            decision=Decision.ALLOW,
            matched_rule_id="allow-analysis",
            rule_description="Intelligence summarization",
            audit_level=AuditLevel.STANDARD,
            alerts=[],
            constraints=[],
            color="green",
            note="",
            classification=classification,
        )
        assert evaluation.llm_response is None

    def test_explicit_llm_response(self):
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test",
        )
        evaluation = EvaluationResult(
            decision=Decision.ALLOW,
            matched_rule_id="allow-analysis",
            rule_description="Intelligence summarization",
            audit_level=AuditLevel.STANDARD,
            alerts=[],
            constraints=[],
            color="green",
            note="",
            classification=classification,
            llm_response="Here is the summary...",
        )
        assert evaluation.llm_response == "Here is the summary..."


class TestAuditEntry:
    """Tests for the AuditEntry dataclass."""

    def test_uuid_generation(self):
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test",
        )
        evaluation = EvaluationResult(
            decision=Decision.ALLOW,
            matched_rule_id="allow-analysis",
            rule_description="d",
            audit_level=AuditLevel.STANDARD,
            alerts=[],
            constraints=[],
            color="green",
            note="",
            classification=classification,
        )
        entry = AuditEntry(
            prompt_text="test",
            classification=classification,
            evaluation=evaluation,
        )
        # UUID4 format: 8-4-4-4-12 hex chars
        parts = entry.id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8

    def test_unique_ids(self):
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test",
        )
        evaluation = EvaluationResult(
            decision=Decision.ALLOW,
            matched_rule_id="allow-analysis",
            rule_description="d",
            audit_level=AuditLevel.STANDARD,
            alerts=[],
            constraints=[],
            color="green",
            note="",
            classification=classification,
        )
        entry1 = AuditEntry(
            prompt_text="test",
            classification=classification,
            evaluation=evaluation,
        )
        entry2 = AuditEntry(
            prompt_text="test",
            classification=classification,
            evaluation=evaluation,
        )
        assert entry1.id != entry2.id

    def test_auto_timestamp(self):
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test",
        )
        evaluation = EvaluationResult(
            decision=Decision.ALLOW,
            matched_rule_id="allow-analysis",
            rule_description="d",
            audit_level=AuditLevel.STANDARD,
            alerts=[],
            constraints=[],
            color="green",
            note="",
            classification=classification,
        )
        before = datetime.now()
        entry = AuditEntry(
            prompt_text="test",
            classification=classification,
            evaluation=evaluation,
        )
        after = datetime.now()
        assert before <= entry.timestamp <= after


class TestDemoScenario:
    """Tests for the DemoScenario dataclass."""

    def test_instantiation(self):
        scenario = DemoScenario(
            id="scenario-1",
            prompt="Summarize the briefing.",
            expected_category="summarization",
            narration="Standard intelligence analysis.",
        )
        assert scenario.id == "scenario-1"
        assert scenario.prompt == "Summarize the briefing."
        assert scenario.expected_category == "summarization"
        assert scenario.narration == "Standard intelligence analysis."

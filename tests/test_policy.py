"""Tests for the policy engine."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from firebreak.models import (
    AuditLevel,
    ClassificationResult,
    Decision,
)
from firebreak.policy import PolicyEngine

# Path to the real policy file
POLICY_PATH = str(
    Path(__file__).resolve().parent.parent / "policies" / "defense-standard.yaml"
)


@pytest.fixture
def engine() -> PolicyEngine:
    """Return a PolicyEngine with the defense-standard policy loaded."""
    eng = PolicyEngine()
    eng.load(POLICY_PATH)
    return eng


@pytest.fixture
def make_classification():
    """Factory fixture to create ClassificationResult objects."""

    def _make(category: str) -> ClassificationResult:
        return ClassificationResult(
            intent_category=category,
            confidence=0.95,
            raw_prompt=f"Test prompt for {category}",
            timestamp=datetime(2026, 2, 28, 12, 0, 0),
        )

    return _make


# --------------------------------------------------------------------------- #
# Loading the real policy file
# --------------------------------------------------------------------------- #


class TestLoadPolicy:
    """Tests for loading and parsing YAML policy files."""

    def test_load_returns_policy(self, engine: PolicyEngine) -> None:
        """Loading the real policy file returns a Policy object."""
        assert engine.policy is not None
        assert engine.policy.name == "defense-standard"
        assert engine.policy.version == "2.0"

    def test_policy_metadata(self, engine: PolicyEngine) -> None:
        """Policy metadata fields are parsed correctly."""
        policy = engine.policy
        assert policy is not None
        assert policy.effective == "2026-02-28"
        assert policy.signatories["ai_provider"] == "Anthropic"
        assert policy.signatories["deploying_org"] == "DoD CDAO"

    def test_policy_categories(self, engine: PolicyEngine) -> None:
        """All nine categories are loaded."""
        policy = engine.policy
        assert policy is not None
        expected = [
            "summarization",
            "translation",
            "threat_assessment",
            "missile_defense",
            "cyber_defense",
            "bulk_surveillance",
            "warranted_surveillance",
            "autonomous_targeting",
            "pattern_of_life",
        ]
        assert policy.categories == expected

    def test_policy_rules_count(self, engine: PolicyEngine) -> None:
        """Seven rules are loaded from the YAML file."""
        assert engine.policy is not None
        assert len(engine.policy.rules) == 7

    def test_load_stores_policy(self) -> None:
        """load() stores the policy on the engine instance."""
        eng = PolicyEngine()
        assert eng.policy is None
        policy = eng.load(POLICY_PATH)
        assert eng.policy is policy


# --------------------------------------------------------------------------- #
# Rule matching for each category
# --------------------------------------------------------------------------- #


class TestRuleMatching:
    """Tests for evaluating each intent category against policy rules."""

    def test_summarization_allows(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Summarization maps to allow-analysis with ALLOW."""
        classification = make_classification("summarization")
        result = engine.evaluate("summarization", classification)
        assert result.decision == Decision.ALLOW
        assert result.matched_rule_id == "allow-analysis"
        assert result.audit_level == AuditLevel.STANDARD
        assert result.color == "green"

    def test_translation_allows(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Translation maps to allow-analysis with ALLOW."""
        classification = make_classification("translation")
        result = engine.evaluate("translation", classification)
        assert result.decision == Decision.ALLOW
        assert result.matched_rule_id == "allow-analysis"
        assert result.audit_level == AuditLevel.STANDARD
        assert result.color == "green"

    def test_summarization_and_translation_share_rule(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Both summarization and translation match the same rule."""
        r1 = engine.evaluate("summarization", make_classification("summarization"))
        r2 = engine.evaluate("translation", make_classification("translation"))
        assert r1.matched_rule_id == r2.matched_rule_id == "allow-analysis"

    def test_threat_assessment(self, engine: PolicyEngine, make_classification) -> None:
        """Threat assessment maps to allow-threat-assessment with ALLOW."""
        classification = make_classification("threat_assessment")
        result = engine.evaluate("threat_assessment", classification)
        assert result.decision == Decision.ALLOW
        assert result.matched_rule_id == "allow-threat-assessment"
        assert result.audit_level == AuditLevel.ENHANCED
        assert result.color == "yellow"

    def test_missile_defense(self, engine: PolicyEngine, make_classification) -> None:
        """Missile defense maps to allow-missile-defense with ALLOW."""
        classification = make_classification("missile_defense")
        result = engine.evaluate("missile_defense", classification)
        assert result.decision == Decision.ALLOW
        assert result.matched_rule_id == "allow-missile-defense"
        assert result.audit_level == AuditLevel.ENHANCED
        assert result.color == "green"
        assert result.note == "Pre-authorized. No phone call required."

    def test_cyber_defense(self, engine: PolicyEngine, make_classification) -> None:
        """Cyber defense maps to allow-cyber-defense with ALLOW_CONSTRAINED."""
        classification = make_classification("cyber_defense")
        result = engine.evaluate("cyber_defense", classification)
        assert result.decision == Decision.ALLOW_CONSTRAINED
        assert result.matched_rule_id == "allow-cyber-defense"
        assert result.audit_level == AuditLevel.ENHANCED
        assert result.color == "yellow"
        assert "Defensive operations only" in result.constraints
        assert "Own or allied infrastructure targets only" in result.constraints

    def test_warranted_surveillance_allows_constrained(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Warranted surveillance maps to allow-warranted-analysis."""
        classification = make_classification("warranted_surveillance")
        result = engine.evaluate("warranted_surveillance", classification)
        assert result.decision == Decision.ALLOW_CONSTRAINED
        assert result.matched_rule_id == "allow-warranted-analysis"
        assert result.audit_level == AuditLevel.ENHANCED
        assert result.color == "yellow"
        assert "Valid judicial warrant must be on file" in result.constraints
        expected_note = (
            "Court-authorized. Requires warrant verification and legal review."
        )
        assert result.note == expected_note

    def test_bulk_surveillance_blocks(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Bulk surveillance maps to block-surveillance with BLOCK."""
        classification = make_classification("bulk_surveillance")
        result = engine.evaluate("bulk_surveillance", classification)
        assert result.decision == Decision.BLOCK
        assert result.matched_rule_id == "block-surveillance"
        assert result.audit_level == AuditLevel.CRITICAL
        assert result.color == "red"
        assert "trust_safety" in result.alerts
        assert "inspector_general" in result.alerts

    def test_pattern_of_life_blocks(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Pattern of life maps to block-surveillance with BLOCK."""
        classification = make_classification("pattern_of_life")
        result = engine.evaluate("pattern_of_life", classification)
        assert result.decision == Decision.BLOCK
        assert result.matched_rule_id == "block-surveillance"
        assert result.audit_level == AuditLevel.CRITICAL
        assert result.color == "red"

    def test_autonomous_targeting_blocks(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """Autonomous targeting maps to block-autonomous-lethal with BLOCK."""
        classification = make_classification("autonomous_targeting")
        result = engine.evaluate("autonomous_targeting", classification)
        assert result.decision == Decision.BLOCK
        assert result.matched_rule_id == "block-autonomous-lethal"
        assert result.audit_level == AuditLevel.CRITICAL
        assert result.color == "red"
        assert "trust_safety" in result.alerts
        assert "inspector_general" in result.alerts
        assert "legal_counsel" in result.alerts


# --------------------------------------------------------------------------- #
# No-match default behavior
# --------------------------------------------------------------------------- #


class TestNoMatchDefault:
    """Tests for the default BLOCK behavior when no rule matches."""

    def test_unknown_category_returns_block(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """An unrecognized category returns BLOCK with unknown-intent."""
        classification = make_classification("nonexistent_category")
        result = engine.evaluate("nonexistent_category", classification)
        assert result.decision == Decision.BLOCK
        assert result.matched_rule_id == "unknown-intent"
        assert result.audit_level == AuditLevel.CRITICAL
        assert "trust_safety" in result.alerts

    def test_empty_category_returns_block(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """An empty string category returns BLOCK with unknown-intent."""
        classification = make_classification("")
        result = engine.evaluate("", classification)
        assert result.decision == Decision.BLOCK
        assert result.matched_rule_id == "unknown-intent"

    def test_unknown_preserves_classification(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """The classification is preserved on the BLOCK result."""
        classification = make_classification("unknown_thing")
        result = engine.evaluate("unknown_thing", classification)
        assert result.classification is classification


# --------------------------------------------------------------------------- #
# Classification preserved on result
# --------------------------------------------------------------------------- #


class TestEvaluationResultFields:
    """Tests verifying EvaluationResult fields are populated correctly."""

    def test_classification_attached(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """The classification object is attached to the evaluation result."""
        classification = make_classification("summarization")
        result = engine.evaluate("summarization", classification)
        assert result.classification is classification
        assert result.classification.intent_category == "summarization"

    def test_llm_response_is_none(
        self, engine: PolicyEngine, make_classification
    ) -> None:
        """llm_response defaults to None on evaluation results."""
        classification = make_classification("summarization")
        result = engine.evaluate("summarization", classification)
        assert result.llm_response is None


# --------------------------------------------------------------------------- #
# Invalid YAML raises ValueError
# --------------------------------------------------------------------------- #


class TestInvalidYaml:
    """Tests for validation errors when loading malformed YAML."""

    @staticmethod
    def _write_yaml(data: dict) -> str:
        """Write a dict as YAML to a temp file and return its path."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        yaml.dump(data, tmp)
        tmp.close()
        return tmp.name

    def test_missing_policy_name(self) -> None:
        """Missing policy.name raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"version": "1.0"},
                "rules": [
                    {
                        "id": "r1",
                        "decision": "ALLOW",
                        "match_categories": ["test"],
                    }
                ],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="policy.name"):
            eng.load(path)

    def test_missing_policy_version(self) -> None:
        """Missing policy.version raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"name": "test"},
                "rules": [
                    {
                        "id": "r1",
                        "decision": "ALLOW",
                        "match_categories": ["test"],
                    }
                ],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="policy.version"):
            eng.load(path)

    def test_missing_policy_section(self) -> None:
        """Missing top-level policy section raises ValueError."""
        path = self._write_yaml(
            {
                "rules": [
                    {
                        "id": "r1",
                        "decision": "ALLOW",
                        "match_categories": ["test"],
                    }
                ],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="policy"):
            eng.load(path)

    def test_missing_rules_section(self) -> None:
        """Missing top-level rules section raises ValueError."""
        path = self._write_yaml({"policy": {"name": "test", "version": "1.0"}})
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="rules"):
            eng.load(path)

    def test_missing_rule_id(self) -> None:
        """A rule missing its id raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"name": "test", "version": "1.0"},
                "rules": [{"decision": "ALLOW", "match_categories": ["test"]}],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="id"):
            eng.load(path)

    def test_missing_rule_decision(self) -> None:
        """A rule missing its decision raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"name": "test", "version": "1.0"},
                "rules": [{"id": "r1", "match_categories": ["test"]}],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="decision"):
            eng.load(path)

    def test_missing_rule_match_categories(self) -> None:
        """A rule missing match_categories raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"name": "test", "version": "1.0"},
                "rules": [{"id": "r1", "decision": "ALLOW"}],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="match_categories"):
            eng.load(path)

    def test_empty_rules_list(self) -> None:
        """An empty rules list raises ValueError."""
        path = self._write_yaml(
            {
                "policy": {"name": "test", "version": "1.0"},
                "rules": [],
            }
        )
        eng = PolicyEngine()
        with pytest.raises(ValueError, match="rules"):
            eng.load(path)


# --------------------------------------------------------------------------- #
# Engine state
# --------------------------------------------------------------------------- #


class TestEngineState:
    """Tests for PolicyEngine initialization and state management."""

    def test_init_no_policy(self) -> None:
        """A freshly initialized engine has no policy."""
        eng = PolicyEngine()
        assert eng.policy is None

    def test_evaluate_without_load_raises(self, make_classification) -> None:
        """Calling evaluate before load raises RuntimeError."""
        eng = PolicyEngine()
        classification = make_classification("summarization")
        with pytest.raises(RuntimeError, match="No policy loaded"):
            eng.evaluate("summarization", classification)

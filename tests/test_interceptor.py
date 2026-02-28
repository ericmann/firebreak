"""Tests for the request interceptor and audit log."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from firebreak.audit import AuditLog
from firebreak.classifier import ClassifierCache, IntentClassifier
from firebreak.interceptor import FirebreakInterceptor
from firebreak.models import (
    ClassificationResult,
    Decision,
)
from firebreak.policy import PolicyEngine

# Path to the real policy file
POLICY_PATH = "policies/defense-standard.yaml"


def _make_interceptor_with_cache(prompt: str, category: str, confidence: float = 0.95):
    """Build an interceptor with a pre-cached classification."""
    engine = PolicyEngine()
    engine.load(POLICY_PATH)

    cache = ClassifierCache()
    cache.set(
        prompt,
        ClassificationResult(
            intent_category=category,
            confidence=confidence,
            raw_prompt=prompt,
            timestamp=datetime.now(),
        ),
    )
    classifier = IntentClassifier(
        categories=engine.policy.categories,
        cache=cache,
    )
    audit_log = AuditLog()
    interceptor = FirebreakInterceptor(
        policy_engine=engine,
        classifier=classifier,
        audit_log=audit_log,
    )
    return interceptor, audit_log


class TestAuditLog:
    """Tests for the AuditLog class."""

    def test_log_creates_entry(self):
        """log() creates and appends an AuditEntry."""
        audit_log = AuditLog()
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
        )
        evaluation = MagicMock()
        evaluation.alerts = []

        entry = audit_log.log("test", classification, evaluation)
        assert entry.prompt_text == "test"
        assert entry.classification is classification
        assert len(audit_log.entries) == 1

    def test_unique_entry_ids(self):
        """Each entry gets a unique UUID."""
        audit_log = AuditLog()
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
        )
        evaluation = MagicMock()
        evaluation.alerts = []

        e1 = audit_log.log("test1", classification, evaluation)
        e2 = audit_log.log("test2", classification, evaluation)
        assert e1.id != e2.id

    def test_get_entries(self):
        """get_entries() returns all entries."""
        audit_log = AuditLog()
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
        )
        evaluation = MagicMock()
        evaluation.alerts = []

        audit_log.log("test1", classification, evaluation)
        audit_log.log("test2", classification, evaluation)
        assert len(audit_log.get_entries()) == 2

    def test_get_alerts(self):
        """get_alerts() returns only entries with alerts."""
        audit_log = AuditLog()
        classification = ClassificationResult(
            intent_category="summarization",
            confidence=0.9,
            raw_prompt="test",
        )
        no_alerts = MagicMock()
        no_alerts.alerts = []
        with_alerts = MagicMock()
        with_alerts.alerts = ["trust_safety"]

        audit_log.log("safe", classification, no_alerts)
        audit_log.log("blocked", classification, with_alerts)
        alerts = audit_log.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].prompt_text == "blocked"


class TestFirebreakInterceptor:
    """Tests for the FirebreakInterceptor pipeline."""

    @patch("firebreak.interceptor.anthropic.Anthropic")
    def test_allow_pipeline(self, mock_anthropic):
        """An allowed prompt flows through classify -> evaluate -> LLM."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Here is the summary.")]
        )

        prompt = "Summarize the briefing."
        interceptor, audit_log = _make_interceptor_with_cache(prompt, "summarization")

        events = []
        interceptor.on(
            "prompt_received",
            lambda d: events.append(("prompt_received", d)),
        )
        interceptor.on("classified", lambda d: events.append(("classified", d)))
        interceptor.on("evaluated", lambda d: events.append(("evaluated", d)))
        interceptor.on("response", lambda d: events.append(("response", d)))

        result = interceptor.evaluate_request(prompt)

        assert result.decision == Decision.ALLOW
        assert result.llm_response == "Here is the summary."
        assert len(audit_log.entries) == 1
        event_names = [e[0] for e in events]
        assert "prompt_received" in event_names
        assert "classified" in event_names
        assert "evaluated" in event_names
        assert "response" in event_names

    @patch("firebreak.interceptor.anthropic.Anthropic")
    def test_block_pipeline(self, mock_anthropic):
        """A blocked prompt fires blocked and alert events, no LLM."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        prompt = "Cross-reference phone records"
        interceptor, audit_log = _make_interceptor_with_cache(
            prompt, "bulk_surveillance"
        )

        events = []
        interceptor.on("blocked", lambda d: events.append(("blocked", d)))
        interceptor.on("alert", lambda d: events.append(("alert", d)))

        result = interceptor.evaluate_request(prompt)

        assert result.decision == Decision.BLOCK
        assert result.llm_response is None
        mock_client.messages.create.assert_not_called()
        assert len(audit_log.entries) == 1
        event_names = [e[0] for e in events]
        assert "blocked" in event_names
        assert "alert" in event_names

    @patch("firebreak.interceptor.anthropic.Anthropic")
    def test_cached_classification_skips_api(self, mock_anthropic):
        """Cached classification uses cache, not classifier API."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Response text.")]
        )

        prompt = "summarize this"
        interceptor, _ = _make_interceptor_with_cache(prompt, "summarization")
        result = interceptor.evaluate_request(prompt)

        assert result.decision == Decision.ALLOW
        assert result.matched_rule_id == "allow-analysis"

    @patch("firebreak.interceptor.anthropic.Anthropic")
    def test_alert_events_per_target(self, mock_anthropic):
        """Each alert target fires a separate alert event."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        prompt = "Strike coordinates"
        interceptor, _ = _make_interceptor_with_cache(prompt, "autonomous_targeting")

        alert_targets = []
        interceptor.on("alert", lambda d: alert_targets.append(d["target"]))

        interceptor.evaluate_request(prompt)

        assert "trust_safety" in alert_targets
        assert "inspector_general" in alert_targets
        assert "legal_counsel" in alert_targets

    @patch("firebreak.interceptor.anthropic.Anthropic")
    def test_constrained_allow(self, mock_anthropic):
        """ALLOW_CONSTRAINED still calls the LLM."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Defensive analysis.")]
        )

        prompt = "Analyze network intrusion"
        interceptor, _ = _make_interceptor_with_cache(prompt, "cyber_defense")

        result = interceptor.evaluate_request(prompt)

        assert result.decision == Decision.ALLOW_CONSTRAINED
        assert result.llm_response == "Defensive analysis."
        mock_client.messages.create.assert_called_once()

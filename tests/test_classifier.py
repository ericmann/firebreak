"""Tests for the intent classifier."""

import json
import tempfile
from unittest.mock import MagicMock, patch

from firebreak.classifier import ClassifierCache, IntentClassifier
from firebreak.models import ClassificationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mock_classify_response(category: str, confidence: float = 0.95):
    """Build a mock Anthropic API response for classification.

    Args:
        category: The intent category the mock should return.
        confidence: The confidence score the mock should return.

    Returns:
        A MagicMock shaped like an Anthropic messages response.
    """
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=(f'{{"category": "{category}", "confidence": {confidence}}}'))
    ]
    return mock_response


def _write_cache_file(data: dict) -> str:
    """Write a temporary JSON cache file and return its path.

    Args:
        data: Dictionary to serialize as JSON.

    Returns:
        Path to the temporary file.
    """
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# ClassifierCache tests
# ---------------------------------------------------------------------------


class TestClassifierCache:
    """Tests for ClassifierCache."""

    def test_load_from_json_file(self):
        """Cache loads entries from a JSON file on disk."""
        cache_data = {
            "summarize this report": {
                "category": "summarization",
                "confidence": 0.85,
            }
        }
        path = _write_cache_file(cache_data)

        cache = ClassifierCache(cache_path=path)
        result = cache.get("summarize this report")

        assert result is not None
        assert result.intent_category == "summarization"
        assert result.confidence == 0.85
        assert result.raw_prompt == "summarize this report"

    def test_get_hit(self):
        """Cache returns a result for a previously stored prompt."""
        cache = ClassifierCache()
        result = ClassificationResult(
            intent_category="translation",
            confidence=0.90,
            raw_prompt="translate this",
        )
        cache.set("Translate this", result)

        retrieved = cache.get("  translate this  ")
        assert retrieved is not None
        assert retrieved.intent_category == "translation"
        assert retrieved.confidence == 0.90

    def test_get_miss(self):
        """Cache returns None for an unknown prompt."""
        cache = ClassifierCache()
        assert cache.get("never seen this prompt") is None

    def test_set_and_retrieve(self):
        """Stores a result and retrieves it by normalized key."""
        cache = ClassifierCache()
        result = ClassificationResult(
            intent_category="threat_assessment",
            confidence=0.92,
            raw_prompt="assess the threat level",
        )
        cache.set("  Assess the Threat Level  ", result)

        retrieved = cache.get("assess the threat level")
        assert retrieved is result

    def test_empty_cache_path_none(self):
        """Cache with no file path starts empty."""
        cache = ClassifierCache(cache_path=None)
        assert cache.get("anything") is None


# ---------------------------------------------------------------------------
# IntentClassifier tests
# ---------------------------------------------------------------------------

CATEGORIES = [
    "summarization",
    "translation",
    "threat_assessment",
    "autonomous_targeting",
]


class TestIntentClassifier:
    """Tests for IntentClassifier."""

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_successful_classification(self, mock_anthropic_cls):
        """Classifier returns a correct result from the API."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_classify_response(
            "summarization", 0.88
        )

        classifier = IntentClassifier(categories=CATEGORIES)
        result = classifier.classify("Summarize this briefing.")

        assert result.intent_category == "summarization"
        assert result.confidence == 0.88
        assert result.raw_prompt == "Summarize this briefing."
        mock_client.messages.create.assert_called_once()

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_cache_hit_skips_api_call(self, mock_anthropic_cls):
        """When the cache has a hit, the API is never called."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        cache = ClassifierCache()
        cached_result = ClassificationResult(
            intent_category="translation",
            confidence=0.90,
            raw_prompt="translate this message",
        )
        cache.set("translate this message", cached_result)

        classifier = IntentClassifier(categories=CATEGORIES, cache=cache)
        result = classifier.classify("translate this message")

        assert result is cached_result
        mock_client.messages.create.assert_not_called()

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_api_error_returns_unclassified(self, mock_anthropic_cls):
        """An API error results in an unclassified fallback."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API unavailable")

        classifier = IntentClassifier(categories=CATEGORIES)
        result = classifier.classify("Some prompt text")

        assert result.intent_category == "unclassified"
        assert result.confidence == 0.0
        assert result.raw_prompt == "Some prompt text"

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_invalid_category_returns_unclassified(self, mock_anthropic_cls):
        """A category not in the valid list is treated as failure."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_classify_response(
            "made_up_category", 0.80
        )

        classifier = IntentClassifier(categories=CATEGORIES)
        result = classifier.classify("Do something unexpected")

        assert result.intent_category == "unclassified"
        assert result.confidence == 0.0
        assert result.raw_prompt == "Do something unexpected"

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_malformed_json_returns_unclassified(self, mock_anthropic_cls):
        """Malformed JSON from API results in unclassified fallback."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json {{{")]
        mock_client.messages.create.return_value = mock_response

        classifier = IntentClassifier(categories=CATEGORIES)
        result = classifier.classify("Parse this badly")

        assert result.intent_category == "unclassified"
        assert result.confidence == 0.0

    @patch("firebreak.classifier.anthropic.Anthropic")
    def test_successful_result_is_cached(self, mock_anthropic_cls):
        """A successful classification is stored in the cache."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_classify_response(
            "threat_assessment", 0.91
        )

        cache = ClassifierCache()
        classifier = IntentClassifier(categories=CATEGORIES, cache=cache)
        result = classifier.classify("Assess threat level")

        assert result.intent_category == "threat_assessment"

        cached = cache.get("Assess threat level")
        assert cached is not None
        assert cached.intent_category == "threat_assessment"
        assert cached.confidence == 0.91

"""Intent classifier using Claude API to categorize prompts."""

import json
from datetime import datetime

import anthropic

from firebreak.models import ClassificationResult

SYSTEM_PROMPT_TEMPLATE = (
    "You are an intent classifier for an AI deployment"
    " policy system.\n\n"
    "Classify the following user prompt into exactly ONE"
    " of these categories:\n"
    "{categories}\n\n"
    "Respond with ONLY a JSON object in this exact format,"
    " no other text:\n"
    '{{"category": "<category_name>",'
    ' "confidence": <float_between_0_and_1>}}'
)


class ClassifierCache:
    """Cache for pre-computed intent classifications.

    Stores classification results keyed by normalized prompt text
    (stripped and lowercased). Optionally loads pre-computed results
    from a JSON file on disk.

    Attributes:
        _cache: Internal dictionary mapping normalized prompts
            to results.
    """

    def __init__(self, cache_path: str | None = None) -> None:
        """Initialize the cache, optionally loading from a JSON file.

        Args:
            cache_path: Path to a JSON file with pre-computed
                classifications. If None, starts with an empty cache.
        """
        self._cache: dict[str, ClassificationResult] = {}
        if cache_path is not None:
            self._load_from_file(cache_path)

    def _load_from_file(self, cache_path: str) -> None:
        """Load pre-computed classifications from a JSON file.

        Args:
            cache_path: Path to the JSON cache file.
        """
        with open(cache_path) as f:
            data = json.load(f)
        for prompt_key, entry in data.items():
            result = ClassificationResult(
                intent_category=entry["category"],
                confidence=entry["confidence"],
                raw_prompt=prompt_key,
                timestamp=datetime.now(),
            )
            self._cache[prompt_key] = result

    def get(self, prompt: str) -> ClassificationResult | None:
        """Look up a cached classification result.

        Args:
            prompt: The raw prompt text to look up.

        Returns:
            The cached ClassificationResult if found, or None
            on a miss.
        """
        key = prompt.strip().lower()
        return self._cache.get(key)

    def set(self, prompt: str, result: ClassificationResult) -> None:
        """Store a classification result in the cache.

        Args:
            prompt: The raw prompt text to use as the cache key.
            result: The ClassificationResult to cache.
        """
        key = prompt.strip().lower()
        self._cache[key] = result


class IntentClassifier:
    """Classifies prompts into intent categories via the Claude API.

    Uses an Anthropic model to determine which predefined category a
    prompt belongs to. Results are cached to avoid redundant API calls.

    Attributes:
        categories: Valid intent categories for classification.
        cache: Optional cache for storing/retrieving results.
        model: The Anthropic model identifier to use.
    """

    def __init__(
        self,
        categories: list[str],
        cache: ClassifierCache | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        """Initialize the classifier.

        Args:
            categories: List of valid intent category names.
            cache: Optional ClassifierCache for caching results.
            model: Anthropic model identifier to use for
                classification.
        """
        self.categories = categories
        self.cache = cache
        self.model = model
        self._client = anthropic.Anthropic()

    def classify(self, prompt: str) -> ClassificationResult:
        """Classify a prompt into one of the configured categories.

        Checks the cache first. On a cache miss, calls the Anthropic
        API to classify the prompt. On any error (API, parsing, invalid
        category), returns an "unclassified" result with confidence 0.0.

        Args:
            prompt: The user prompt text to classify.

        Returns:
            A ClassificationResult with the determined category
            and confidence.
        """
        if self.cache is not None:
            cached = self.cache.get(prompt)
            if cached is not None:
                return cached

        try:
            system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                categories="\n".join(self.categories)
            )

            response = self._client.messages.create(
                model=self.model,
                max_tokens=256,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text
            parsed = json.loads(response_text)

            category = parsed["category"]
            confidence = float(parsed["confidence"])

            if category not in self.categories:
                return ClassificationResult(
                    intent_category="unclassified",
                    confidence=0.0,
                    raw_prompt=prompt,
                )

            result = ClassificationResult(
                intent_category=category,
                confidence=confidence,
                raw_prompt=prompt,
            )

            if self.cache is not None:
                self.cache.set(prompt, result)

            return result

        except Exception:
            return ClassificationResult(
                intent_category="unclassified",
                confidence=0.0,
                raw_prompt=prompt,
            )

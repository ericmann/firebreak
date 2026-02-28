"""Tests that demo scenario prompts stay in sync with the classifier cache."""

import json
from pathlib import Path

import yaml

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def test_every_scenario_prompt_has_cache_entry():
    """Every scenario prompt (normalized) must have a matching cache key."""
    scenarios_path = DEMO_DIR / "scenarios.yaml"
    cache_path = DEMO_DIR / "classifier_cache.json"

    with open(scenarios_path) as f:
        scenarios = yaml.safe_load(f)["scenarios"]

    with open(cache_path) as f:
        cache = json.load(f)

    for scenario in scenarios:
        prompt = scenario["prompt"].strip().lower()
        assert prompt in cache, (
            f"Scenario {scenario['id']!r} prompt not found in cache. "
            f"Expected key: {prompt!r}"
        )

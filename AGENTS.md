# AGENTS.md — Firebreak Claude Code Coordination Guide

> This file tells Claude Code how to work on this project. Read SPEC.md first for full context.

---

## Project Overview

Firebreak is a policy-as-code enforcement proxy for LLM API deployments. It intercepts prompts, classifies their intent, evaluates them against pre-negotiated YAML policy rules, and allows or blocks them — with full audit logging. The MVP is a Python CLI demo with a Rich TUI dashboard.

**This is a hackathon project.** We have ~5 hours of build time. Speed and correctness matter more than production polish. Shipping a working demo beats architectural perfection.

---

## Architecture at a Glance

```
User prompt → Interceptor → Classifier (Claude API) → Policy Engine (YAML rules) → Decision
                                                                                      ↓
                                                              ALLOW → forward to Claude API → response
                                                              BLOCK → return explanation + fire alerts
                                                                                      ↓
                                                                              Audit Log + Dashboard
```

All components live in `src/firebreak/`. Entry point is `src/firebreak/demo.py`.

---

## Code Conventions

- **Python 3.11+**. Use type hints everywhere. Use dataclasses, not dicts.
- **No classes where functions suffice.** But the spec defines several classes — follow the spec.
- **Docstrings** on all public classes and methods. Google style.
- **Imports:** Use absolute imports (`from firebreak.models import Decision`).
- **Error handling:** Fail closed. If anything unexpected happens during classification or evaluation, the decision is BLOCK. Never allow a request because of an error.
- **Tests:** Use pytest. Each module gets a corresponding test file in `tests/`. Mock the Anthropic API — do not make real API calls in tests (except `test_classifier_live.py` if it exists).
- **Dependencies:** Only `anthropic`, `pyyaml`, `rich`. Nothing else unless absolutely necessary.
- **YAML files** in `policies/` and `demo/` are the source of truth for policy rules and demo scenarios. Do not hardcode policy logic in Python.

---

## Module Dependency Graph

```
models.py          ← no dependencies (pure data structures)
    ↑
policy.py           ← depends on models
classifier.py       ← depends on models
    ↑
interceptor.py      ← depends on policy, classifier, audit, models
audit.py            ← depends on models
    ↑
dashboard.py        ← depends on models (reads EvaluationResult, AuditEntry)
    ↑
demo.py             ← depends on everything (orchestrator)
```

**Build order:** models → policy + classifier (parallel) → audit → interceptor → dashboard → demo

---

## Module Specifications

### `src/firebreak/models.py`

Pure data structures. No business logic. No imports beyond stdlib.

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class Decision(Enum):
    ALLOW = "ALLOW"
    ALLOW_CONSTRAINED = "ALLOW_CONSTRAINED"
    BLOCK = "BLOCK"

class AuditLevel(Enum):
    STANDARD = "standard"
    ENHANCED = "enhanced"
    CRITICAL = "critical"
```

Implement these dataclasses exactly:
- `PolicyRule`: id, description, match_categories (list[str]), decision (Decision), audit (AuditLevel), requires_human (bool, default False), constraints (list[str], default empty), alerts (list[str], default empty), color (str), note (str, default "")
- `Policy`: name, version, effective, signatories (dict), rules (list[PolicyRule]), categories (list[str])
- `ClassificationResult`: intent_category (str), confidence (float), raw_prompt (str), timestamp (datetime)
- `EvaluationResult`: decision (Decision), matched_rule_id (str), rule_description (str), audit_level (AuditLevel), alerts (list[str]), constraints (list[str]), color (str), note (str), classification (ClassificationResult), llm_response (str | None, default None)
- `AuditEntry`: id (str — use uuid4), timestamp (datetime), prompt_text (str), classification (ClassificationResult), evaluation (EvaluationResult)
- `DemoScenario`: id (str), prompt (str), expected_category (str), narration (str)

### `src/firebreak/policy.py`

**Class: `PolicyEngine`**

- `__init__(self)` — empty, call load() separately
- `load(self, path: str) -> Policy` — parse YAML, validate structure, build PolicyRule objects, store as self.policy
- `evaluate(self, intent_category: str, metadata: dict | None = None) -> EvaluationResult` — iterate rules, find first rule where intent_category is in match_categories, return corresponding EvaluationResult. **If no rule matches: return BLOCK decision with "unknown-intent" rule_id, CRITICAL audit, and alert to trust_safety.**
- The `evaluate` method requires a `ClassificationResult` to embed in the result. Accept it as a parameter.

Validation: Raise `ValueError` if YAML is missing required fields (policy.name, policy.version, rules with id/decision/match_categories).

### `src/firebreak/classifier.py`

**Class: `ClassifierCache`**

- `__init__(self, cache_path: str | None = None)` — if path provided, load pre-computed classifications from JSON file
- `get(self, prompt: str) -> ClassificationResult | None`
- `set(self, prompt: str, result: ClassificationResult)`
- Cache key: the exact prompt string (stripped and lowered)

**Class: `IntentClassifier`**

- `__init__(self, categories: list[str], cache: ClassifierCache | None = None, model: str = "claude-sonnet-4-5-20250514")`
- `classify(self, prompt: str) -> ClassificationResult`
  - Check cache first. If hit, return cached result.
  - Build system prompt listing the valid categories. Instruct the model to respond with ONLY a JSON object: `{"category": "...", "confidence": 0.XX}`
  - Call the Anthropic API. Parse the JSON response.
  - If the returned category is not in the valid categories list, treat as classification failure.
  - On ANY error (API error, parse error, invalid category): return a ClassificationResult with category="unclassified" and confidence=0.0. **This will trigger a BLOCK via the policy engine's no-match rule.**
  - Cache successful results.

**System prompt template:**
```
You are an intent classifier for an AI deployment policy system.

Classify the following user prompt into exactly ONE of these categories:
{newline-separated category list}

Respond with ONLY a JSON object in this exact format, no other text:
{"category": "<category_name>", "confidence": <float_between_0_and_1>}
```

### `src/firebreak/audit.py`

**Class: `AuditLog`**

- `__init__(self)`
- `self.entries: list[AuditEntry]` — append-only
- `log(self, prompt: str, classification: ClassificationResult, evaluation: EvaluationResult) -> AuditEntry` — create AuditEntry with uuid and timestamp, append, return it
- `get_entries(self) -> list[AuditEntry]`
- `get_alerts(self) -> list[AuditEntry]` — return only entries where evaluation has alerts

Simple. No persistence needed for the MVP.

### `src/firebreak/interceptor.py`

**Class: `FirebreakInterceptor`**

- `__init__(self, policy_engine: PolicyEngine, classifier: IntentClassifier, audit_log: AuditLog, llm_model: str = "claude-sonnet-4-5-20250514")`
- `self.callbacks: dict[str, list[Callable]]` — event callback registry
- `on(self, event: str, callback: Callable)` — register a callback for an event
- `_emit(self, event: str, data: Any)` — fire all callbacks for an event

- `async evaluate_request(self, prompt: str, metadata: dict | None = None) -> EvaluationResult`:
  1. `_emit("prompt_received", prompt)`
  2. Classify: `result = self.classifier.classify(prompt)`
  3. `_emit("classified", result)`
  4. Evaluate: `evaluation = self.policy_engine.evaluate(result.intent_category, result, metadata)`
  5. `_emit("evaluated", evaluation)`
  6. If ALLOW or ALLOW_CONSTRAINED:
     - Call Claude API with the original prompt
     - Attach the LLM response to the evaluation result
     - `_emit("response", evaluation)`
  7. If BLOCK:
     - `_emit("blocked", evaluation)`
     - For each alert target: `_emit("alert", {"target": target, "evaluation": evaluation})`
  8. Log to audit: `self.audit_log.log(prompt, result, evaluation)`
  9. Return evaluation

**Note on async:** Use `async/await` with the Anthropic async client for the LLM calls. The classifier and interceptor should both be async. If this causes complexity issues, synchronous is acceptable for the MVP — just make it work.

### `src/firebreak/dashboard.py`

**Class: `FirebreakDashboard`**

Uses `rich` library. Four-panel layout.

- `__init__(self, policy: Policy)`
- `self.layout` — `rich.layout.Layout` with four rows
- `self.evaluation_history: list[EvaluationResult]`
- `self.alerts: list[dict]`
- `self.current_prompt: str | None`
- `self.current_classification: ClassificationResult | None`
- `self.current_evaluation: EvaluationResult | None`

**Panel 1 — Policy Info (top, small):**
Show policy name, version, signatory names with checkmarks, rule count, effective date.

**Panel 2 — Current Request (middle-top):**
Shows the prompt text being evaluated. After classification, shows intent category and confidence. After evaluation, shows decision with color-coded text (green/yellow/red), matched rule ID, and note if present.

**Panel 3 — Evaluation History (middle-bottom):**
A `rich.table.Table` with columns: TIME, DECISION, INTENT, RULE, AUDIT.
Decision column uses colored dots: 🟢 ALLOW, 🟡 CONSTRAINED, 🔴 BLOCK.
Each completed evaluation adds a row.

**Panel 4 — Alerts (bottom):**
Shows alert entries with timestamp, severity, rule that triggered, and notification targets.
Only visible when alerts exist. Use `rich.panel.Panel` with border_style="red" when alerts are present.

**Methods:**
- `register_callbacks(self, interceptor: FirebreakInterceptor)` — subscribe to interceptor events and update dashboard state
- `render(self) -> Layout` — build and return the current layout
- `update_prompt(self, prompt: str)` — set current prompt, clear classification/evaluation
- `update_classification(self, result: ClassificationResult)` — set classification
- `update_evaluation(self, result: EvaluationResult)` — set evaluation, add to history, add alerts if any
- `clear_current(self)` — reset the current request panel for the next scenario

**Color mapping:**
```python
DECISION_COLORS = {
    Decision.ALLOW: "green",
    Decision.ALLOW_CONSTRAINED: "yellow",
    Decision.BLOCK: "bold red",
}
```

### `src/firebreak/demo.py`

**The main entry point.** Orchestrates the entire demo.

```python
def main():
    # Parse CLI args (--no-cache, --fast)
    # Load policy from policies/defense-standard.yaml
    # Initialize classifier with cache from demo/classifier_cache.json
    # Initialize audit log
    # Initialize interceptor
    # Initialize dashboard, register callbacks
    # Load scenarios from demo/scenarios.yaml
    # Use rich.live.Live context manager
    # For each scenario:
    #   1. Show scenario narration briefly (or print above the live display)
    #   2. Display prompt on dashboard
    #   3. Pause (configurable)
    #   4. Run interceptor.evaluate_request()
    #   5. Dashboard updates via callbacks
    #   6. Pause before next scenario
    # After all scenarios, hold the final display for 10 seconds
```

**Timing defaults:**
- Between scenarios: 3 seconds
- Between evaluation steps: 1.5 seconds
- `--fast` mode: 0.5 seconds / 0.25 seconds
- Final hold: 10 seconds

**CLI arguments:**
- `--no-cache` — skip the classifier cache, make live API calls
- `--fast` — reduce all pauses
- `--policy PATH` — custom policy file (default: `policies/defense-standard.yaml`)
- `--scenarios PATH` — custom scenarios file (default: `demo/scenarios.yaml`)

Use `argparse` for CLI parsing. Keep it simple.

---

## Testing Strategy

### Unit Tests (required)

| Test file | What it covers |
|-----------|---------------|
| `tests/test_models.py` | Dataclass instantiation, enum values, default fields |
| `tests/test_policy.py` | Load YAML, validate, evaluate each rule, no-match default, invalid YAML |
| `tests/test_classifier.py` | Mock API response parsing, cache hit/miss, error fallback to "unclassified" |
| `tests/test_interceptor.py` | Full pipeline with mocked classifier and policy engine, callback emission |

### Integration Test (nice to have)

| Test file | What it covers |
|-----------|---------------|
| `tests/test_demo_flow.py` | Load real policy + scenarios, mock only the Anthropic API, run all 6 scenarios, verify decisions match expected |

### How to Mock the Anthropic API

```python
from unittest.mock import MagicMock, patch

def mock_classify_response(category: str, confidence: float = 0.95):
    """Create a mock Anthropic API response for the classifier."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'{{"category": "{category}", "confidence": {confidence}}}')
    ]
    return mock_response
```

---

## Linear Integration

This project uses Linear for task tracking. When an MCP connection to Linear is available:

- **Project name:** Firebreak
- **Team:** Use Eric's default team
- **Ticket prefix:** FB
- **Labels:** `hackathon`, `mvp`
- **Ticket format:** Title matches the ticket names in SPEC.md (e.g., "FB-001: Project Scaffold & Data Models")
- **Descriptions:** Copy acceptance criteria from SPEC.md into the ticket description as a checklist
- **Status workflow:** Backlog → In Progress → Done
- **Dependencies:** Note dependencies in ticket descriptions (e.g., "Blocked by: FB-001")

If Linear MCP is not available, just use the SPEC.md ticket list as the task tracker.

---

## Key Reminders for Claude Code

1. **Read SPEC.md first.** It has the full context, architecture, and detailed acceptance criteria for every ticket.
2. **Fail closed.** Any error in classification or evaluation results in BLOCK. Never ALLOW because of an error.
3. **Cache is critical.** The demo must work reliably even if the Anthropic API is slow or rate-limited. Pre-cache all 6 demo scenario classifications.
4. **Don't over-engineer.** This is a 5-hour hackathon. No databases. No HTTP servers. No Docker. No async if it causes problems. Working > elegant.
5. **The demo is the deliverable.** If something works but doesn't display well on the dashboard, it might as well not work. Visual impact matters.
6. **Color coding is non-negotiable.** Green = ALLOW, Yellow = CONSTRAINED, Red = BLOCK. This is the visual through-line of the entire demo.
7. **Respect the YAML.** Policy logic lives in YAML files, not in Python. The Python code reads and evaluates — it does not define the rules.
8. **Test with the real demo scenarios.** The 6 prompts in `demo/scenarios.yaml` are the acceptance test for the entire project.
9. **If you're unsure about a design decision,** choose the simpler option.
10. **Typing effects are nice-to-have.** Static prompt display is fine. The evaluation pipeline and color-coded decisions are what matter.

---

## Quick Start for a New Claude Code Session

If you're a Claude Code instance picking up work on this project:

```bash
# Check what exists
ls -la src/firebreak/
cat SPEC.md | head -50  # Get oriented

# Run existing tests
python -m pytest tests/ -v

# Run the demo (if it exists yet)
python -m firebreak.demo --fast

# Check which tickets are done
grep -n "Status:" SPEC.md  # Or check Linear
```

Then read the relevant ticket's acceptance criteria in SPEC.md and implement it.

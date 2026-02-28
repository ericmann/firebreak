<p align="center">
  <img src="https://raw.githubusercontent.com/ericmann/firebreak/main/docs/firebreak-icon.svg" alt="Firebreak" width="160" />
</p>

<h1 align="center">Firebreak</h1>

<p align="center">
  <strong>Policy-as-code enforcement for LLM API deployments.</strong><br>
  Pre-negotiated rules. Automatic enforcement. Complete audit trail.
</p>

<p align="center">
  <a href="https://github.com/ericmann/firebreak/actions/workflows/ci.yml"><img src="https://github.com/ericmann/firebreak/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white" alt="Python 3.11 | 3.12 | 3.13 | 3.14" />
  <img src="https://img.shields.io/badge/Claude_API-Anthropic-191919?logo=anthropic&logoColor=white" alt="Claude API" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License" />
</p>

---

## The Problem

The Pentagon says they can't call a CEO during a missile crisis. Anthropic says they can't allow mass surveillance or autonomous kill chains. Both are right — but they're treating an engineering problem as a political argument.

## The Solution

**Firebreak** is a policy enforcement proxy that sits between an LLM consumer and an LLM API endpoint. It intercepts every request, classifies the intent, evaluates it against a pre-negotiated policy, and either allows, constrains, or blocks the request — automatically, at machine speed, with a complete audit trail.

Both sides pre-negotiate the rules. Neither side can unilaterally change them. No phone calls during missile crises. No silent drift toward surveillance.

## How It Works

```mermaid
sequenceDiagram
    participant A as Analyst
    participant F as Firebreak
    participant C as Claude API

    A->>F: Submit prompt
    F->>F: Classify intent
    F->>F: Evaluate against policy

    alt ALLOW / ALLOW_CONSTRAINED
        F->>C: Forward prompt
        C-->>F: Response
        F->>F: Log to audit trail
        F-->>A: Return response
    else BLOCK
        F->>F: Log + fire alerts
        F-->>A: Return block explanation
    end
```

1. **A prompt arrives** — from an analyst, a defense workflow, or an intelligence system.
2. **Firebreak classifies the intent** using a lightweight LLM call (summarization, threat assessment, surveillance, targeting, etc.).
3. **Firebreak evaluates against policy** — pre-negotiated YAML rules defining what's allowed, constrained, or blocked.
4. **The decision executes automatically:**
   - **ALLOW** — prompt passes through. Standard audit logging.
   - **ALLOW_CONSTRAINED** — prompt passes through with enhanced logging, constraints noted, and informational alerts where configured.
   - **BLOCK** — prompt is rejected. The LLM never sees it. Critical alerts fire.
5. **Everything is logged** to an immutable audit trail.

## Policy Format

Policies are YAML files — version-controlled, testable, deployable:

```yaml
rules:
  - id: allow-missile-defense
    description: "Missile defense — pre-authorized, no escalation"
    match_categories: [missile_defense]
    decision: ALLOW
    audit: enhanced
    note: "Pre-authorized. No phone call required."

  - id: allow-warranted-analysis
    description: "Court-authorized surveillance — constrained allow"
    match_categories: [warranted_surveillance]
    decision: ALLOW_CONSTRAINED
    audit: enhanced
    constraints:
      - "Valid judicial warrant must be on file"
      - "Scope limited to named subjects in warrant"
    alerts: [legal_counsel]

  - id: block-surveillance
    description: "Mass domestic surveillance — hard block"
    match_categories: [bulk_surveillance, pattern_of_life]
    decision: BLOCK
    audit: critical
    alerts: [trust_safety, inspector_general]

  - id: block-autonomous-lethal
    description: "Autonomous lethal action — hard block"
    match_categories: [autonomous_targeting]
    decision: BLOCK
    audit: critical
    alerts: [trust_safety, inspector_general, legal_counsel]
```

## Demo

The MVP includes a Rich TUI dashboard processing seven scenarios in real time — from routine intelligence summarization (green) through missile defense (green, pre-authorized) and court-authorized surveillance (yellow, constrained with legal alert) to domestic surveillance and autonomous targeting (red, hard blocked with alerts).

```
┌─ Firebreak Policy Monitor ─────────────────────────────────────────┐
│  ┌─ Active Policy ───────────────────────────────────────────────┐  │
│  │  defense-standard v2.0                                        │  │
│  │  Signatories: AI Provider ✓  Deploying Org ✓                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌─ Evaluation History ──────────────────────────────────────────┐  │
│  │  TIME      DECISION           INTENT              RULE               AUDIT     │  │
│  │  10:42:01  ● ALLOW              summarization       allow-analysis       STANDARD  │  │
│  │  10:42:15  ● ALLOW              translation         allow-analysis       STANDARD  │  │
│  │  10:42:30  ● ALLOW              threat_assessment   allow-threat-assess  ENHANCED  │  │
│  │  10:43:01  ● ALLOW              missile_defense     allow-missile-def    ENHANCED  │  │
│  │  10:43:15  ● ALLOW_CONSTRAINED  warranted_surveil   allow-warranted      ENHANCED  │  │
│  │  10:43:22  ● BLOCK              bulk_surveillance   block-surv           CRITICAL  │  │
│  │  10:43:45  ● BLOCK              autonomous_target   block-auto-lethal    CRITICAL  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌─ Alerts ──────────────────────────────────────────────────────┐  │
│  │  ⚠ [10:43:22] CRITICAL: block-surveillance triggered          │  │
│  │    Notified: trust_safety, inspector_general                  │  │
│  │  ⚠ [10:43:45] CRITICAL: block-autonomous-lethal triggered     │  │
│  │    Notified: trust_safety, inspector_general, legal_counsel   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Quick Start

```bash
git clone https://github.com/ericmann/firebreak.git
cd firebreak
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run the demo (press Enter to advance between scenarios)
firebreak-demo

# Run with interactive proxy mode for live prompts
firebreak-demo --interactive
```

### CLI Options

```
firebreak-demo                  # Full demo, manual advance (press Enter)
firebreak-demo --auto           # Auto-advance with pauses for screen recording
firebreak-demo --fast           # Auto-advance with short pauses (for testing)
firebreak-demo --server         # Start OpenAI-compatible proxy server with live TUI
firebreak-demo --server --port 9000  # Custom port (default: 8080)
firebreak-demo --interactive    # Enter live proxy mode after canned scenarios
firebreak-demo --no-cache       # Force live API classification calls
firebreak-demo --policy PATH    # Custom policy file
firebreak-demo --scenarios PATH # Custom scenario file
```

> `--auto`, `--fast`, and `--server` are mutually exclusive. Default mode waits for Enter between scenarios.

### Server Mode

Start Firebreak as a persistent OpenAI-compatible proxy server:

```bash
firebreak-demo --server
```

The TUI dashboard runs in the foreground and updates live as requests arrive. The server listens on `http://localhost:8080/v1`.

**Point any OpenAI-compatible client at it:**

```bash
# curl
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "firebreak-proxy", "messages": [{"role": "user", "content": "Summarize the latest threat briefing"}]}'

# Python openai SDK
import openai
client = openai.OpenAI(base_url="http://localhost:8080/v1", api_key="unused")
client.chat.completions.create(model="firebreak-proxy", messages=[...])

# Cursor / other tools — set the base URL:
OPENAI_API_BASE=http://localhost:8080/v1
```

**Allowed requests** return a standard chat completion response. **Blocked requests** return an OpenAI-format error (HTTP 400, `code: "content_policy_violation"`) with the matched rule ID and description.

**Endpoints:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/v1/chat/completions` | POST | Proxy endpoint — classify, evaluate, forward or block |
| `/v1/models` | GET | List available models |
| `/health` | GET | Health check |

## Architecture

```mermaid
graph BT
    models[models.py<br/>Pure data structures]
    policy[policy.py<br/>YAML policy loader] --> models
    classifier[classifier.py<br/>Intent classification] --> models
    audit[audit.py<br/>Audit logging] --> models
    interceptor[interceptor.py<br/>Evaluation pipeline] --> policy
    interceptor --> classifier
    interceptor --> audit
    server[server.py<br/>OpenAI-compatible proxy] --> interceptor
    dashboard[dashboard.py<br/>Rich TUI dashboard] --> models
    demo[demo.py<br/>CLI entry point] --> interceptor
    demo --> dashboard
    demo --> server
```

**Key design decisions:**
- **Fail closed.** Unknown intents are blocked by default. Errors result in BLOCK, never ALLOW.
- **Policy lives in YAML, not code.** Python reads and evaluates — it does not define the rules.
- **Classification is cached.** Pre-cached results for demo reliability, live API via `--no-cache`.

## Production Vision

The hackathon MVP demonstrates the concept. In production:

| Layer | MVP | Production |
|-------|-----|------------|
| Policy engine | YAML matcher | [OPA](https://www.openpolicyagent.org/) + Rego |
| Deployment | In-process Python | Kubernetes sidecar proxy (Envoy filter) |
| Policy auth | Trust-based | Cryptographic dual-signatures |
| Inspection | Prompts only | Prompts + responses |
| Safety | Static rules | Circuit breaker + anomaly detection |
| Models | Claude only | Claude, GPT, Gemini, etc. |
| Audit | In-memory list | Hash-chained tamper-evident log |

## Why This Matters

The same pattern already exists: Kubernetes admission controllers evaluate API requests against policy at machine speed, at massive scale, every day. Firebreak applies that proven pattern to a new kind of API — one where the stakes include both national security and civil liberties.

The hard part isn't the technology. It's getting both sides to agree on the policy. Firebreak makes sure that once they do, the agreement holds.

## Author

Built by **Eric Mann** — engineer with experience in defense AI, secure infrastructure, and Kubernetes platform engineering.

## License

MIT

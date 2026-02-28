"""Demo runner — main entry point for the Firebreak demonstration."""

import argparse
import time

import yaml
from rich.console import Console
from rich.live import Live
from rich.text import Text

from firebreak.audit import AuditLog
from firebreak.classifier import ClassifierCache, IntentClassifier
from firebreak.dashboard import FirebreakDashboard
from firebreak.interceptor import FirebreakInterceptor
from firebreak.models import DemoScenario
from firebreak.policy import PolicyEngine

DEFAULT_POLICY = "policies/defense-standard.yaml"
DEFAULT_SCENARIOS = "demo/scenarios.yaml"
DEFAULT_CACHE = "demo/classifier_cache.json"

# Timing constants (seconds)
STEP_DELAY = 1.5
SCENARIO_DELAY = 3.0
FAST_STEP_DELAY = 0.25
FAST_SCENARIO_DELAY = 0.5
FINAL_HOLD = 10.0


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Firebreak — policy-as-code enforcement demo",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the classifier cache, make live API calls",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Reduce all pauses for faster demo",
    )
    parser.add_argument(
        "--policy",
        default=DEFAULT_POLICY,
        help=f"Path to policy YAML file (default: {DEFAULT_POLICY})",
    )
    parser.add_argument(
        "--scenarios",
        default=DEFAULT_SCENARIOS,
        help=f"Path to scenarios YAML file (default: {DEFAULT_SCENARIOS})",
    )
    parser.add_argument(
        "--cache",
        default=DEFAULT_CACHE,
        help=f"Path to classifier cache JSON (default: {DEFAULT_CACHE})",
    )
    return parser.parse_args()


def _load_scenarios(path: str) -> list[DemoScenario]:
    """Load demo scenarios from a YAML file.

    Args:
        path: Path to the scenarios YAML file.

    Returns:
        List of DemoScenario objects.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    scenarios = []
    for entry in data["scenarios"]:
        scenarios.append(
            DemoScenario(
                id=entry["id"],
                prompt=entry["prompt"].strip(),
                expected_category=entry["expected_category"],
                narration=entry["narration"],
            )
        )
    return scenarios


def main() -> None:
    """Run the Firebreak demo."""
    args = _parse_args()
    console = Console()

    step_delay = FAST_STEP_DELAY if args.fast else STEP_DELAY
    scenario_delay = FAST_SCENARIO_DELAY if args.fast else SCENARIO_DELAY

    # Load policy
    engine = PolicyEngine()
    engine.load(args.policy)
    policy = engine.policy

    # Initialize classifier
    cache = None
    if not args.no_cache:
        cache = ClassifierCache(cache_path=args.cache)
    classifier = IntentClassifier(
        categories=policy.categories,
        cache=cache,
    )

    # Initialize audit log and interceptor
    audit_log = AuditLog()
    interceptor = FirebreakInterceptor(
        policy_engine=engine,
        classifier=classifier,
        audit_log=audit_log,
    )

    # Initialize dashboard
    dashboard = FirebreakDashboard(policy)
    dashboard.register_callbacks(interceptor)

    # Load scenarios
    scenarios = _load_scenarios(args.scenarios)

    # Run the demo
    console.print()
    console.print(
        Text.from_markup(
            "[bold blue]FIREBREAK[/bold blue] — Policy-as-Code Enforcement Demo"
        )
    )
    console.print()
    time.sleep(step_delay)

    with Live(
        dashboard.render(),
        console=console,
        refresh_per_second=4,
        screen=True,
    ) as live:
        for i, scenario in enumerate(scenarios):
            # Show narration in the console above the live display
            live.console.print(
                Text.from_markup(
                    f"\n  [dim]Scenario {i + 1}/{len(scenarios)}:"
                    f" {scenario.narration}[/dim]"
                )
            )
            time.sleep(step_delay)

            # Update dashboard with the incoming prompt
            dashboard.update_prompt(scenario.prompt)
            live.update(dashboard.render())
            time.sleep(step_delay)

            # Run through the interceptor pipeline
            # (callbacks update dashboard state automatically)
            interceptor.evaluate_request(scenario.prompt)
            live.update(dashboard.render())

            # Pause between scenarios
            if i < len(scenarios) - 1:
                time.sleep(scenario_delay)
                dashboard.clear_current()
                live.update(dashboard.render())

        # Final hold
        time.sleep(FINAL_HOLD)


if __name__ == "__main__":
    main()

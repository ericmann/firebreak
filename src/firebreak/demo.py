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
FAST_STEP_DELAY = 0.25


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
        help="Auto-advance with short pauses (for testing)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enter interactive proxy mode after scenarios",
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


def _wait_or_auto(console: Console, fast: bool, message: str = "") -> None:
    """Wait for Enter keypress, or auto-advance in fast mode.

    Args:
        console: Rich console for output.
        fast: If True, skip waiting and auto-advance.
        message: Optional message to display before waiting.
    """
    if fast:
        time.sleep(FAST_STEP_DELAY)
    else:
        prompt = message if message else "  Press Enter to continue..."
        console.print(
            Text.from_markup(f"  [dim italic]{prompt}[/dim italic]"),
        )
        input()


def main() -> None:
    """Run the Firebreak demo."""
    args = _parse_args()
    console = Console()

    step_delay = FAST_STEP_DELAY if args.fast else STEP_DELAY

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

    with Live(
        dashboard.render(),
        console=console,
        refresh_per_second=4,
    ) as live:
        for i, scenario in enumerate(scenarios):
            # Pause for presenter to narrate
            live.stop()
            console.print()
            console.print(
                Text.from_markup(
                    f"  [bold]Scenario {i + 1}/{len(scenarios)}:[/bold]"
                    f" {scenario.narration}"
                )
            )
            _wait_or_auto(console, args.fast, "Press Enter to run scenario...")
            live.start()

            # Show prompt on dashboard
            dashboard.update_prompt(scenario.prompt)
            live.update(dashboard.render())
            time.sleep(step_delay)

            # Run through the interceptor pipeline
            interceptor.evaluate_request(scenario.prompt)
            live.update(dashboard.render())

        # Interactive proxy mode
        if args.interactive:
            live.stop()
            console.print()
            console.print(
                Text.from_markup(
                    "\n  [bold blue]INTERACTIVE MODE[/bold blue]"
                    " — Type a prompt to evaluate through the policy proxy."
                    "\n  [dim]Type 'quit' or 'exit' to end.[/dim]\n"
                )
            )
            live.start()

            while True:
                live.stop()
                try:
                    prompt = input("  > ")
                except (EOFError, KeyboardInterrupt):
                    break

                if prompt.strip().lower() in ("quit", "exit", "q"):
                    break

                if not prompt.strip():
                    live.start()
                    continue

                live.start()

                # Clear previous and show new prompt
                dashboard.clear_current()
                dashboard.update_prompt(prompt.strip())
                live.update(dashboard.render())
                time.sleep(step_delay)

                # Run through the full pipeline (live classification + policy + LLM)
                interceptor.evaluate_request(prompt.strip())
                live.update(dashboard.render())

        # Wait for presenter to exit
        live.stop()
        console.print()
        _wait_or_auto(console, args.fast, "Press Enter to exit...")


if __name__ == "__main__":
    main()

"""Demo runner — main entry point for the Firebreak demonstration."""

import argparse
import threading
import time

import yaml
from rich.console import Console
from rich.live import Live

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
AUTO_STEP_DELAY = 2.0
AUTO_NARRATION_DELAY = 3.0


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
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fast",
        action="store_true",
        help="Auto-advance with short pauses (for testing)",
    )
    mode_group.add_argument(
        "--auto",
        action="store_true",
        help="Auto-advance with pauses for screen recording",
    )
    mode_group.add_argument(
        "--server",
        action="store_true",
        help="Start as an OpenAI-compatible proxy server with live TUI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server listen port (default: 8080)",
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


def _wait_or_auto(
    dashboard: FirebreakDashboard,
    live: Live,
    *,
    fast: bool,
    auto: bool,
) -> None:
    """Wait for Enter keypress, or auto-advance in fast/auto mode.

    Args:
        dashboard: Dashboard instance (for narration updates).
        live: The Rich Live display.
        fast: If True, auto-advance with short pauses.
        auto: If True, auto-advance with screen-recording pauses.
    """
    if fast:
        time.sleep(FAST_STEP_DELAY)
    elif auto:
        time.sleep(AUTO_NARRATION_DELAY)
    else:
        prompt_text = "[dim italic]Press Enter to continue...[/dim italic]"
        dashboard.update_narration(prompt_text)
        live.update(dashboard)
        live.stop()
        input()
        live.start()


def _run_server(
    args: argparse.Namespace,
    console: Console,
    interceptor: FirebreakInterceptor,
    dashboard: FirebreakDashboard,
) -> None:
    """Start the proxy server with a live TUI dashboard.

    Args:
        args: Parsed CLI arguments (needs .port).
        console: Rich console for output.
        interceptor: The configured interceptor pipeline.
        dashboard: The dashboard instance.
    """
    import uvicorn

    from firebreak.server import create_app

    with Live(
        dashboard,
        console=console,
        refresh_per_second=4,
    ) as live:
        app = create_app(interceptor, dashboard, live)

        dashboard.update_narration(
            f"[bold green]Server listening on"
            f" http://localhost:{args.port}[/bold green]"
            f" — Ctrl+C to stop"
        )
        live.update(dashboard)

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=args.port,
                log_level="warning",
            )
        )

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        try:
            while thread.is_alive():
                time.sleep(0.25)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(timeout=5)


def main() -> None:
    """Run the Firebreak demo."""
    args = _parse_args()
    console = Console()

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

    # Server mode — start HTTP proxy and show live TUI
    if args.server:
        _run_server(args, console, interceptor, dashboard)
        return

    # Demo mode — step delay selection
    if args.fast:
        step_delay = FAST_STEP_DELAY
    elif args.auto:
        step_delay = AUTO_STEP_DELAY
    else:
        step_delay = STEP_DELAY

    # Load scenarios
    scenarios = _load_scenarios(args.scenarios)

    # Run the demo
    with Live(
        dashboard,
        console=console,
        refresh_per_second=4,
    ) as live:
        for i, scenario in enumerate(scenarios):
            # Show narration in the dashboard status bar
            dashboard.update_narration(
                f"[bold]Scenario {i + 1}/{len(scenarios)}:[/bold] {scenario.narration}"
            )
            live.update(dashboard)
            _wait_or_auto(dashboard, live, fast=args.fast, auto=args.auto)

            # Show prompt on dashboard
            dashboard.update_narration(None)
            dashboard.update_prompt(scenario.prompt)
            live.update(dashboard)
            time.sleep(step_delay)

            # Run through the interceptor pipeline
            interceptor.evaluate_request(scenario.prompt)
            live.update(dashboard)

        # Interactive proxy mode
        if args.interactive:
            dashboard.update_narration(
                "[bold blue]INTERACTIVE MODE[/bold blue]"
                " — Type a prompt to evaluate. Type 'quit' to end."
            )
            live.update(dashboard)

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
                live.update(dashboard)
                time.sleep(step_delay)

                # Run through the full pipeline
                interceptor.evaluate_request(prompt.strip())
                live.update(dashboard)

        # Wait for presenter to exit
        dashboard.update_narration(
            "[dim italic]Demo complete. Press Enter to exit...[/dim italic]"
        )
        live.update(dashboard)
        _wait_or_auto(dashboard, live, fast=args.fast, auto=args.auto)


if __name__ == "__main__":
    main()

"""Rich TUI dashboard for real-time policy evaluation display."""

from datetime import datetime

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from firebreak.interceptor import FirebreakInterceptor
from firebreak.models import (
    ClassificationResult,
    Decision,
    EvaluationResult,
    Policy,
)

DECISION_COLORS = {
    Decision.ALLOW: "green",
    Decision.ALLOW_CONSTRAINED: "yellow",
    Decision.BLOCK: "bold red",
}

DECISION_DOTS = {
    Decision.ALLOW: "[green]\u25cf[/green]",
    Decision.ALLOW_CONSTRAINED: "[yellow]\u25cf[/yellow]",
    Decision.BLOCK: "[red]\u25cf[/red]",
}


class FirebreakDashboard:
    """Five-panel TUI dashboard for policy evaluation display.

    Panels:
    1. Policy info (top) — active policy metadata
    2. Current request (middle-top) — prompt, classification, decision
    3. Evaluation history (middle-bottom) — table of all evaluations
    4. Alerts (bottom) — critical alert notifications
    5. Narration (footer) — scenario narration status bar

    Attributes:
        policy: The active deployment policy.
        evaluation_history: List of completed evaluations.
        alerts: List of alert event dicts.
        current_prompt: The prompt currently being evaluated.
        current_classification: Classification of current prompt.
        current_evaluation: Evaluation of current prompt.
        narration: Current narration text for the status bar.
    """

    def __init__(self, policy: Policy) -> None:
        """Initialize the dashboard with a loaded policy.

        Args:
            policy: The active Policy to display.
        """
        self.policy = policy
        self.evaluation_history: list[EvaluationResult] = []
        self.alerts: list[dict] = []
        self.current_prompt: str | None = None
        self.current_classification: ClassificationResult | None = None
        self.current_evaluation: EvaluationResult | None = None
        self.narration: str | None = None
        self._frame: int = 0

    def register_callbacks(self, interceptor: FirebreakInterceptor) -> None:
        """Subscribe to interceptor events for live updates.

        Args:
            interceptor: The FirebreakInterceptor to subscribe to.
        """
        interceptor.on("prompt_received", self.update_prompt)
        interceptor.on("classified", self.update_classification)
        interceptor.on("evaluated", self.update_evaluation)
        interceptor.on("alert", self._add_alert)

    def update_prompt(self, prompt: str) -> None:
        """Set the current prompt and clear prior state.

        Args:
            prompt: The new prompt text being evaluated.
        """
        for alert in self.alerts:
            alert["aged"] = True
        self.current_prompt = prompt
        self.current_classification = None
        self.current_evaluation = None

    def update_classification(self, result: ClassificationResult) -> None:
        """Set the current classification result.

        Args:
            result: The ClassificationResult for the current prompt.
        """
        self.current_classification = result

    def update_evaluation(self, result: EvaluationResult) -> None:
        """Set the current evaluation and add to history.

        Args:
            result: The EvaluationResult for the current prompt.
        """
        self.current_evaluation = result
        self.evaluation_history.append(result)

    def _add_alert(self, alert_data: dict) -> None:
        """Add an alert to the alerts panel.

        Args:
            alert_data: Dict with "target" and "evaluation" keys.
        """
        self.alerts.append(
            {
                "timestamp": datetime.now(),
                "target": alert_data["target"],
                "evaluation": alert_data["evaluation"],
                "aged": False,
            }
        )

    def clear_current(self) -> None:
        """Reset the current request panel for the next scenario."""
        self.current_prompt = None
        self.current_classification = None
        self.current_evaluation = None

    def update_narration(self, text: str | None) -> None:
        """Set the narration text shown in the status bar.

        Args:
            text: Narration text, or None to clear.
        """
        self.narration = text

    def _dots(self) -> str:
        """Return an animated ellipsis that cycles across render frames."""
        return "." * ((self._frame % 3) + 1)

    def __rich__(self) -> Layout:
        """Allow Rich to use this object directly as a renderable."""
        return self.render()

    def render(self) -> Layout:
        """Build and return the full dashboard layout.

        Returns:
            A rich Layout with five panels.
        """
        self._frame += 1
        layout = Layout()
        layout.split_column(
            Layout(name="policy", size=3),
            Layout(name="request", size=7),
            Layout(name="history", ratio=1),
            Layout(name="alerts", size=4),
            Layout(name="narration", size=3),
        )

        layout["policy"].update(self._render_policy_panel())
        layout["request"].update(self._render_request_panel())
        layout["history"].update(self._render_history_panel())
        layout["alerts"].update(self._render_alerts_panel())
        layout["narration"].update(self._render_narration_panel())

        return layout

    def _render_policy_panel(self) -> Panel:
        """Render the active policy info panel."""
        p = self.policy
        sigs = " ".join(f"{v} [green]\u2713[/green]" for v in p.signatories.values())
        text = Text.from_markup(
            f"  [bold]{p.name}[/bold] v{p.version}"
            f"    Signatories: {sigs}"
            f"    Rules: {len(p.rules)} active"
            f" | Effective: {p.effective}"
        )
        return Panel(
            text,
            title="[bold]Active Policy[/bold]",
            border_style="blue",
        )

    def _render_request_panel(self) -> Panel:
        """Render the current request evaluation panel."""
        parts: list[str] = []

        if self.current_prompt:
            parts.append(f"  > {self.current_prompt.strip()}")
        else:
            parts.append("  [dim]Waiting for next request...[/dim]")

        if self.current_classification:
            c = self.current_classification
            parts.append("")
            parts.append(
                f"  Intent: [bold]{c.intent_category}[/bold]"
                f"          Confidence: {c.confidence:.2f}"
            )
        elif self.current_prompt:
            parts.append("")
            dots = self._dots()
            parts.append(f"  [dim italic]Classifying{dots}[/dim italic]")

        if self.current_evaluation:
            e = self.current_evaluation
            color = DECISION_COLORS.get(e.decision, "white")
            parts.append(
                f"  Rule:   [bold]{e.matched_rule_id}[/bold]"
                f"           Decision:   [{color}]"
                f"{e.decision.value}[/{color}]"
            )
            if e.note:
                parts.append(f"  [dim italic]{e.note}[/dim italic]")
        elif self.current_classification:
            dots = self._dots()
            parts.append(f"  [dim italic]Evaluating{dots}[/dim italic]")

        content = Text.from_markup("\n".join(parts))
        return Panel(
            content,
            title="[bold]Incoming Request[/bold]",
            border_style="cyan",
        )

    def _render_history_panel(self) -> Panel:
        """Render the evaluation history table."""
        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            padding=(0, 1),
        )
        table.add_column("TIME", width=10)
        table.add_column("DECISION", width=18)
        table.add_column("INTENT", width=22)
        table.add_column("RULE", width=24)
        table.add_column("AUDIT", width=10)

        for ev in self.evaluation_history:
            ts = ev.classification.timestamp.strftime("%H:%M:%S")
            dot = DECISION_DOTS.get(ev.decision, "\u25cf")
            color = DECISION_COLORS.get(ev.decision, "white")
            table.add_row(
                ts,
                Text.from_markup(f"{dot} [{color}]{ev.decision.value}[/{color}]"),
                ev.classification.intent_category,
                ev.matched_rule_id,
                ev.audit_level.value.upper(),
            )

        return Panel(
            table,
            title="[bold]Evaluation History[/bold]",
            border_style="blue",
        )

    def _render_alerts_panel(self) -> Panel:
        """Render the alerts panel."""
        if not self.alerts:
            content = Text.from_markup("  [dim]No alerts.[/dim]")
            return Panel(
                content,
                title="[bold]Alerts[/bold]",
                border_style="dim",
            )

        parts: list[str] = []
        for alert in self.alerts:
            ts = alert["timestamp"].strftime("%H:%M:%S")
            ev = alert["evaluation"]
            target = alert["target"]
            if alert.get("aged"):
                parts.append(
                    f"  [dim]\u26a0 [{ts}] CRITICAL:"
                    f" {ev.matched_rule_id} triggered"
                    f"  \u2192 {target}[/dim]"
                )
            else:
                parts.append(
                    f"  [red]\u26a0[/red] [{ts}] CRITICAL:"
                    f" {ev.matched_rule_id} triggered"
                    f"  \u2192 {target}"
                )

        content = Text.from_markup("\n".join(parts))
        return Panel(
            content,
            title="[bold red]Alerts[/bold red]",
            border_style="red",
        )

    def _render_narration_panel(self) -> Panel:
        """Render the narration status bar."""
        if self.narration:
            content = Text.from_markup(f"  {self.narration}")
        else:
            content = Text.from_markup("  [dim]Ready.[/dim]")
        return Panel(
            content,
            title="[bold]Status[/bold]",
            border_style="dim",
        )

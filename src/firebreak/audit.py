"""Append-only audit log for policy evaluation records."""

from firebreak.models import AuditEntry, ClassificationResult, EvaluationResult


class AuditLog:
    """Append-only log of policy evaluation audit entries.

    Attributes:
        entries: The ordered list of audit entries.
    """

    def __init__(self) -> None:
        """Initialize an empty audit log."""
        self.entries: list[AuditEntry] = []

    def log(
        self,
        prompt: str,
        classification: ClassificationResult,
        evaluation: EvaluationResult,
    ) -> AuditEntry:
        """Create and append an audit entry.

        Args:
            prompt: The original prompt text.
            classification: The intent classification result.
            evaluation: The policy evaluation result.

        Returns:
            The newly created AuditEntry.
        """
        entry = AuditEntry(
            prompt_text=prompt,
            classification=classification,
            evaluation=evaluation,
        )
        self.entries.append(entry)
        return entry

    def get_entries(self) -> list[AuditEntry]:
        """Return all audit entries.

        Returns:
            The full list of audit entries in chronological order.
        """
        return list(self.entries)

    def get_alerts(self) -> list[AuditEntry]:
        """Return only audit entries that triggered alerts.

        Returns:
            Entries where the evaluation result has non-empty alerts.
        """
        return [e for e in self.entries if e.evaluation.alerts]

"""Policy engine for loading and evaluating YAML-based deployment policies."""

from pathlib import Path

import yaml

from firebreak.models import (
    AuditLevel,
    ClassificationResult,
    Decision,
    EvaluationResult,
    Policy,
    PolicyRule,
)


class PolicyEngine:
    """Loads YAML policy files and evaluates intent categories against rules.

    Attributes:
        policy: The loaded Policy object, or None if not yet loaded.
    """

    def __init__(self) -> None:
        """Initialize the PolicyEngine with no policy loaded."""
        self.policy: Policy | None = None

    def load(self, path: str) -> Policy:
        """Parse a YAML policy file, validate structure, and store it.

        Args:
            path: Filesystem path to the YAML policy file.

        Returns:
            The parsed and validated Policy object.

        Raises:
            ValueError: If the YAML is missing required fields such as
                policy.name, policy.version, or rules with id/decision/
                match_categories.
        """
        file_path = Path(path)
        with open(file_path) as f:
            data = yaml.safe_load(f)

        # Validate top-level policy section
        if not isinstance(data, dict) or "policy" not in data:
            raise ValueError("YAML must contain a top-level 'policy' section")

        policy_data = data["policy"]
        if not isinstance(policy_data, dict):
            raise ValueError("'policy' section must be a mapping")

        if "name" not in policy_data:
            raise ValueError("Policy is missing required field: policy.name")
        if "version" not in policy_data:
            raise ValueError("Policy is missing required field: policy.version")

        # Validate rules section
        if "rules" not in data:
            raise ValueError("YAML must contain a top-level 'rules' section")

        raw_rules = data["rules"]
        if not isinstance(raw_rules, list) or len(raw_rules) == 0:
            raise ValueError("'rules' must be a non-empty list")

        # Build PolicyRule objects
        rules: list[PolicyRule] = []
        for i, raw_rule in enumerate(raw_rules):
            if not isinstance(raw_rule, dict):
                raise ValueError(f"Rule at index {i} must be a mapping")
            if "id" not in raw_rule:
                raise ValueError(f"Rule at index {i} is missing required field: id")
            if "decision" not in raw_rule:
                raise ValueError(
                    f"Rule '{raw_rule.get('id', i)}' is missing required field: "
                    "decision"
                )
            if "match_categories" not in raw_rule:
                raise ValueError(
                    f"Rule '{raw_rule['id']}' is missing required field: "
                    "match_categories"
                )

            rule = PolicyRule(
                id=raw_rule["id"],
                description=raw_rule.get("description", ""),
                match_categories=raw_rule["match_categories"],
                decision=Decision(raw_rule["decision"]),
                audit=AuditLevel(raw_rule.get("audit", "standard")),
                requires_human=raw_rule.get("requires_human", False),
                constraints=raw_rule.get("constraints", []),
                alerts=raw_rule.get("alerts", []),
                color=raw_rule.get("color", "green"),
                note=raw_rule.get("note", ""),
            )
            rules.append(rule)

        # Build categories list
        categories: list[str] = data.get("categories", [])

        # Build signatories
        signatories: dict[str, str] = policy_data.get("signatories", {})

        policy = Policy(
            name=policy_data["name"],
            version=str(policy_data["version"]),
            effective=str(policy_data.get("effective", "")),
            signatories=signatories,
            rules=rules,
            categories=categories,
        )

        self.policy = policy
        return policy

    def evaluate(
        self,
        intent_category: str,
        classification: ClassificationResult,
        metadata: dict | None = None,
    ) -> EvaluationResult:
        """Evaluate an intent category against the loaded policy rules.

        Iterates rules in order and returns the first match. If no rule
        matches, returns a BLOCK decision with "unknown-intent" rule_id.

        Args:
            intent_category: The classified intent category to evaluate.
            classification: The ClassificationResult that produced this
                intent category.
            metadata: Optional metadata dict (reserved for future use).

        Returns:
            An EvaluationResult describing the policy decision.

        Raises:
            RuntimeError: If no policy has been loaded yet.
        """
        if self.policy is None:
            raise RuntimeError("No policy loaded. Call load() first.")

        for rule in self.policy.rules:
            if intent_category in rule.match_categories:
                return EvaluationResult(
                    decision=rule.decision,
                    matched_rule_id=rule.id,
                    rule_description=rule.description,
                    audit_level=rule.audit,
                    alerts=list(rule.alerts),
                    constraints=list(rule.constraints),
                    color=rule.color,
                    note=rule.note,
                    classification=classification,
                )

        # No rule matched — default to BLOCK
        return EvaluationResult(
            decision=Decision.BLOCK,
            matched_rule_id="unknown-intent",
            rule_description="No matching rule for intent category",
            audit_level=AuditLevel.CRITICAL,
            alerts=["trust_safety"],
            constraints=[],
            color="red",
            note="",
            classification=classification,
        )

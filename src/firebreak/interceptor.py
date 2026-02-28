"""Request interceptor — orchestrates classification, evaluation, and response."""

from collections import defaultdict
from typing import Any, Callable

import anthropic

from firebreak.audit import AuditLog
from firebreak.classifier import IntentClassifier
from firebreak.models import Decision, EvaluationResult
from firebreak.policy import PolicyEngine


class FirebreakInterceptor:
    """Orchestrates the full prompt evaluation pipeline.

    Classifies prompts, evaluates them against policy, calls the LLM
    for allowed requests, and emits events for dashboard consumption.

    Attributes:
        policy_engine: The loaded policy engine.
        classifier: The intent classifier.
        audit_log: The audit log.
        llm_model: Model ID for LLM calls on allowed requests.
        callbacks: Registered event callbacks.
    """

    def __init__(
        self,
        policy_engine: PolicyEngine,
        classifier: IntentClassifier,
        audit_log: AuditLog,
        llm_model: str = "claude-sonnet-4-6",
    ) -> None:
        """Initialize the interceptor.

        Args:
            policy_engine: A PolicyEngine with a policy loaded.
            classifier: An IntentClassifier for prompt classification.
            audit_log: An AuditLog for recording evaluations.
            llm_model: Anthropic model ID for allowed LLM calls.
        """
        self.policy_engine = policy_engine
        self.classifier = classifier
        self.audit_log = audit_log
        self.llm_model = llm_model
        self.callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._client = anthropic.Anthropic()

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an event.

        Args:
            event: Event name (e.g. "prompt_received", "classified").
            callback: Function to call when the event fires.
        """
        self.callbacks[event].append(callback)

    def _emit(self, event: str, data: Any) -> None:
        """Fire all callbacks registered for an event.

        Args:
            event: Event name.
            data: Data to pass to each callback.
        """
        for callback in self.callbacks.get(event, []):
            callback(data)

    def evaluate_request(
        self, prompt: str, metadata: dict | None = None
    ) -> EvaluationResult:
        """Run a prompt through the full evaluation pipeline.

        Steps:
        1. Emit prompt_received
        2. Classify intent
        3. Emit classified
        4. Evaluate against policy
        5. Emit evaluated
        6. If allowed: call LLM, attach response, emit response
        7. If blocked: emit blocked + alert events
        8. Log to audit trail
        9. Return result

        Args:
            prompt: The user prompt to evaluate.
            metadata: Optional metadata dict.

        Returns:
            The EvaluationResult from the policy engine.
        """
        # 1. Prompt received
        self._emit("prompt_received", prompt)

        # 2. Classify
        classification = self.classifier.classify(prompt)

        # 3. Emit classification
        self._emit("classified", classification)

        # 4. Evaluate against policy
        evaluation = self.policy_engine.evaluate(
            classification.intent_category, classification, metadata
        )

        # 5. Emit evaluation
        self._emit("evaluated", evaluation)

        # 6/7. Handle decision
        if evaluation.decision in (Decision.ALLOW, Decision.ALLOW_CONSTRAINED):
            try:
                response = self._client.messages.create(
                    model=self.llm_model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                evaluation.llm_response = response.content[0].text
            except Exception:
                evaluation.llm_response = "[LLM call failed]"
            self._emit("response", evaluation)
        else:
            self._emit("blocked", evaluation)

        # Emit alerts for any decision that has them
        for target in evaluation.alerts:
            self._emit("alert", {"target": target, "evaluation": evaluation})

        # 8. Log to audit
        self.audit_log.log(prompt, classification, evaluation)

        # 9. Return
        return evaluation

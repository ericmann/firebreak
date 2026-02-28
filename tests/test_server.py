"""Tests for the OpenAI-compatible proxy server."""

from unittest.mock import MagicMock

from starlette.testclient import TestClient

from firebreak.models import (
    AuditLevel,
    ClassificationResult,
    Decision,
    EvaluationResult,
)
from firebreak.server import create_app


def _make_evaluation(
    decision: Decision,
    rule_id: str = "test-rule",
    llm_response: str | None = None,
    constraints: list[str] | None = None,
) -> EvaluationResult:
    """Build a minimal EvaluationResult for testing."""
    return EvaluationResult(
        decision=decision,
        matched_rule_id=rule_id,
        rule_description="Test rule description",
        audit_level=AuditLevel.STANDARD,
        alerts=[],
        constraints=constraints or [],
        color="green",
        note="",
        classification=ClassificationResult(
            intent_category="summarization",
            confidence=0.95,
            raw_prompt="test prompt",
        ),
        llm_response=llm_response,
    )


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        interceptor = MagicMock()
        app = create_app(interceptor)
        client = TestClient(app)

        resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestModelsEndpoint:
    def test_list_models(self):
        interceptor = MagicMock()
        app = create_app(interceptor)
        client = TestClient(app)

        resp = client.get("/v1/models")

        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "firebreak-proxy"


class TestChatCompletions:
    def test_allow_returns_200_with_response(self):
        interceptor = MagicMock()
        interceptor.evaluate_request.return_value = _make_evaluation(
            Decision.ALLOW, llm_response="Hello, world!"
        )
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "firebreak-proxy",
                "messages": [{"role": "user", "content": "Summarize this"}],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "firebreak-proxy"
        assert data["choices"][0]["message"]["content"] == "Hello, world!"
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_allow_constrained_returns_200(self):
        interceptor = MagicMock()
        interceptor.evaluate_request.return_value = _make_evaluation(
            Decision.ALLOW_CONSTRAINED,
            rule_id="allow-warranted",
            llm_response="Constrained response",
            constraints=["Warrant required"],
        )
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "firebreak-proxy",
                "messages": [{"role": "user", "content": "Analyze target"}],
            },
        )

        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert content == "Constrained response"

    def test_block_returns_400_with_error(self):
        interceptor = MagicMock()
        interceptor.evaluate_request.return_value = _make_evaluation(
            Decision.BLOCK, rule_id="block-surveillance"
        )
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "firebreak-proxy",
                "messages": [{"role": "user", "content": "Track citizens"}],
            },
        )

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["type"] == "policy_violation"
        assert error["code"] == "content_policy_violation"
        assert "block-surveillance" in error["message"]

    def test_missing_messages_returns_400(self):
        interceptor = MagicMock()
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={"model": "firebreak-proxy"},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_request"
        interceptor.evaluate_request.assert_not_called()

    def test_empty_messages_returns_400(self):
        interceptor = MagicMock()
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={"model": "firebreak-proxy", "messages": []},
        )

        assert resp.status_code == 400
        interceptor.evaluate_request.assert_not_called()

    def test_no_user_message_returns_400(self):
        interceptor = MagicMock()
        client = TestClient(create_app(interceptor))

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "firebreak-proxy",
                "messages": [{"role": "system", "content": "You are helpful"}],
            },
        )

        assert resp.status_code == 400
        assert "No user message" in resp.json()["error"]["message"]
        interceptor.evaluate_request.assert_not_called()

    def test_extracts_last_user_message(self):
        interceptor = MagicMock()
        interceptor.evaluate_request.return_value = _make_evaluation(
            Decision.ALLOW, llm_response="OK"
        )
        client = TestClient(create_app(interceptor))

        client.post(
            "/v1/chat/completions",
            json={
                "model": "firebreak-proxy",
                "messages": [
                    {"role": "user", "content": "First message"},
                    {"role": "assistant", "content": "Response"},
                    {"role": "user", "content": "Second message"},
                ],
            },
        )

        interceptor.evaluate_request.assert_called_once_with("Second message")

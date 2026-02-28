"""OpenAI-compatible proxy server for Firebreak policy enforcement."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from firebreak.interceptor import FirebreakInterceptor
from firebreak.models import Decision

if TYPE_CHECKING:
    from rich.live import Live

    from firebreak.dashboard import FirebreakDashboard


def create_app(
    interceptor: FirebreakInterceptor,
    dashboard: FirebreakDashboard | None = None,
    live: Live | None = None,
) -> Starlette:
    """Create the Starlette ASGI application.

    Args:
        interceptor: The FirebreakInterceptor pipeline.
        dashboard: Optional dashboard for live TUI updates.
        live: Optional Rich Live display to refresh after requests.

    Returns:
        A configured Starlette application.
    """

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def list_models(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "object": "list",
                "data": [
                    {
                        "id": "firebreak-proxy",
                        "object": "model",
                        "created": 0,
                        "owned_by": "firebreak",
                    }
                ],
            }
        )

    async def chat_completions(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {
                    "error": {
                        "message": "Invalid JSON in request body",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_json",
                    }
                },
                status_code=400,
            )

        messages = body.get("messages")
        if not messages or not isinstance(messages, list):
            return JSONResponse(
                {
                    "error": {
                        "message": "Missing or empty 'messages' array",
                        "type": "invalid_request_error",
                        "param": "messages",
                        "code": "invalid_request",
                    }
                },
                status_code=400,
            )

        # Extract the last user message as the prompt
        prompt = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = msg.get("content", "")
                break

        if not prompt:
            return JSONResponse(
                {
                    "error": {
                        "message": "No user message found in 'messages'",
                        "type": "invalid_request_error",
                        "param": "messages",
                        "code": "invalid_request",
                    }
                },
                status_code=400,
            )

        # Run through the interceptor pipeline
        evaluation = interceptor.evaluate_request(prompt)

        # Refresh the TUI if connected
        if dashboard and live:
            live.update(dashboard)

        if evaluation.decision == Decision.BLOCK:
            return JSONResponse(
                {
                    "error": {
                        "message": (
                            f"Request blocked by policy:"
                            f" {evaluation.matched_rule_id}"
                            f" \u2014 {evaluation.rule_description}"
                        ),
                        "type": "policy_violation",
                        "param": None,
                        "code": "content_policy_violation",
                    }
                },
                status_code=400,
            )

        # ALLOW or ALLOW_CONSTRAINED
        content = evaluation.llm_response or ""
        return JSONResponse(
            {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "firebreak-proxy",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/v1/models", list_models, methods=["GET"]),
            Route(
                "/v1/chat/completions",
                chat_completions,
                methods=["POST"],
            ),
        ],
    )

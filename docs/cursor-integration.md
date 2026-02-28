# Firebreak + Cursor Integration Guide

Connect Cursor IDE to your local Firebreak proxy so every AI request flows through policy enforcement with a live TUI dashboard.

## Prerequisites

- Firebreak installed (`pip install -e .`) with an `ANTHROPIC_API_KEY` set
- [ngrok](https://ngrok.com/) installed and authenticated
- Cursor IDE

## 1. Test Locally with curl

Start the server:

```bash
firebreak-demo --server
```

The TUI dashboard appears. The status bar shows `Server listening on http://localhost:8080`.

In another terminal, send an **allowed** request:

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "firebreak-proxy",
    "messages": [{"role": "user", "content": "Summarize the latest CENTCOM threat briefing"}]
  }' | python3 -m json.tool
```

Expected: HTTP 200 with an OpenAI-format chat completion response. The TUI dashboard updates with the evaluation.

Now send a **blocked** request:

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "firebreak-proxy",
    "messages": [{"role": "user", "content": "Run pattern-of-life analysis on all residents of zip code 90210"}]
  }' | python3 -m json.tool
```

Expected: HTTP 400 with an OpenAI error response:

```json
{
  "error": {
    "message": "Request blocked by policy: block-surveillance — Mass domestic surveillance — hard block",
    "type": "policy_violation",
    "param": null,
    "code": "content_policy_violation"
  }
}
```

Verify the health endpoint:

```bash
curl -s http://localhost:8080/health
# {"status":"ok"}
```

## 2. Expose via ngrok

Cursor can't reach `localhost` directly. Use ngrok to create a public HTTPS tunnel.

### Install ngrok

```bash
# macOS
brew install ngrok/ngrok/ngrok

# Linux
sudo snap install ngrok

# Or download from https://ngrok.com/download
```

### Authenticate (one-time)

Sign up at https://ngrok.com, grab your auth token from the dashboard, then:

```bash
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### Start the tunnel

With Firebreak already running on port 8080:

```bash
ngrok http 8080
```

ngrok shows output like:

```
Forwarding  https://a1b2c3d4.ngrok-free.app -> http://localhost:8080
```

Copy the `https://...ngrok-free.app` URL. This is your public endpoint.

### Verify the tunnel

```bash
curl -s https://a1b2c3d4.ngrok-free.app/health
# {"status":"ok"}
```

> **Tip:** ngrok provides a local inspection UI at http://127.0.0.1:4040 where you can see all requests flowing through the tunnel, inspect headers/bodies, and replay requests for debugging.

## 3. Configure Cursor

1. Open Cursor Settings: **Cmd+,** (macOS) or **Ctrl+,** (Windows/Linux)
2. Click **"Models"** in the sidebar
3. Under **OpenAI API Key**, enter any non-empty string (e.g., `unused`) — Firebreak doesn't check this, but Cursor requires it
4. Toggle on **"Override OpenAI Base URL"**
5. Set the base URL to your ngrok tunnel **with `/v1` appended**:
   ```
   https://a1b2c3d4.ngrok-free.app/v1
   ```
6. Add a custom model named `firebreak-proxy`
7. Deselect all other models to prevent Cursor from routing requests to the wrong endpoint

### Verify in Cursor

Open a chat window in Cursor and select the `firebreak-proxy` model. Type a prompt. You should see:

- The request appear in the Firebreak TUI dashboard
- Classification and policy evaluation update live
- The response flow back to Cursor's chat window

For a blocked request, Cursor will display an error — this is expected. The Firebreak TUI will show the BLOCK decision and any alerts that fired.

## Architecture

```
Cursor IDE
    ↓ HTTPS
ngrok tunnel (a1b2c3d4.ngrok-free.app)
    ↓ HTTP
Firebreak proxy (localhost:8080)
    ↓
Interceptor pipeline (classify → evaluate → allow/block)
    ↓ (if allowed)
Claude API (api.anthropic.com)
    ↓
Response flows back up the chain
```

## Troubleshooting

**Cursor shows "model not found" or validation errors:**
Deselect all built-in models. Cursor may try to validate them against your overridden base URL, which fails since Firebreak only knows about `firebreak-proxy`.

**ngrok tunnel expires:**
Free ngrok accounts have session time limits. Restart `ngrok http 8080` and update the base URL in Cursor settings.

**Requests hang or timeout:**
Check that Firebreak is running (`curl localhost:8080/health`). Check that `ANTHROPIC_API_KEY` is set — allowed requests need to reach the Claude API.

**Want to skip ngrok for local-only testing:**
If you're just testing with curl or a Python script, skip ngrok entirely and use `http://localhost:8080/v1` directly.

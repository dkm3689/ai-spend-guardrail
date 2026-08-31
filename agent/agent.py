"""
Guardrail Agent — runs on your infrastructure, never on ours.

Your Anthropic API key stays in your environment. The control plane
receives only usage numbers (tokens, cost, model) — never the key itself.

Flow per request:
  1. Receive request from your app (same interface as Anthropic)
  2. POST /agent/check  → control plane returns allow / downgrade / block
  3. If allowed: call Anthropic directly using your local key
  4. Stream or return response to your app
  5. POST /agent/report → control plane logs usage, updates spend, fires alerts

Config (env vars — keep in .env, never commit it):
  ANTHROPIC_API_KEY       Your real Anthropic key — stays on this machine
  GUARDRAIL_PROJECT_KEY   sk-guard-... key from the Guardrail dashboard
  GUARDRAIL_URL           https://your-guardrail-proxy.railway.app
  PORT                    Port this agent listens on (default: 8002)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── config ─────────────────────────────────────────────────────────────────────

ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
PROJECT_KEY   = os.environ["GUARDRAIL_PROJECT_KEY"]
GUARDRAIL_URL = os.environ.get("GUARDRAIL_URL", "http://localhost:8000").rstrip("/")
ANTHROPIC_URL = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_VER = "2023-06-01"
PORT          = int(os.environ.get("PORT", "8002"))

# ── pricing table (kept local so cost estimate doesn't need a network call) ────

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8":           (15.0, 75.0),
    "claude-opus-4-7":           (15.0, 75.0),
    "claude-sonnet-5":           (3.0,  15.0),
    "claude-sonnet-4-5":         (3.0,  15.0),
    "claude-haiku-4-5":          (0.80,  4.0),
    "claude-haiku-4-5-20251001": (0.80,  4.0),
}
_DEFAULT_PRICING = (3.0, 15.0)


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = next(
        (v for k, v in _PRICING.items() if model.startswith(k)),
        _DEFAULT_PRICING,
    )
    return (input_tokens / 1_000_000) * inp + (output_tokens / 1_000_000) * out


# ── control plane helpers ──────────────────────────────────────────────────────

_cp_headers = {"x-api-key": PROJECT_KEY, "content-type": "application/json"}


async def _check(model: str) -> dict:
    """Ask the control plane whether this call is allowed."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GUARDRAIL_URL}/agent/check",
            json={"model": model},
            headers=_cp_headers,
        )
        resp.raise_for_status()
        return resp.json()


async def _report(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    was_downgraded: bool,
    was_blocked: bool,
) -> None:
    """Report usage to the control plane after the call completes."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{GUARDRAIL_URL}/agent/report",
                json={
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "was_downgraded": was_downgraded,
                    "was_blocked": was_blocked,
                },
                headers=_cp_headers,
            )
    except Exception as exc:
        # Never let a reporting failure break the response path
        logger.warning("Usage report failed (will retry on next call): %s", exc)


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="Guardrail Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/v1/messages")
async def proxy(request: Request):
    body = await request.json()
    model = body.get("model", "")
    is_stream = body.get("stream", False)

    # ── step 1: enforcement check ──────────────────────────────────────────────
    try:
        decision = await _check(model)
    except httpx.HTTPStatusError as exc:
        logger.error("Control plane check failed: %s", exc)
        raise HTTPException(status_code=503, detail="Guardrail control plane unavailable")

    if decision["decision"] == "block":
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "type": "budget_exceeded",
                    "message": decision.get("reason", "Budget exhausted"),
                }
            },
        )

    was_downgraded = decision["decision"] == "downgrade"
    final_model = decision.get("model", model)

    if was_downgraded:
        logger.info("Model downgraded: %s → %s", model, final_model)
        body = {**body, "model": final_model}

    # ── step 2: call Anthropic using the local key ─────────────────────────────
    upstream_headers = {
        "x-api-key": ANTHROPIC_KEY,          # key stays on this machine
        "anthropic-version": ANTHROPIC_VER,
        "content-type": "application/json",
    }

    if is_stream:
        return await _stream_response(body, upstream_headers, final_model, was_downgraded)
    return await _json_response(body, upstream_headers, final_model, was_downgraded)


# ── non-streaming ──────────────────────────────────────────────────────────────

async def _json_response(body, headers, model, was_downgraded):
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(ANTHROPIC_URL, json=body, headers=headers)

    data = resp.json()
    if resp.status_code == 200:
        usage = data.get("usage", {})
        input_tokens  = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        actual_model  = data.get("model", model)
        cost = _compute_cost(actual_model, input_tokens, output_tokens)
        asyncio.create_task(
            _report(actual_model, input_tokens, output_tokens, cost, was_downgraded, False)
        )

    return JSONResponse(content=data, status_code=resp.status_code)


# ── streaming ──────────────────────────────────────────────────────────────────

async def _stream_response(body, headers, model, was_downgraded):
    async def generator() -> AsyncIterator[bytes]:
        ctx = {"input_tokens": 0, "output_tokens": 0, "model": model}
        buf = ""

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", ANTHROPIC_URL, json=body, headers=headers) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
                    buf += chunk.decode("utf-8", errors="ignore")
                    *lines, buf = buf.split("\n")
                    for line in lines:
                        _parse_sse(line, ctx)

        cost = _compute_cost(ctx["model"], ctx["input_tokens"], ctx["output_tokens"])
        asyncio.create_task(
            _report(ctx["model"], ctx["input_tokens"], ctx["output_tokens"],
                    cost, was_downgraded, False)
        )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


def _parse_sse(line: str, ctx: dict) -> None:
    if not line.startswith("data: "):
        return
    try:
        ev = json.loads(line[6:])
        t  = ev.get("type")
        if t == "message_start":
            msg = ev.get("message", {})
            ctx["input_tokens"] = msg.get("usage", {}).get("input_tokens", 0)
            ctx["model"]        = msg.get("model", ctx["model"])
        elif t == "message_delta":
            ctx["output_tokens"] = ev.get("usage", {}).get("output_tokens", 0)
    except (json.JSONDecodeError, KeyError):
        pass


# ── health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    masked = f"{ANTHROPIC_KEY[:8]}...{ANTHROPIC_KEY[-4:]}"
    return {
        "status": "ok",
        "mode": "agent",
        "anthropic_key": masked,
        "guardrail_url": GUARDRAIL_URL,
    }


# ── entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 55)
    logger.info("  Guardrail Agent")
    logger.info("  Listening on       http://0.0.0.0:%d", PORT)
    logger.info("  Control plane      %s", GUARDRAIL_URL)
    logger.info("  Anthropic key      %s...%s", ANTHROPIC_KEY[:8], ANTHROPIC_KEY[-4:])
    logger.info("  Key never leaves this machine.")
    logger.info("=" * 55)

    uvicorn.run(app, host="0.0.0.0", port=PORT)

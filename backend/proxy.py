"""
Core proxy logic: intercept → enforce → forward → log.
Handles both streaming (SSE) and non-streaming Anthropic requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from alerts import maybe_send_alert
from cost import compute_cost
from enforcement import EnforcementDecision, EnforcementMode, Project, check_enforcement
from redis_client import get_spend, increment_spend

logger = logging.getLogger(__name__)

from config import settings as _settings
ANTHROPIC_API_URL = _settings.anthropic_api_url
ANTHROPIC_VERSION = "2023-06-01"


async def handle_proxy_request(
    request_body: dict,
    raw_headers: dict,
    project: Project,
    provider_key: str,
    pool,
) -> JSONResponse | StreamingResponse:
    model = request_body.get("model", "")
    is_stream = request_body.get("stream", False)

    # --- spend check ---
    daily_spend, monthly_spend = await get_spend(project.id)
    decision = check_enforcement(project, model, daily_spend, monthly_spend)

    if decision.blocked:
        await _log_request(pool, project.id, model, 0, 0, 0.0, False, True)
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "type": "budget_exceeded",
                    "message": decision.block_reason,
                }
            },
        )

    if decision.downgraded:
        logger.info(
            "[%s] model downgraded %s → %s",
            project.name,
            decision.original_model,
            decision.new_model,
        )
        request_body = {**request_body, "model": decision.new_model}

    upstream_headers = {
        "x-api-key": provider_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    if is_stream:
        return await _stream(pool, project, request_body, upstream_headers, decision, model)
    return await _non_stream(pool, project, request_body, upstream_headers, decision, model)


# ── non-streaming ────────────────────────────────────────────────────────────

async def _non_stream(pool, project, body, headers, decision, original_model):
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(ANTHROPIC_API_URL, json=body, headers=headers)

    data = resp.json()

    if resp.status_code == 200:
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        actual_model = data.get("model", body["model"])
        cost = compute_cost(actual_model, input_tokens, output_tokens)
        asyncio.create_task(
            _post_request(pool, project, actual_model, input_tokens, output_tokens,
                          cost, decision.downgraded)
        )

    return JSONResponse(content=data, status_code=resp.status_code)


# ── streaming ────────────────────────────────────────────────────────────────

async def _stream(pool, project, body, headers, decision, original_model):
    async def generator() -> AsyncIterator[bytes]:
        ctx = {"input_tokens": 0, "output_tokens": 0, "model": body.get("model", "")}
        buffer = ""

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", ANTHROPIC_API_URL, json=body, headers=headers) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
                    buffer += chunk.decode("utf-8", errors="ignore")
                    # process complete lines, keep any trailing partial line
                    *lines, buffer = buffer.split("\n")
                    for line in lines:
                        _parse_sse_line(line, ctx)

        # stream done — run post-request tasks
        cost = compute_cost(ctx["model"], ctx["input_tokens"], ctx["output_tokens"])
        asyncio.create_task(
            _post_request(pool, project, ctx["model"], ctx["input_tokens"],
                          ctx["output_tokens"], cost, decision.downgraded)
        )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


def _parse_sse_line(line: str, ctx: dict) -> None:
    if not line.startswith("data: "):
        return
    try:
        event = json.loads(line[6:])
        t = event.get("type")
        if t == "message_start":
            msg = event.get("message", {})
            ctx["input_tokens"] = msg.get("usage", {}).get("input_tokens", 0)
            ctx["model"] = msg.get("model", ctx["model"])
        elif t == "message_delta":
            ctx["output_tokens"] = event.get("usage", {}).get("output_tokens", 0)
    except (json.JSONDecodeError, KeyError):
        pass


# ── post-request: update Redis, log to Postgres, fire alerts ─────────────────

async def _post_request(
    pool, project: Project, model: str,
    input_tokens: int, output_tokens: int,
    cost: float, was_downgraded: bool,
) -> None:
    daily_spend, monthly_spend = await increment_spend(project.id, cost)
    await _log_request(pool, project.id, model, input_tokens, output_tokens,
                       cost, was_downgraded, False)

    budget = project.budget_daily or project.budget_monthly
    spend = daily_spend if project.budget_daily else monthly_spend

    if budget and project.telegram_chat_id:
        await maybe_send_alert(
            project.id, project.name, project.telegram_chat_id,
            spend, budget, pool,
        )


async def _log_request(
    pool, project_id: str, model: str,
    input_tokens: int, output_tokens: int,
    cost: float, was_downgraded: bool, was_blocked: bool,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO requests
              (project_id, model, input_tokens, output_tokens, cost, was_downgraded, was_blocked)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            project_id, model, input_tokens, output_tokens,
            cost, was_downgraded, was_blocked,
        )

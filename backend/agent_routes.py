"""
Agent-mode control plane endpoints.

The local agent (running on the user's infrastructure) calls these two routes:
  POST /agent/check  — pre-call: returns allow / downgrade / block decision
  POST /agent/report — post-call: logs usage, updates spend, fires alerts

The Anthropic API key never appears in either call — it stays on the user's machine.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from alerts import maybe_send_alert
from cost import compute_cost
from database import get_pool
from enforcement import EnforcementMode, Project, check_enforcement
from redis_client import get_spend, increment_spend

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ── request models ─────────────────────────────────────────────────────────────

class CheckRequest(BaseModel):
    model: str


class ReportRequest(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    was_downgraded: bool = False
    was_blocked: bool = False


# ── shared auth helper ─────────────────────────────────────────────────────────

async def _get_agent_project(proxy_key: str) -> Project:
    """Look up a project by proxy key. Rejects stored-mode keys."""
    if not proxy_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    key_hash = hashlib.sha256(proxy_key.encode()).hexdigest()
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.id, p.name, p.budget_daily, p.budget_monthly,
                   p.enforcement_mode, p.telegram_chat_id,
                   k.key_mode
            FROM api_keys k
            JOIN projects p ON k.project_id = p.id
            WHERE k.key_hash = $1
            """,
            key_hash,
        )

    if not row:
        raise HTTPException(status_code=401, detail="Invalid proxy API key")
    if row["key_mode"] != "agent":
        raise HTTPException(
            status_code=403,
            detail="This key is configured for stored mode. Use /v1/messages instead.",
        )

    return Project(
        id=str(row["id"]),
        name=row["name"],
        budget_daily=float(row["budget_daily"]) if row["budget_daily"] else None,
        budget_monthly=float(row["budget_monthly"]) if row["budget_monthly"] else None,
        enforcement_mode=EnforcementMode(row["enforcement_mode"]),
        telegram_chat_id=row["telegram_chat_id"],
    )


# ── /agent/check ───────────────────────────────────────────────────────────────

@router.post("/check")
async def agent_check(body: CheckRequest, request: Request):
    """
    Pre-call enforcement check. The agent calls this before forwarding to Anthropic.
    Returns one of: allow / downgrade / block.
    """
    project = await _get_agent_project(request.headers.get("x-api-key", ""))
    daily_spend, monthly_spend = await get_spend(project.id)
    decision = check_enforcement(project, body.model, daily_spend, monthly_spend)

    if decision.blocked:
        # Log the blocked attempt immediately so the dashboard reflects it
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO requests
                  (project_id, model, input_tokens, output_tokens, cost, was_downgraded, was_blocked)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                """,
                project.id, body.model, 0, 0, 0.0, False, True,
            )
        return {"decision": "block", "reason": decision.block_reason}

    if decision.downgraded:
        logger.info("[%s] agent downgrade %s → %s", project.name, body.model, decision.new_model)
        return {"decision": "downgrade", "model": decision.new_model}

    return {"decision": "allow", "model": body.model}


# ── /agent/report ──────────────────────────────────────────────────────────────

@router.post("/report")
async def agent_report(body: ReportRequest, request: Request):
    """
    Post-call usage report. The agent calls this after the Anthropic response completes.
    Updates Redis spend counters, writes to Postgres, fires Telegram alerts if needed.
    """
    project = await _get_agent_project(request.headers.get("x-api-key", ""))

    daily_spend, monthly_spend = await increment_spend(project.id, body.cost)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO requests
              (project_id, model, input_tokens, output_tokens, cost, was_downgraded, was_blocked)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            project.id, body.model, body.input_tokens, body.output_tokens,
            body.cost, body.was_downgraded, body.was_blocked,
        )

    budget = project.budget_daily or project.budget_monthly
    spend = daily_spend if project.budget_daily else monthly_spend
    if budget and project.telegram_chat_id:
        await maybe_send_alert(
            project.id, project.name, project.telegram_chat_id,
            spend, budget, pool,
        )

    return {"ok": True}

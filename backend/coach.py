"""
Usage coach analytics — runs entirely over the existing `requests` table.
No additional storage needed; all insights are derived from token counts and costs.
"""
from __future__ import annotations

import asyncpg

from cost import MODEL_DOWNGRADE_MAP, compute_cost

# Models worth flagging for "cheaper alternative" suggestions
_EXPENSIVE_PREFIXES = ("claude-opus", "claude-sonnet")

# Calls below this total-token count on an expensive model are candidates for downgrade
_SHORT_CALL_THRESHOLD = 2_000


# ── public API ────────────────────────────────────────────────────────────────

async def get_top_cost_drivers(
    pool: asyncpg.Pool, project_id: str, days: int = 30
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                model,
                COUNT(*)                             AS call_count,
                SUM(cost)                            AS total_cost,
                AVG(input_tokens + output_tokens)    AS avg_tokens
            FROM requests
            WHERE project_id = $1
              AND created_at > NOW() - ($2 * INTERVAL '1 day')
              AND was_blocked = FALSE
            GROUP BY model
            ORDER BY total_cost DESC
            LIMIT 10
            """,
            project_id, days,
        )

    total = sum(float(r["total_cost"]) for r in rows)
    return [
        {
            "model": r["model"],
            "call_count": int(r["call_count"]),
            "total_cost": round(float(r["total_cost"]), 4),
            "avg_tokens": round(float(r["avg_tokens"] or 0)),
            "pct_of_total": round(float(r["total_cost"]) / total * 100, 1) if total > 0 else 0,
        }
        for r in rows
    ]


async def get_context_bloat(
    pool: asyncpg.Pool, project_id: str, last_n: int = 20
) -> dict:
    """
    Detects when a project keeps resending growing context across consecutive calls.
    Strategy: if >= 65% of the last N calls show strictly increasing input_tokens
    with an average growth of >=10% per call, we flag it.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT input_tokens, output_tokens, cost
            FROM requests
            WHERE project_id = $1 AND was_blocked = FALSE
            ORDER BY created_at DESC
            LIMIT $2
            """,
            project_id, last_n,
        )

    if len(rows) < 4:
        return {"detected": False}

    # chronological order (oldest first)
    tokens = [r["input_tokens"] for r in reversed(rows)]

    increases = [
        (tokens[i] - tokens[i - 1]) / max(tokens[i - 1], 1) * 100
        for i in range(1, len(tokens))
        if tokens[i] > tokens[i - 1]
    ]
    growth_ratio = len(increases) / (len(tokens) - 1)
    avg_growth_pct = sum(increases) / len(increases) if increases else 0

    if growth_ratio < 0.65 or avg_growth_pct < 10:
        return {"detected": False}

    # Estimate wasted cost: tokens above the minimum baseline multiplied by
    # average cost-per-token across the sampled window.
    total_cost = sum(float(r["cost"]) for r in rows)
    total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in rows)
    cost_per_token = total_cost / max(total_tokens, 1)
    waste_tokens_per_call = max(tokens) - min(tokens)
    estimated_waste = waste_tokens_per_call * cost_per_token * len(rows)

    return {
        "detected": True,
        "growth_ratio": round(growth_ratio, 2),
        "avg_growth_pct": round(avg_growth_pct, 1),
        "requests_analyzed": len(rows),
        "min_input_tokens": min(tokens),
        "max_input_tokens": max(tokens),
        "estimated_waste_usd": round(estimated_waste, 4),
    }


async def get_model_suggestions(
    pool: asyncpg.Pool, project_id: str, days: int = 30
) -> list[dict]:
    """
    Finds short calls (< _SHORT_CALL_THRESHOLD tokens) made with expensive models
    and estimates savings if a cheaper model had been used instead.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                model,
                COUNT(*)            AS call_count,
                SUM(cost)           AS total_cost,
                SUM(input_tokens)   AS total_input,
                SUM(output_tokens)  AS total_output,
                AVG(input_tokens + output_tokens) AS avg_tokens
            FROM requests
            WHERE project_id = $1
              AND created_at > NOW() - ($2 * INTERVAL '1 day')
              AND was_blocked = FALSE
              AND (input_tokens + output_tokens) < $3
            GROUP BY model
            HAVING COUNT(*) >= 3
            ORDER BY SUM(cost) DESC
            """,
            project_id, days, _SHORT_CALL_THRESHOLD,
        )

    suggestions = []
    for row in rows:
        model: str = row["model"]
        if not any(model.startswith(p) for p in _EXPENSIVE_PREFIXES):
            continue

        cheaper = next(
            (target for prefix, target in MODEL_DOWNGRADE_MAP.items() if model.startswith(prefix)),
            None,
        )
        if not cheaper or cheaper == model:
            continue

        total_in = int(row["total_input"] or 0)
        total_out = int(row["total_output"] or 0)
        actual = float(row["total_cost"])
        estimated = compute_cost(cheaper, total_in, total_out)
        savings = actual - estimated
        savings_pct = savings / actual * 100 if actual > 0 else 0

        if savings_pct < 30:
            continue

        suggestions.append({
            "current_model": model,
            "suggested_model": cheaper,
            "call_count": int(row["call_count"]),
            "avg_tokens": round(float(row["avg_tokens"] or 0)),
            "actual_cost": round(actual, 4),
            "estimated_cost_with_suggestion": round(estimated, 4),
            "estimated_savings_usd": round(savings, 4),
            "savings_pct": round(savings_pct, 1),
        })

    return suggestions

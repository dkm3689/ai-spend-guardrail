from __future__ import annotations
import asyncpg
import httpx
from config import settings

THRESHOLDS = [50, 80, 100]


async def maybe_send_alert(
    project_id: str,
    project_name: str,
    chat_id: str,
    spend: float,
    budget: float,
    pool: asyncpg.Pool,
) -> None:
    if not chat_id or not settings.telegram_bot_token:
        return

    pct = (spend / budget) * 100
    sent = await _get_sent_thresholds(pool, project_id)

    for threshold in THRESHOLDS:
        if pct >= threshold and threshold not in sent:
            await _send_telegram(chat_id, project_name, spend, budget, threshold)
            await _record_alert(pool, project_id, threshold)


async def _get_sent_thresholds(pool: asyncpg.Pool, project_id: str) -> list[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT threshold_pct FROM alerts_sent
            WHERE project_id = $1
              AND sent_at > NOW() - INTERVAL '24 hours'
            """,
            project_id,
        )
    return [r["threshold_pct"] for r in rows]


async def _send_telegram(
    chat_id: str, project_name: str, spend: float, budget: float, threshold: int
) -> None:
    emoji = "🚨" if threshold == 100 else "⚠️"
    text = (
        f"{emoji} *AI Spend Alert — {project_name}*\n"
        f"Reached *{threshold}%* of budget\n"
        f"Spent: `${spend:.4f}` / `${budget:.2f}`"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        )


async def _record_alert(pool: asyncpg.Pool, project_id: str, threshold: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO alerts_sent (project_id, threshold_pct) VALUES ($1, $2)",
            project_id,
            threshold,
        )

from __future__ import annotations
from datetime import date
import redis.asyncio as aioredis
from config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _daily_key(project_id: str) -> str:
    return f"spend:{project_id}:daily:{date.today().isoformat()}"


def _monthly_key(project_id: str) -> str:
    today = date.today()
    return f"spend:{project_id}:monthly:{today.year}-{today.month:02d}"


async def get_spend(project_id: str) -> tuple[float, float]:
    redis = get_redis()
    daily, monthly = await redis.mget(_daily_key(project_id), _monthly_key(project_id))
    return float(daily or 0), float(monthly or 0)


async def increment_spend(project_id: str, cost: float) -> tuple[float, float]:
    redis = get_redis()
    daily_k = _daily_key(project_id)
    monthly_k = _monthly_key(project_id)

    pipe = redis.pipeline()
    pipe.incrbyfloat(daily_k, cost)
    pipe.incrbyfloat(monthly_k, cost)
    pipe.expire(daily_k, 86400 * 2)    # 2-day TTL — safe window for daily rollover
    pipe.expire(monthly_k, 86400 * 35)
    results = await pipe.execute()

    return float(results[0]), float(results[1])

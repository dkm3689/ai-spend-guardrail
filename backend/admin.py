"""
Admin endpoints for managing projects and API keys (no UI yet — Week 2).
Protected by a master admin secret in the Authorization header.
"""
from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config import settings
from crypto import decrypt_key, encrypt_key
from database import get_pool
from redis_client import get_spend

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(authorization: str = Header(...)):
    expected = f"Bearer {settings.admin_secret}"
    if authorization != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── request / response models ─────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    budget_daily: float | None = None
    budget_monthly: float | None = None
    enforcement_mode: str = "alert-only"  # alert-only | visible-downgrade | hard-cap
    telegram_chat_id: str | None = None


class CreateKeyRequest(BaseModel):
    provider_key: str  # the user's real Anthropic API key


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/projects", dependencies=[Depends(_require_admin)])
async def create_project(body: CreateProjectRequest):
    valid_modes = {"alert-only", "visible-downgrade", "hard-cap"}
    if body.enforcement_mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"enforcement_mode must be one of {valid_modes}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (name, budget_daily, budget_monthly, enforcement_mode, telegram_chat_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, name, budget_daily, budget_monthly, enforcement_mode, created_at
            """,
            body.name, body.budget_daily, body.budget_monthly,
            body.enforcement_mode, body.telegram_chat_id,
        )
    return dict(row)


@router.get("/projects", dependencies=[Depends(_require_admin)])
async def list_projects():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, budget_daily, budget_monthly, enforcement_mode, created_at FROM projects ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/keys", dependencies=[Depends(_require_admin)])
async def create_api_key(project_id: str, body: CreateKeyRequest):
    plain_key = f"sk-guard-{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    encrypted = encrypt_key(body.provider_key)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO api_keys (project_id, key_hash, provider_key_encrypted) VALUES ($1, $2, $3)",
            project_id, key_hash, encrypted,
        )

    # Return the plain key once — it is NOT stored in plaintext, save it now
    return {"proxy_key": plain_key, "warning": "Save this key — it will not be shown again."}


@router.get("/projects/{project_id}/spend", dependencies=[Depends(_require_admin)])
async def get_project_spend(project_id: str):
    daily, monthly = await get_spend(project_id)
    return {"project_id": project_id, "daily_spend": daily, "monthly_spend": monthly}


@router.patch("/projects/{project_id}", dependencies=[Depends(_require_admin)])
async def update_project(project_id: str, body: CreateProjectRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE projects
            SET name=$1, budget_daily=$2, budget_monthly=$3,
                enforcement_mode=$4, telegram_chat_id=$5
            WHERE id=$6
            RETURNING id, name, budget_daily, budget_monthly, enforcement_mode
            """,
            body.name, body.budget_daily, body.budget_monthly,
            body.enforcement_mode, body.telegram_chat_id, project_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)

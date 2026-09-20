from __future__ import annotations

import logging

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException

from config import settings

logger = logging.getLogger(__name__)

_DEV_USER_ID = "00000000-0000-0000-0000-000000000000"

# Cached JWKS client — fetched once, keys are cached internally by PyJWKClient
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        logger.info("Initializing JWKS client: %s", url)
        _jwks_client = PyJWKClient(url, cache_jwk_set=True)
    return _jwks_client


async def get_current_user_id(authorization: str = Header(default="")) -> str:
    # Dev mode: no Supabase configured — accept any Bearer token
    if not settings.supabase_url and not settings.supabase_jwt_secret:
        return _DEV_USER_ID

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[7:]

    try:
        if settings.supabase_url:
            # JWKS path — works for ES256, RS256, and any future Supabase algorithm
            client = _get_jwks_client()
            signing_key = client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience="authenticated",
            )
        else:
            # Fallback: symmetric HS256 secret (older Supabase projects)
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        return str(payload["sub"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

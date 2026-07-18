from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException

from config import settings

_DEV_USER_ID = "dev-user-00000000-0000-0000-0000-000000000000"


async def get_current_user_id(authorization: str = Header(default="")) -> str:
    # When no JWT secret is configured, accept any Bearer token and return a
    # fixed dev user ID so local testing works without Supabase.
    if not settings.supabase_jwt_secret:
        return _DEV_USER_ID

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[7:]
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return str(payload["sub"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

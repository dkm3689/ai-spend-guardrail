from __future__ import annotations
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379"
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str
    telegram_bot_token: str = ""
    # Master secret for admin endpoints (project/key management)
    admin_secret: str = "change-me"
    # Supabase JWT secret — leave empty to disable auth (local dev only)
    supabase_jwt_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

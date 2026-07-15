from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    upstash_redis_url: str
    upstash_redis_token: str
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str
    telegram_bot_token: str = ""
    # Master secret for admin endpoints (project/key management)
    admin_secret: str = "change-me"
    # From Supabase dashboard → Project Settings → API → JWT Secret
    supabase_jwt_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

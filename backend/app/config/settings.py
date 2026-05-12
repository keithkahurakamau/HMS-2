from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "MediFleet"
    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ENCRYPTION_KEY: str = "00000000000000000000000000000000" # 32-byte fallback, must override in .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — comma-separated list of allowed origins.
    # Production deployments MUST set CORS_ORIGINS explicitly to a closed list of trusted domains.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # Database pool tuning. With many tenants and gunicorn/uvicorn workers,
    # connection pressure mounts quickly. Defaults are conservative and
    # designed to sit comfortably behind PgBouncer in production.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800  # recycle every 30 min to dodge idle-killers
    TENANT_ENGINE_CACHE_SIZE: int = 32   # LRU cap on the in-process tenant engine cache

    # Redis (optional) — when set, WebSocket broadcasts use Redis pub/sub so they
    # work across multiple workers / load-balanced replicas. When unset, we fall
    # back to the in-process dictionary and log a warning at boot.
    REDIS_URL: str = ""

    # M-Pesa
    MPESA_ENV: str = "sandbox"
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_PASSKEY: str = ""
    MPESA_SHORTCODE: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Pydantic V2 specific config for loading .env files
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
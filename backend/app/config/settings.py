from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "MediFleet"
    VERSION: str = "1.0.0"

    # Authoritative environment flag. Drives cookie security flags (secure,
    # samesite=none) and any future "am I in production" decisions. Set this
    # on Render to "production". Anything else (or unset) is treated as
    # development. The legacy fallback below ALSO accepts MPESA_ENV for
    # backwards compatibility with older deployments, but APP_ENV wins.
    APP_ENV: str = "development"

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

    @property
    def is_production(self) -> bool:
        """Authoritative production flag.

        Reads APP_ENV first (explicit, recommended). Falls back to MPESA_ENV
        for older deployments that were keying cookie flags off the M-Pesa
        environment — a brittle proxy that broke when sandbox M-Pesa was
        used in production. Either signal flipping to 'production' marks
        the deployment as prod.
        """
        return (self.APP_ENV or "").lower() == "production" or (self.MPESA_ENV or "").lower() == "production"

    # Pydantic V2 specific config for loading .env files
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
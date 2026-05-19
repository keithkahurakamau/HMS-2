from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "MediFleet"
    VERSION: str = "1.0.0"

    # Authoritative environment flag. Drives cookie security flags (secure,
    # samesite=none), CORS strictness, log redaction, and the rest of the
    # production toggles. APP_ENV is the *only* signal; the previous
    # MPESA_ENV fallback was brittle (a prod deploy with sandbox Daraja
    # accidentally leaked password-reset tokens — see audit SEC-004).
    APP_ENV: str = "development"

    # Database
    DATABASE_URL: str

    # Security — SECRET_KEY and ENCRYPTION_KEY have NO defaults. Pydantic
    # raises at import-time if either is missing or weak (audit SEC-001).
    SECRET_KEY: SecretStr
    ENCRYPTION_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_strength(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if len(raw) < 32:
            raise ValueError("SECRET_KEY must be at least 32 bytes")
        if raw.strip("0") == "" or raw == "changeme":
            raise ValueError("SECRET_KEY appears to be a placeholder")
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _enc_strength(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if len(raw) < 32:
            raise ValueError("ENCRYPTION_KEY must be at least 32 bytes (use Fernet.generate_key())")
        if len(set(raw)) < 8:
            raise ValueError("ENCRYPTION_KEY entropy too low — generate with cryptography.fernet.Fernet.generate_key()")
        return v

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
    def jwt_secret(self) -> str:
        """Plain JWT signing secret. Use this everywhere instead of
        ``settings.SECRET_KEY`` directly — SECRET_KEY is now a SecretStr so
        accidental ``str(settings.SECRET_KEY)`` returns ``'**********'``.
        """
        return self.SECRET_KEY.get_secret_value()

    @property
    def is_production(self) -> bool:
        """Authoritative production flag. APP_ENV is the single source of truth.

        Audit SEC-004 retired the MPESA_ENV fallback: a prod deploy running
        Daraja-sandbox was being misclassified as non-production by code that
        keyed off the M-Pesa env (e.g. password-reset token leakage). M-Pesa
        environment is configured separately under MPESA_ENV and never gates
        security-critical behaviour.
        """
        return (self.APP_ENV or "").lower() == "production"

    # Pydantic V2 — extra="forbid" so typos like SECERT_KEY fail loud instead
    # of silently falling back to a default (audit SEC-005).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

settings = Settings()
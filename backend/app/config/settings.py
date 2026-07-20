import logging

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

_logger = logging.getLogger(__name__)

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
    # AUTH-001: server-side pepper HMACed into every password before Argon2id
    # hashing. Required in production; empty allowed in dev so existing
    # bcrypt-only hashes keep verifying.
    PASSWORD_PEPPER: SecretStr = SecretStr("")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Pay Hero aggregator (PAY-001) ──────────────────────────────────
    PAYHERO_ENV: str = "sandbox"               # 'sandbox' | 'production'
    PAYHERO_BASE_URL: str = "https://backend.payhero.co.ke/api/v2"
    PAYHERO_USERNAME: SecretStr = SecretStr("")
    PAYHERO_PASSWORD: SecretStr = SecretStr("")
    PAYHERO_CHANNEL_ID: str = ""               # Till / Paybill / Bank channel
    PAYHERO_WEBHOOK_SECRET: SecretStr = SecretStr("")
    # Comma-separated CIDR allow-list (PAY-002). Empty disables IP check —
    # only acceptable in development; verify_payhero raises in production.
    PAYHERO_WEBHOOK_CIDRS: str = ""
    # H-4: CIDRs of the proxies/load-balancers we sit behind (e.g. Render/LB
    # egress). X-Forwarded-For is only trusted when the *immediate* peer is one
    # of these — otherwise a direct caller could spoof an allow-listed source.
    # Empty falls back to a safe heuristic: trust XFF only when the peer is a
    # private/loopback address (i.e. we're clearly behind a platform LB).
    PAYHERO_TRUSTED_PROXIES: str = ""
    PUBLIC_BASE_URL: str = ""                  # https://… used for callback URLs

    # ── Email / SMTP (EMAIL-001) ───────────────────────────────────────
    # Provider-agnostic: any SMTP relay works (Gmail, Mailgun, Resend,
    # AWS SES — they all expose an SMTP endpoint). Swap providers by
    # editing these env vars; no code change required.
    #
    # EMAIL_ENABLED is the master switch. When false (the dev default) the
    # service logs the rendered message instead of sending, and auth flows
    # keep surfacing tokens inline (dev_token) so local testing still works.
    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_USE_TLS: bool = True                  # STARTTLS on port 587
    SMTP_USE_SSL: bool = False                 # implicit TLS on port 465
    SMTP_TIMEOUT_SECONDS: int = 15
    EMAIL_FROM: str = ""                        # noreply@yourplatform.com
    EMAIL_FROM_NAME: str = "MediFleet"
    # Reply-To address. Set to your support inbox (e.g. support@medifleet.app)
    # so when a client hits "reply" on a system email it reaches the support
    # team. Receiving those replies still requires MX/inbound configured on the
    # mail provider for that domain — see docs.
    EMAIL_REPLY_TO: str = ""
    # Role-based sender identities (EMAIL-002). When set, outbound mail can be
    # sent "from" the right desk. Empty falls back to EMAIL_FROM.
    EMAIL_FROM_SUPPORT: str = ""               # support@medifleet.app
    EMAIL_FROM_FINANCE: str = ""               # finance@medifleet.app
    EMAIL_FROM_TECHNICAL: str = ""             # technical@medifleet.app
    # Where the public landing-page contact form delivers leads. Point this at
    # a real mailbox you actually read (Gmail, Google Workspace, etc.) — NOT an
    # address whose MX routes back into Resend inbound. Falls back to
    # EMAIL_REPLY_TO then EMAIL_FROM.
    CONTACT_RECIPIENT_EMAIL: str = ""
    # Where emailed links (password reset, invites) point. Falls back to the
    # first CORS origin when unset so dev "just works".
    FRONTEND_BASE_URL: str = ""

    # ── Inbound support email (EMAIL-003) ──────────────────────────────
    # Clients email support@/finance@/technical@<domain>; the mail provider
    # (Resend Inbound) POSTs the parsed message to /api/public/support/inbound,
    # which threads it into the platform Support Inbox.
    SUPPORT_INBOUND_ENABLED: bool = False
    # HMAC signing secret from the provider's inbound webhook config. Required
    # when inbound is enabled — the endpoint rejects unsigned/forged posts.
    SUPPORT_INBOUND_SIGNING_SECRET: SecretStr = SecretStr("")
    # Domain used to build per-ticket reply addresses (support+ticket-<id>@…)
    # and to recognise our own inbound recipients.
    SUPPORT_INBOUND_DOMAIN: str = "medifleet.app"
    # When True, only senders who already have a ticket can email in (strict
    # anti-spam). When False (default), ANY inbound email from a recognised
    # recipient address becomes a ticket — unknown senders land in the
    # "Unassigned" bucket. Default False so real customer emails actually arrive.
    SUPPORT_INBOUND_KNOWN_CONTACTS_ONLY: bool = False

    # ── Outbound email events / suppression (EMAIL-004) ────────────────
    # Resend "events" webhook → /api/public/email/events records delivery
    # events and auto-suppresses hard bounces / spam complaints.
    EMAIL_EVENTS_ENABLED: bool = False
    EMAIL_EVENTS_SIGNING_SECRET: SecretStr = SecretStr("")
    # When true, EmailService.send skips addresses on the suppression list.
    EMAIL_SUPPRESSION_ENABLED: bool = False

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

    # Concurrency / throughput tuning (per worker).
    #
    # ~245 of the API handlers are synchronous `def`, which FastAPI runs in
    # AnyIO's thread pool. Its default cap is 40 threads; that's also the ceiling
    # on concurrent in-flight DB-bound requests per worker. Raising it lets one
    # worker serve more simultaneous requests, but each busy thread can hold one
    # DB connection — so keep THREADPOOL_TOKENS in sane proportion to the
    # database's connection budget (front Postgres with PgBouncer before pushing
    # this high across multiple workers). Default keeps the historical 40.
    THREADPOOL_TOKENS: int = 40

    # Minimum response size (bytes) before GZip compression kicks in. Small
    # bodies aren't worth the CPU; large JSON (charts, lists, reports) benefit a
    # lot over the wire. 0 disables compression entirely.
    GZIP_MIN_SIZE: int = 500

    # Redis (optional) — when set, WebSocket broadcasts use Redis pub/sub so they
    # work across multiple workers / load-balanced replicas. When unset, we fall
    # back to the in-process dictionary and log a warning at boot.
    #
    # NOTE: running more than one web worker (WEB_CONCURRENCY > 1, see
    # render-start.sh) REQUIRES this — without it, a notification or payment
    # event published on worker-A never reaches a socket living on worker-B.
    REDIS_URL: str = ""

    # Infrastructure / orchestration values consumed by docker-compose from the
    # same .env file. Declared here (rather than relaxing extra="forbid") so
    # SEC-005 still catches typos on security-critical fields.
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_HOST_PORT: str = ""
    REDIS_HOST_PORT: str = ""
    BACKEND_HOST_PORT: str = ""
    FRONTEND_HOST_PORT: str = ""
    MIGRATE_ON_BOOT: str = ""
    # Consumed by render-start.sh / docker-compose (gunicorn worker count), not
    # by the app itself — declared so its presence in .env doesn't trip
    # extra="forbid".
    WEB_CONCURRENCY: str = ""
    SEED_SUPERADMIN_EMAIL: str = ""
    SEED_SUPERADMIN_PASSWORD: str = ""

    # Legacy Daraja keys. NO CODE READS THESE — declared only so existing
    # .env files don't trip ``extra="forbid"`` after the Pay Hero swap.
    # Safe to delete from .env; safe to leave in place.
    MPESA_ENV: str = ""
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_PASSKEY: str = ""
    MPESA_SHORTCODE: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def password_pepper(self) -> str:
        """Server-side pepper; empty bytes if not configured (dev only)."""
        return self.PASSWORD_PEPPER.get_secret_value()

    @property
    def payhero_webhook_secret(self) -> str:
        return self.PAYHERO_WEBHOOK_SECRET.get_secret_value()

    @property
    def smtp_password(self) -> str:
        return self.SMTP_PASSWORD.get_secret_value()

    @property
    def support_inbound_signing_secret(self) -> str:
        return self.SUPPORT_INBOUND_SIGNING_SECRET.get_secret_value()

    @property
    def email_events_signing_secret(self) -> str:
        return self.EMAIL_EVENTS_SIGNING_SECRET.get_secret_value()

    def email_from_for(self, desk: str | None) -> str:
        """Resolve the From address for a desk ('support'|'finance'|'technical').
        Falls back to EMAIL_FROM when the desk-specific address isn't set."""
        mapping = {
            "support": self.EMAIL_FROM_SUPPORT,
            "finance": self.EMAIL_FROM_FINANCE,
            "technical": self.EMAIL_FROM_TECHNICAL,
        }
        return (mapping.get(desk or "") or "").strip() or self.EMAIL_FROM

    @property
    def frontend_base_url(self) -> str:
        """Base URL emailed links point at. Explicit FRONTEND_BASE_URL wins;
        otherwise fall back to the first configured CORS origin (dev), then
        to a localhost guess so a missing config never crashes link building.
        """
        if self.FRONTEND_BASE_URL.strip():
            return self.FRONTEND_BASE_URL.strip().rstrip("/")
        origins = self.cors_origin_list
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")

    @property
    def jwt_secret(self) -> str:
        """Plain JWT signing secret. Use this everywhere instead of
        ``settings.SECRET_KEY`` directly — SECRET_KEY is now a SecretStr so
        accidental ``str(settings.SECRET_KEY)`` returns ``'**********'``.
        """
        return self.SECRET_KEY.get_secret_value()

    @model_validator(mode="after")
    def _enforce_production_cors(self):
        """M-5: with allow_credentials=True a stray localhost/preview/wildcard
        origin means credentialed cross-origin access. In production the origin
        list must be a non-empty, closed set — fail boot otherwise (same
        fail-fast posture as the SECRET_KEY/ENCRYPTION_KEY validators)."""
        if (self.APP_ENV or "").lower() == "production":
            origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
            if not origins:
                raise ValueError("CORS_ORIGINS must be a non-empty closed list in production.")
            unsafe = [o for o in origins if "*" in o or "localhost" in o or "127.0.0.1" in o]
            if unsafe:
                raise ValueError(
                    f"production CORS_ORIGINS must not include wildcard or localhost: {unsafe}"
                )
            # AUTH-001 / audit L-1: the pepper is HMACed into every password
            # before Argon2id hashing and is documented as "required in
            # production", but nothing enforced it — a prod deploy that forgot
            # PASSWORD_PEPPER silently dropped to un-peppered hashing. Fail boot
            # with the same fail-fast posture as SECRET_KEY/ENCRYPTION_KEY.
            if not self.PASSWORD_PEPPER.get_secret_value():
                raise ValueError(
                    "PASSWORD_PEPPER must be set in production (HMAC pepper for password hashing)."
                )
            # L-2: warn (don't hard-fail) if SEED_SUPERADMIN_PASSWORD is still
            # the shipped example/placeholder. This var only seeds the *first*
            # superadmin via seed_superadmin.py; an already-bootstrapped
            # platform has its real password in the DB, so failing boot here
            # could needlessly take prod down. We log loudly instead and rely on
            # the stored credential — rotate the example value when convenient.
            if self.SEED_SUPERADMIN_PASSWORD in {"SuperAdmin@2026", "CHANGE_ME_set_a_strong_unique_password"}:
                _logger.warning(
                    "SECURITY: SEED_SUPERADMIN_PASSWORD is still the example/placeholder "
                    "value in production — rotate it and ensure the live superadmin "
                    "account does not use a guessable password."
                )
        return self

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
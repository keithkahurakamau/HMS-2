"""SlowAPI Limiter with optional Redis-backed shared state.

RL-001: prior version used the library default ``memory://`` store, so each
uvicorn worker held its own counter. With 2 workers a "5/minute" cap was
effectively 10/minute. Now:

  * key_func returns ``u:<user_id>`` for authenticated requests (cookie or
    Authorization bearer) and ``ip:<addr>`` for unauthenticated ones, so
    rotating IPs no longer bypasses per-user throttles.
  * storage_uri uses settings.REDIS_URL when set, giving every worker /
    replica a shared view; falls back to memory only when Redis is absent
    (and logs a one-time warning during boot via main.py lifespan).
"""
from __future__ import annotations

import logging

from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _user_or_ip_key(request) -> str:
    """Rate-limit key. Authenticated requests bind to user_id; otherwise IP."""
    token = None
    # Cookie-based session (the only flow used by the SPA)
    try:
        token = request.cookies.get("access_token")
    except Exception:
        token = None
    # Authorization: Bearer ... fallback (machine clients / superadmin)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if token:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.ALGORITHM],
                # Don't verify exp here — an expired token is still the same
                # user for rate-limiting purposes; verify_exp would otherwise
                # raise mid-rate-limit-check and downgrade us to IP keying.
                options={"verify_exp": False},
            )
            uid = payload.get("user_id") or payload.get("sub")
            if uid is not None:
                return f"u:{uid}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


_storage_uri = settings.REDIS_URL or "memory://"
if not settings.REDIS_URL:
    logger.warning(
        "REDIS_URL is unset — SlowAPI is using in-process memory storage. "
        "Per-worker rate limits will diverge; set REDIS_URL in production.",
    )

limiter = Limiter(
    key_func=_user_or_ip_key,
    storage_uri=_storage_uri,
    strategy="moving-window",
    default_limits=["120/minute", "2000/hour"],
)

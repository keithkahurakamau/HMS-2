"""The single seam between MediFleet and Safaricom Daraja.

Every outbound Daraja call goes through here, which is what lets the whole
external surface be mocked at one point in tests. Nothing else in the codebase
may call requests against a Safaricom URL.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import requests

from app.core.circuit import CircuitBreakerOpen, daraja_breaker
from app.services.daraja.credentials import base_url
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

# Tokens live about an hour. Cached per consumer key, in-process: under
# multiple gunicorn workers each process fetching its own costs a handful of
# extra calls per hour, which is cheaper than the invalidation problem a
# shared cache creates.
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_EXPIRY_MARGIN_SECONDS = 60.0


class DarajaError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int | None = None, body: Any = None,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        # Daraja's own machine-readable error code (e.g. "500.001.1001",
        # "The transaction is being processed"), when the rejected response
        # carried one. Preserved as its own attribute, not just folded into
        # `body`'s safe_repr string: that string is redacted and truncated
        # for logging, neither of which this codebase wants to depend on
        # when deciding what a specific error code MEANS (see
        # reconcile_queries.requery_stk, which needs to tell "still
        # processing" apart from every other rejection). errorCode itself
        # is never a secret, so no redaction is needed for it specifically.
        self.error_code = error_code


class DarajaClient:
    """Per-config Daraja client. Construct one per request, it is cheap."""

    def __init__(self, config: Any):
        self.consumer_key = config.consumer_key
        self.consumer_secret = config.consumer_secret
        self.environment = config.environment
        self.shortcode = getattr(config, "shortcode", "")
        self.base = base_url(self.environment)

    def access_token(self) -> str:
        cached = _TOKEN_CACHE.get(self.consumer_key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        return self._fetch_token()

    def _fetch_token(self) -> str:
        pair = f"{self.consumer_key}:{self.consumer_secret}".encode("utf-8")
        headers = {"Authorization": "Basic " + base64.b64encode(pair).decode("ascii")}
        url = f"{self.base}/oauth/v1/generate?grant_type=client_credentials"
        try:
            response = daraja_breaker.call(requests.get, url, headers=headers, timeout=15)
        except CircuitBreakerOpen:
            raise DarajaError("Daraja temporarily unavailable", status_code=503)
        except requests.RequestException as exc:
            raise DarajaError(f"Daraja unreachable: {exc}", status_code=502)
        if response.status_code >= 400:
            raise DarajaError("Daraja rejected the credentials", status_code=response.status_code)
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise DarajaError("Daraja returned no access token", body=safe_repr(data))
        ttl = float(data.get("expires_in") or 3599)
        _TOKEN_CACHE[self.consumer_key] = (
            token,
            time.monotonic() + max(ttl - _EXPIRY_MARGIN_SECONDS, 30.0),
        )
        return token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": "application/json",
        }

    def post(self, path: str, payload: dict) -> dict:
        return self._call(requests.post, path, json=payload)

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._call(requests.get, path, params=params or {})

    def _call(self, fn, path: str, **kwargs) -> dict:
        url = f"{self.base}{path}"
        response = self._execute(fn, url, **kwargs)
        # A 401 means the cached token went stale early. Refresh once and
        # retry; a second 401 is a real credential problem, not a stale token.
        if response.status_code == 401:
            _TOKEN_CACHE.pop(self.consumer_key, None)
            response = self._execute(fn, url, **kwargs)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            message = (
                data.get("errorMessage")
                or data.get("ResponseDescription")
                or "Daraja rejected the request"
            )
            logger.warning("Daraja %s -> %s %s", path, response.status_code, safe_repr(data))
            raise DarajaError(
                message, status_code=response.status_code, body=safe_repr(data),
                error_code=data.get("errorCode"),
            )
        return data

    def _execute(self, fn, url: str, **kwargs):
        try:
            return daraja_breaker.call(fn, url, headers=self._headers(), timeout=30, **kwargs)
        except CircuitBreakerOpen:
            raise DarajaError("Daraja temporarily unavailable", status_code=503)
        except requests.RequestException as exc:
            raise DarajaError(f"Daraja unreachable: {exc}", status_code=502)

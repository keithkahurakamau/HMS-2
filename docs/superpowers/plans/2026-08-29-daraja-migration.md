# Daraja Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Pay Hero aggregator with a direct Safaricom Daraja integration on both the hospital and subscription rails, covering STK Push, C2B, B2C refunds, Transaction Status and reconciliation.

**Architecture:** One Daraja client module is the single seam to Safaricom, so the whole external surface mocks at one point. Per-tenant credentials are Fernet-encrypted on the config row. Because Daraja does not sign callbacks, authentication is rebuilt from an unguessable rotatable token in the callback path, the Safaricom IP allow-list, and a settlement cross-check that never trusts a callback's claim about an amount.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Postgres, `requests`, `cryptography` (Fernet at rest, RSA for `SecurityCredential`), React 19 + Vite + Vitest.

**Spec:** `docs/superpowers/specs/2026-08-29-daraja-migration-design.md`

## Global Constraints

- **No em dashes** anywhere: not in code comments, not in docstrings, not in user-facing copy. Use a colon, a comma, parentheses, or a full stop. This applies to every file you touch, including ones you are only editing in passing.
- **Master-only models stay OUT of the import block** in `backend/scripts/migrate_all_tenants.py`. That list feeds `Base.metadata`, and the script runs an unfiltered `create_all()` against every tenant engine, so anything listed there is physically created in every hospital database. Master schema arrives through `MASTER_DB_PATCHES` instead.
- **Master-only alembic revisions are guarded on the database NAME**, never on `_has_table("tenants")`: tenant databases also contain a `tenants` table, so that guard does not hold.
- **Every secret is Fernet-encrypted at rest** via `app.utils.encryption.encrypt_data` / `decrypt_data`. No plaintext consumer secret, passkey, initiator password or callback token in a column, a log line, or an API response.
- **Callbacks always return HTTP 200** with Safaricom's expected acknowledgement body, including when we reject the content. A non-200 makes Safaricom retry a payload we have already rejected, and on C2B validation it can cause the customer's payment to be declined at the till.
- **Money is `Decimal` end to end.** Never `float`. Never compare or arithmetic across the two.
- Run `cd frontend && npm run build && npm test && npm run lint` after frontend changes. `vite build` does not surface `no-undef`; ESLint must be run explicitly.
- Prefer files under ~500 lines, but never split at the cost of behaviour that works.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/app/services/daraja/client.py` | The only module that speaks HTTP to Safaricom. OAuth token cache, request execution, error mapping. |
| `backend/app/services/daraja/credentials.py` | STK password, `SecurityCredential` RSA generation, MSISDN normalisation. |
| `backend/app/services/daraja/stk.py` | STK Push and STK Query. |
| `backend/app/services/daraja/c2b.py` | RegisterURL, validation and confirmation handling. |
| `backend/app/services/daraja/b2c.py` | Refund dispatch, result and timeout handling. |
| `backend/app/services/daraja/status.py` | Transaction Status and Account Balance. |
| `backend/app/services/daraja/settlement.py` | The shared settle-an-invoice path with the amount cross-check. |
| `backend/app/services/daraja/reconcile.py` | The scheduled resolver for stuck transactions and refunds. |
| `backend/app/core/daraja_callback.py` | Callback authentication: token resolution, IP allow-list, acknowledgement bodies. |
| `backend/app/models/mpesa.py` | `MpesaConfig`, `MpesaTransaction`, `MpesaRefund` (tenant DB). |
| `backend/app/models/platform_mpesa.py` | `PlatformMpesaConfig`, `PlatformMpesaTransaction` (master DB, excluded from the migrate import block). |
| `backend/app/routes/mpesa_payment.py` | Payment initiation and the five callback endpoints. |
| `backend/app/routes/mpesa_admin.py` | Per-tenant config, test push, unmatched queue, transactions. |
| `backend/app/routes/mpesa_refunds.py` | Refund request, approve, list. |
| `backend/app/routes/mpesa_superadmin.py` | Operator view of any tenant's config. |
| `backend/app/routes/platform_mpesa.py` | Subscription rail, wired to the receivables ledger. |
| `backend/app/vendor/safaricom/sandbox.cer`, `production.cer` | Safaricom public certificates for `SecurityCredential`. |
| `backend/app/cli/run_reconcile.py` | Cron entry point. |
| `frontend/src/pages/MpesaSettings.jsx` | Rebuilt against Daraja config. |
| `frontend/src/pages/billing/Refunds.jsx` | Refund request and approval UI. |

**Deleted (Task 12, last, so nothing breaks mid-flight):** `services/payhero_service.py`, `services/payhero_banks.py`, `services/platform_payhero_service.py`, `core/payhero_webhook.py`, `models/payhero.py`, `models/platform_payhero.py`, `routes/payhero_*.py`, `routes/platform_payhero.py`, and the Pay Hero settings block.

---

## Task 1: Daraja credentials and the client seam

**Files:**
- Create: `backend/app/services/daraja/__init__.py`, `credentials.py`, `client.py`
- Create: `backend/app/vendor/safaricom/sandbox.cer`, `backend/app/vendor/safaricom/production.cer`
- Test: `backend/tests/daraja/test_credentials.py`, `backend/tests/daraja/test_client.py`

**Interfaces:**
- Produces:
  - `normalize_msisdn(phone: str) -> str` returning `254XXXXXXXXX`
  - `stk_password(shortcode: str, passkey: str, timestamp: str) -> str`
  - `daraja_timestamp(now: datetime | None = None) -> str` returning `YYYYMMDDHHMMSS`
  - `security_credential(initiator_password: str, environment: str) -> str`
  - `DarajaClient(config)` with `.post(path, payload) -> dict` and `.get(path, params) -> dict`
  - `DarajaError(Exception)` with `.status_code` and `.body`

- [ ] **Step 1: Write the failing credential tests**

```python
# backend/tests/daraja/test_credentials.py
import base64
from datetime import datetime

import pytest

from app.services.daraja.credentials import (
    daraja_timestamp,
    normalize_msisdn,
    security_credential,
    stk_password,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0712345678", "254712345678"),
        ("+254712345678", "254712345678"),
        ("254712345678", "254712345678"),
        (" 0712 345 678 ", "254712345678"),
        ("712345678", "254712345678"),
    ],
)
def test_normalize_msisdn(raw, expected):
    assert normalize_msisdn(raw) == expected


@pytest.mark.parametrize("bad", ["", None, "abc", "07123", "0712345678901234"])
def test_normalize_msisdn_rejects_garbage(bad):
    with pytest.raises(ValueError):
        normalize_msisdn(bad)


def test_daraja_timestamp_shape():
    ts = daraja_timestamp(datetime(2026, 8, 29, 14, 5, 3))
    assert ts == "20260829140503"


def test_stk_password_is_base64_of_concatenation():
    ts = "20260829140503"
    pw = stk_password("174379", "PASSKEY", ts)
    assert base64.b64decode(pw).decode() == "174379" + "PASSKEY" + ts


def test_security_credential_is_not_the_plaintext():
    cred = security_credential("initiator-pw", "sandbox")
    assert cred and "initiator-pw" not in cred
    # RSA output is base64 and materially longer than the input.
    assert len(base64.b64decode(cred)) >= 128


def test_security_credential_rejects_unknown_environment():
    with pytest.raises(ValueError):
        security_credential("x", "staging")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja/test_credentials.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.services.daraja'`

- [ ] **Step 3: Fetch the Safaricom certificates**

The sandbox and production certificates are published by Safaricom on the Daraja portal. Save them verbatim as `backend/app/vendor/safaricom/sandbox.cer` and `backend/app/vendor/safaricom/production.cer`, PEM encoded, beginning `-----BEGIN CERTIFICATE-----`. Add `backend/app/vendor/safaricom/__init__.py` (empty) so the directory ships with the package.

If you cannot reach the portal, STOP and report BLOCKED rather than inventing a certificate. A wrong certificate produces a `SecurityCredential` Safaricom silently rejects at refund time, which is the worst possible place to discover it.

- [ ] **Step 4: Implement credentials.py**

```python
"""Daraja credential derivation: MSISDN, STK password, SecurityCredential.

Kept apart from client.py so the pure functions here are testable without
touching HTTP, and so the RSA certificate handling has one obvious home.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

_CERT_DIR = Path(__file__).resolve().parent.parent.parent / "vendor" / "safaricom"
_ENVIRONMENTS = {"sandbox", "production"}

_DIGITS = re.compile(r"\D")


def normalize_msisdn(phone: str) -> str:
    """Return a Safaricom MSISDN as 2547XXXXXXXX / 2541XXXXXXXX.

    Daraja rejects anything else, and it rejects it with an opaque error, so
    normalise and validate here rather than letting the API tell us later.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("phone number is required")
    digits = _DIGITS.sub("", phone)
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    if not digits.startswith("254") or len(digits) != 12:
        raise ValueError(f"not a Kenyan MSISDN: {phone!r}")
    return digits


def daraja_timestamp(now: datetime | None = None) -> str:
    """Daraja wants local Kenyan wall-clock time as YYYYMMDDHHMMSS."""
    moment = now or datetime.now(timezone.utc).astimezone()
    return moment.strftime("%Y%m%d%H%M%S")


def stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    """base64(shortcode + passkey + timestamp), per the Daraja STK spec."""
    raw = f"{shortcode}{passkey}{timestamp}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


@lru_cache(maxsize=2)
def _public_key(environment: str):
    if environment not in _ENVIRONMENTS:
        raise ValueError(f"unknown Daraja environment: {environment!r}")
    path = _CERT_DIR / f"{environment}.cer"
    if not path.exists():
        raise FileNotFoundError(f"Safaricom certificate missing: {path}")
    cert = load_pem_x509_certificate(path.read_bytes())
    return cert.public_key()


def security_credential(initiator_password: str, environment: str) -> str:
    """RSA-encrypt the initiator password with Safaricom's public certificate.

    Generated per call rather than stored, so a certificate rotation is a
    redeploy instead of a support ticket to every hospital.
    """
    if environment not in _ENVIRONMENTS:
        raise ValueError(f"unknown Daraja environment: {environment!r}")
    if not initiator_password:
        raise ValueError("initiator password is required")
    encrypted = _public_key(environment).encrypt(
        initiator_password.encode("utf-8"), padding.PKCS1v15()
    )
    return base64.b64encode(encrypted).decode("ascii")


def base_url(environment: str) -> str:
    if environment == "production":
        return "https://api.safaricom.co.ke"
    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"
    raise ValueError(f"unknown Daraja environment: {environment!r}")
```

Note `serialization` is imported for parity with the rest of the codebase's crypto modules but is unused here; drop the import rather than leaving it dangling, ESLint's Python equivalent (ruff, if configured) will flag it and a reviewer certainly will.

- [ ] **Step 5: Run the credential tests to verify they pass**

Run: `cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja/test_credentials.py -q`
Expected: PASS, 9 tests

- [ ] **Step 6: Write the failing client tests**

```python
# backend/tests/daraja/test_client.py
import time
from types import SimpleNamespace

import pytest

from app.services.daraja.client import DarajaClient, DarajaError, _TOKEN_CACHE


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_cache():
    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


def _config(**over):
    base = dict(
        consumer_key="ck",
        consumer_secret="cs",
        environment="sandbox",
        shortcode="174379",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_token_is_fetched_once_and_reused(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_get)
    client = DarajaClient(_config())
    assert client.access_token() == "tok"
    assert client.access_token() == "tok"
    assert len(calls) == 1


def test_expired_token_is_refetched(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok2", "expires_in": "3599"}),
    )
    _TOKEN_CACHE["ck"] = ("stale", time.monotonic() - 1)
    client = DarajaClient(_config())
    assert client.access_token() == "tok2"


def test_token_cache_is_keyed_by_consumer_key(monkeypatch):
    """Two tenants must never share a token. This is the isolation guarantee."""
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok-b", "expires_in": "3599"}),
    )
    _TOKEN_CACHE["ck"] = ("tok-a", time.monotonic() + 3000)
    other = DarajaClient(_config(consumer_key="ck-other"))
    assert other.access_token() == "tok-b"
    assert _TOKEN_CACHE["ck"][0] == "tok-a"


def test_post_raises_daraja_error_on_4xx(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )
    monkeypatch.setattr(
        "app.services.daraja.client.requests.post",
        lambda url, **kw: FakeResponse(400, {"errorMessage": "Bad Request"}),
    )
    client = DarajaClient(_config())
    with pytest.raises(DarajaError) as exc:
        client.post("/mpesa/stkpush/v1/processrequest", {})
    assert exc.value.status_code == 400
    assert "Bad Request" in str(exc.value)


def test_401_refreshes_the_token_once_then_retries(monkeypatch):
    tokens = iter(["stale-tok", "fresh-tok"])
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": next(tokens), "expires_in": "3599"}),
    )
    seen = []

    def fake_post(url, **kw):
        seen.append(kw["headers"]["Authorization"])
        return FakeResponse(401 if len(seen) == 1 else 200, {"ok": True})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)
    client = DarajaClient(_config())
    assert client.post("/x", {}) == {"ok": True}
    assert seen == ["Bearer stale-tok", "Bearer fresh-tok"]
```

- [ ] **Step 7: Run to verify failure, then implement client.py**

```python
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
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


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
            raise DarajaError(message, status_code=response.status_code, body=data)
        return data

    def _execute(self, fn, url: str, **kwargs):
        try:
            return daraja_breaker.call(fn, url, headers=self._headers(), timeout=30, **kwargs)
        except CircuitBreakerOpen:
            raise DarajaError("Daraja temporarily unavailable", status_code=503)
        except requests.RequestException as exc:
            raise DarajaError(f"Daraja unreachable: {exc}", status_code=502)
```

- [ ] **Step 8: Add the circuit breaker**

In `backend/app/core/circuit.py`, beside the existing `payhero_breaker` on line 89, add:

```python
daraja_breaker = CircuitBreaker(name="daraja", failure_threshold=5, recovery_seconds=30.0)
```

Leave `payhero_breaker` in place for now; Task 12 removes it.

- [ ] **Step 9: Run the client tests**

Run: `cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja -q`
Expected: PASS, 14 tests

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/daraja backend/app/vendor backend/app/core/circuit.py backend/tests/daraja
git commit -m "feat(daraja): credential derivation and the single Safaricom client seam"
```

---

## Task 2: Tenant schema and the two-shape migration

**Files:**
- Create: `backend/app/models/mpesa.py`
- Create: `backend/alembic/versions/e1f2a3b4c5d6_daraja_schema.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (import block, line 63)
- Test: `backend/tests/daraja/test_schema.py`

**Interfaces:**
- Produces: `MpesaConfig`, `MpesaTransaction`, `MpesaRefund` importable from `app.models.mpesa`.

**These are TENANT tables, so `mpesa` DOES belong in the migrate script's import block** (alphabetically after `messaging`, before `notification`). This is the opposite of the rule for Task 3's master tables, and getting the two backwards is load-bearing in both directions.

- [ ] **Step 1: Write the model file**

```python
"""Per-tenant Daraja configuration, transaction ledger and refund register.

Replaces app/models/payhero.py. Table names go back to provider-neutral
mpesa_* because M-Pesa is the rail no matter who fronts it, and the next
provider change should not rename tables a third time.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class MpesaConfig(Base):
    """One row per tenant. Every secret column is Fernet-encrypted."""

    __tablename__ = "mpesa_configs"
    id = Column(Integer, primary_key=True)

    # The hospital's own PayBill or Buy Goods till. They already own it; this
    # UI records it, it does not create it.
    shortcode = Column(String(20), nullable=False)
    shortcode_type = Column(String(20), nullable=False, default="paybill")

    # 'sandbox' or 'production', per tenant: hospitals complete Safaricom
    # Go-Live on their own schedule, so a hospital sitting in sandbox while
    # its Go-Live is pending is a normal state, not a misconfiguration.
    environment = Column(String(20), nullable=False, default="sandbox")

    consumer_key_encrypted = Column(String(255), nullable=True)
    consumer_secret_encrypted = Column(String(255), nullable=True)
    passkey_encrypted = Column(String(255), nullable=True)

    # B2C only. initiator_password is stored (encrypted) rather than a
    # pre-generated SecurityCredential so a Safaricom certificate rotation is
    # a redeploy instead of a support ticket to every hospital.
    initiator_name = Column(String(80), nullable=True)
    initiator_password_encrypted = Column(String(255), nullable=True)

    # Daraja does not sign callbacks, so this unguessable token in the callback
    # path is one of the three things standing between us and a forged payment.
    # Rotatable, because a token in a URL leaks through logs and proxies in a
    # way a header secret does not.
    callback_token = Column(String(64), unique=True, index=True, nullable=True)
    callback_token_rotated_at = Column(DateTime(timezone=True), nullable=True)

    # Refund controls. Caps are enforced server-side, never in the UI alone.
    refunds_enabled = Column(Boolean, nullable=False, default=False)
    refund_max_amount = Column(Numeric(12, 2), nullable=False, default=10000)
    refund_daily_cap = Column(Numeric(12, 2), nullable=False, default=50000)
    refund_dual_approval_above = Column(Numeric(12, 2), nullable=False, default=5000)

    account_reference = Column(String(50), default="HMS-BILLING")
    transaction_desc = Column(String(100), default="Hospital Bill Payment")
    is_active = Column(Boolean, default=True)

    c2b_urls_registered_at = Column(DateTime(timezone=True), nullable=True)
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)


class MpesaTransaction(Base):
    """Inbound M-Pesa transaction log: STK pushes and direct-to-till payments."""

    __tablename__ = "mpesa_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)
    dispense_id = Column(Integer, ForeignKey("dispense_logs.dispense_id"), index=True, nullable=True)

    phone_number = Column(String(20), index=True, nullable=False)
    # The amount WE requested. The settlement cross-check compares the
    # callback's claimed amount against this and refuses to settle a mismatch.
    amount = Column(Numeric(12, 2), nullable=False)

    checkout_request_id = Column(String(100), index=True, nullable=True)
    merchant_request_id = Column(String(100), index=True, nullable=True)
    external_reference = Column(String(100), index=True, nullable=True)

    receipt_number = Column(String(50), unique=True, index=True, nullable=True)
    status = Column(String(50), default="Pending", index=True)
    result_desc = Column(String(255), nullable=True)

    # Proof the receipt was confirmed with Safaricom rather than merely
    # asserted by an unsigned callback. NULL means unverified: a C2B receipt
    # in that state is shown to a human and never posted to the ledger.
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_source = Column(String(30), nullable=True)  # 'stk_query' | 'transaction_status'

    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    transaction_type = Column(String(10), nullable=False, default="STK", index=True)
    bill_ref_number = Column(String(80), nullable=True, index=True)
    match_basis = Column(String(20), nullable=True, index=True)

    invoice = relationship("Invoice", backref="mpesa_transactions")

    __table_args__ = (
        Index("ix_mpesa_txn_status_date", "status", "transaction_date"),
    )


class MpesaRefund(Base):
    """B2C refund register. The only path by which money leaves a hospital."""

    __tablename__ = "mpesa_refunds"
    id = Column(Integer, primary_key=True)

    # Every refund points at the inbound receipt it reverses. The refundable
    # amount is that receipt minus refunds already completed or in flight,
    # computed under a row lock at approval time.
    source_transaction_id = Column(
        Integer, ForeignKey("mpesa_transactions.id"), index=True, nullable=False
    )
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)

    phone_number = Column(String(20), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(String(255), nullable=False)

    # Requested -> Approved -> Processing -> Completed | Failed | Reversed
    status = Column(String(20), nullable=False, default="Requested", index=True)

    # Minted once at creation and reused on every retry, so Safaricom
    # recognises a retried request as the same instruction rather than a
    # second one. This is the primary double-refund defence.
    originator_conversation_id = Column(String(64), unique=True, nullable=False)
    conversation_id = Column(String(64), index=True, nullable=True)
    transaction_receipt = Column(String(50), unique=True, index=True, nullable=True)
    result_desc = Column(String(255), nullable=True)

    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    source_transaction = relationship("MpesaTransaction")
```

- [ ] **Step 2: Register the module in the migrate script's import block**

In `backend/scripts/migrate_all_tenants.py` line 63, the list currently reads
`medical_history, messaging, notification, patient, payhero, radiology, referral,`.
Add `mpesa` in alphabetical position, giving
`medical_history, messaging, mpesa, notification, patient, payhero, radiology, referral,`.
Leave `payhero` for now; Task 12 removes it. These are tenant tables, so being in this list is correct and required.

- [ ] **Step 3: Write the alembic revision**

Create `backend/alembic/versions/e1f2a3b4c5d6_daraja_schema.py` with `down_revision = "c3d4e5f6a7b8"`.

The migration must tolerate three starting shapes, because a legacy tenant database may still carry `mpesa_*` names from before revision `aa2b7c3d8e91` renamed them to `payhero_*`:

```python
def _table_exists(conn, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


def upgrade() -> None:
    conn = op.get_bind()

    # Shape A: payhero_* present (the current state) -> rename in place, so
    # the data and the foreign keys survive.
    # Shape B: mpesa_* already present (a legacy tenant that never got the
    # payhero rename) -> leave the tables, add the new columns.
    # Shape C: neither -> create from scratch.
    for old, new in (
        ("payhero_configs", "mpesa_configs"),
        ("payhero_transactions", "mpesa_transactions"),
    ):
        if _table_exists(conn, old) and not _table_exists(conn, new):
            op.rename_table(old, new)

    if not _table_exists(conn, "mpesa_configs"):
        # Column-for-column from MpesaConfig in Step 1: same names, same types,
        # same nullability, same defaults. Do not paraphrase it. A migration
        # that disagrees with the model produces errors that only appear on a
        # tenant you did not test against.
        op.create_table("mpesa_configs", *_mpesa_config_columns())
    else:
        _add_columns_if_missing(conn, "mpesa_configs", _mpesa_config_columns())

Define `_mpesa_config_columns()` and `_mpesa_transaction_columns()` as
module-level helpers returning the full `sa.Column(...)` list, so the create
path and the add-missing path cannot drift apart. `_add_columns_if_missing`
inspects the live table and issues `op.add_column` only for absent names.

    # Same for mpesa_transactions, then create mpesa_refunds unconditionally
    # with a create-if-not-exists guard.
```

Write `_add_columns_if_missing` as a helper that inspects existing columns and issues `op.add_column` only for the ones absent. Drop the Pay Hero-specific columns (`payhero_channel_id`, `payhero_username_encrypted`, `payhero_password_encrypted`, `payhero_webhook_secret_encrypted`, `settlement_bank_code`, `settlement_bank_name`, `settlement_account_number`, `settlement_account_name`) only if they exist. Under Daraja there is no aggregator bank account to nominate: Safaricom pays the hospital's own shortcode.

`downgrade()` reverses the renames and drops `mpesa_refunds`.

- [ ] **Step 4: Write the schema test**

```python
# backend/tests/daraja/test_schema.py
from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.config.database import Base


def test_tables_registered_in_metadata():
    names = set(Base.metadata.tables)
    assert {"mpesa_configs", "mpesa_transactions", "mpesa_refunds"} <= names


def test_receipt_number_is_unique():
    """The replay defence. A repeated callback must not double-credit."""
    assert MpesaTransaction.__table__.c.receipt_number.unique is True


def test_originator_conversation_id_is_unique():
    """The double-refund defence."""
    assert MpesaRefund.__table__.c.originator_conversation_id.unique is True


def test_callback_token_is_unique():
    assert MpesaConfig.__table__.c.callback_token.unique is True


def test_no_plaintext_secret_columns():
    """Every credential column must carry the _encrypted suffix."""
    suspicious = {"consumer_key", "consumer_secret", "passkey", "initiator_password"}
    assert suspicious.isdisjoint(set(MpesaConfig.__table__.c.keys()))
```

- [ ] **Step 5: Run the migration against a scratch database and the tests**

Run: `cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja/test_schema.py -q`
Then run `./venv/bin/python -m alembic upgrade head` against a scratch tenant DB and confirm it is at `e1f2a3b4c5d6`. Then run it against a database that already has `payhero_*` tables and confirm the rename path works, and against an empty one and confirm the create path works. All three shapes must pass; a migration that only works on your laptop's database shape is not done.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/mpesa.py backend/alembic/versions/e1f2a3b4c5d6_daraja_schema.py backend/scripts/migrate_all_tenants.py backend/tests/daraja/test_schema.py
git commit -m "feat(daraja): tenant schema for config, transactions and refunds"
```

---

## Task 3: Master schema for the subscription rail

**Files:**
- Create: `backend/app/models/platform_mpesa.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (`MASTER_DB_PATCHES` only)
- Test: `backend/tests/daraja/test_master_schema.py`

**Do NOT add `platform_mpesa` to the import block in `migrate_all_tenants.py`.** That list feeds `Base.metadata`, and the script runs an unfiltered `create_all()` against every tenant engine, so listing it creates the operator's own billing tables inside every hospital database. `platform_payhero` is absent for exactly this reason, and so is `subscription_billing`. Master schema arrives through `MASTER_DB_PATCHES`.

- [ ] **Step 1: Write `platform_mpesa.py`**

Mirror `MpesaConfig` minus the tenant-specific fields, as a singleton `platform_mpesa_configs` row, plus `platform_mpesa_transactions` carrying `tenant_id`, `subscription_invoice_id` (nullable FK to `subscription_invoices.id`, the link into the receivables ledger shipped on 2026-08-29), `external_reference` unique, `checkout_request_id`, `receipt_number` unique, `status`, `period_label`, `initiated_by`, `initiated_at`, `settled_at`.

The `subscription_invoice_id` column is the whole point: a subscription STK payment must land as an `InvoicePayment` row against a real invoice, not as an untracked receipt sitting in a parallel table.

- [ ] **Step 2: Add the MASTER_DB_PATCHES entries**

Follow the existing `platform_payhero_configs` block in `migrate_all_tenants.py` (around line 212) exactly: `CREATE TABLE IF NOT EXISTS`, then `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for anything added later, then `CREATE INDEX IF NOT EXISTS`. Every statement must be idempotent, because these run on every deploy.

- [ ] **Step 3: Write the test that the master model is NOT in tenant metadata**

```python
def test_platform_tables_are_not_created_in_tenant_databases():
    """Regression guard for the footgun this codebase has hit twice.

    If app.models.platform_mpesa ever lands in the migrate script's import
    block, create_all() puts the operator's billing tables in every hospital
    database. This test reads the script's source rather than its runtime
    metadata, because the failure is a source-level edit.
    """
    src = (Path(__file__).parents[2] / "scripts" / "migrate_all_tenants.py").read_text()
    import_block = src.split("from app.models import (")[1].split(")")[0]
    assert "platform_mpesa" not in import_block
    assert "platform_mpesa_configs" in src  # but it IS in MASTER_DB_PATCHES
```

- [ ] **Step 4: Run and commit**

```bash
cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja -q
git add backend/app/models/platform_mpesa.py backend/scripts/migrate_all_tenants.py backend/tests/daraja/test_master_schema.py
git commit -m "feat(daraja): master schema for the subscription rail, wired to receivables"
```

---

## Task 4: Callback authentication

**Files:**
- Create: `backend/app/core/daraja_callback.py`
- Test: `backend/tests/daraja/test_callback_auth.py`

**Interfaces:**
- Produces:
  - `mint_callback_token() -> str`
  - `resolve_tenant_by_token(token: str) -> str | None` returning a tenant db_name
  - `async verify_daraja_source(request: Request) -> bytes` raising on a disallowed IP
  - `ACK_OK` / `ACK_REJECT` acknowledgement bodies

This task is the reason the spec exists. Read the spec section "The one thing that makes this harder than it looks" before writing a line.

- [ ] **Step 1: Write the security tests first, and make them the real ones**

```python
# backend/tests/daraja/test_callback_auth.py

def test_unknown_callback_token_is_rejected():
    """A forged callback with a guessed URL must not reach settlement."""

def test_tenant_database_name_is_not_accepted_as_a_token():
    """The Pay Hero design keyed callbacks on the tenant db_name, which is
    guessable. Carrying that forward to an unsigned protocol would let anyone
    who guesses 'mayoclinic_db' mint payments. Explicitly assert it fails."""

def test_correct_token_from_disallowed_ip_is_rejected():

def test_x_forwarded_for_is_only_trusted_behind_a_configured_proxy():
    """Ported from the Pay Hero tests, which got this right. A direct public
    caller must not be able to spoof XFF to dodge the allow-list."""

def test_production_with_empty_allowlist_fails_closed():

def test_rejected_callback_still_returns_200():
    """Safaricom retries non-200s, and on C2B validation a non-200 can decline
    the customer's payment at the till. We reject in our own records and
    acknowledge on theirs."""

def test_token_rotation_invalidates_the_old_token():
```

- [ ] **Step 2: Implement, reusing what already works**

Port `_parse_cidrs`, `_peer_is_trusted_proxy` and `_client_ip` from `app/core/payhero_webhook.py` verbatim. That module's `X-Forwarded-For` handling is already correct (audit H-4) and rewriting it from memory risks reintroducing the bug it fixed. Drop the HMAC functions: there is no signature to verify.

`mint_callback_token` uses `secrets.token_urlsafe(32)`. `resolve_tenant_by_token` looks the token up across tenant databases using the same master-registry pattern as `_resolve_tenant_db` in `routes/payhero_payment.py:238`, and caches negative lookups briefly so a token-guessing flood cannot turn into a database scan per request.

Acknowledgement bodies:

```python
ACK_OK = {"ResultCode": 0, "ResultDesc": "Accepted"}
# Even a rejection is acknowledged, for the reasons in the test above.
ACK_REJECT = {"ResultCode": 0, "ResultDesc": "Accepted"}
# C2B validation is the one place a rejection is expressed to Safaricom,
# because there it means "do not accept this payment at the till".
ACK_C2B_DECLINE = {"ResultCode": "C2B00016", "ResultDesc": "Rejected"}
```

- [ ] **Step 3: Update the CSRF exemption list and its comment**

In `backend/app/main.py`, `_CSRF_EXEMPT_PATHS` (line 270) currently exempts `/api/payments/payhero/callback` and the comment above it says "Authentication on those paths is HMAC signature based, not session based". **That comment becomes false under Daraja.** Replace the path with `/api/payments/mpesa/` and rewrite the comment to state the actual model: an unguessable rotatable token in the path, a Safaricom IP allow-list, and a settlement cross-check that never trusts the callback's claimed amount. A stale comment about a security property that no longer holds is worse than no comment.

- [ ] **Step 4: Run and commit**

```bash
git commit -m "feat(daraja): callback authentication without a signature to verify"
```

---

## Task 5: STK Push, STK Query, and the settlement cross-check

**Files:**
- Create: `backend/app/services/daraja/stk.py`, `backend/app/services/daraja/settlement.py`
- Test: `backend/tests/daraja/test_stk.py`, `backend/tests/daraja/test_settlement.py`

**Interfaces:**
- Consumes: `DarajaClient`, `stk_password`, `daraja_timestamp`, `normalize_msisdn` (Task 1); `MpesaConfig`, `MpesaTransaction` (Task 2).
- Produces:
  - `initiate_stk_push(db, *, phone_number, amount, invoice_id=None, dispense_id=None, ...) -> dict` returning `{"checkout_request_id", "merchant_request_id", "external_reference", "transaction_id"}`
  - `query_stk(db, *, checkout_request_id) -> dict`
  - `apply_stk_callback(db, payload: dict) -> MpesaTransaction | None`
  - `settle_invoice_match(db, *, invoice, txn, match_basis, user_id=None) -> Payment`

- [ ] **Step 1: Write the settlement cross-check test FIRST**

This is the single most important test in the migration. Write it before any implementation.

```python
def test_callback_claiming_a_different_amount_is_quarantined_not_settled():
    """Daraja callbacks are unsigned. If a callback claims KES 50,000 against
    a push we made for KES 500, the only safe response is to refuse to settle
    and flag it. Trusting the callback here is the whole attack."""
    txn = _pending_transaction(amount=Decimal("500.00"))
    payload = _stk_callback(checkout_request_id=txn.checkout_request_id,
                            amount=Decimal("50000.00"), receipt="ABC123")
    result = apply_stk_callback(db, payload)
    assert result.status == "Quarantined"
    assert db.query(Payment).count() == 0
    assert result.receipt_number is None  # nothing claimed against the receipt


def test_callback_with_no_matching_pending_transaction_is_ignored():
    """No pending record means we never initiated this. It is either a
    forgery or a callback for another deployment."""


def test_replayed_callback_is_a_no_op():
    """Safaricom retries. A second delivery of a settled receipt must not
    create a second Payment."""
    apply_stk_callback(db, payload)
    first = db.query(Payment).count()
    apply_stk_callback(db, payload)
    assert db.query(Payment).count() == first


def test_matching_amount_settles_and_posts_to_the_ledger():


def test_failed_result_code_marks_failed_without_a_payment():
```

- [ ] **Step 2: Run to verify they fail, then implement**

The STK payload:

```python
payload = {
    "BusinessShortCode": config.shortcode,
    "Password": stk_password(config.shortcode, passkey, timestamp),
    "Timestamp": timestamp,
    "TransactionType": (
        "CustomerBuyGoodsOnline" if config.shortcode_type == "till"
        else "CustomerPayBillOnline"
    ),
    "Amount": int(Decimal(str(amount))),   # Daraja takes whole shillings
    "PartyA": msisdn,
    "PartyB": config.shortcode,
    "PhoneNumber": msisdn,
    "CallBackURL": f"{base}/api/payments/mpesa/stk/callback/{config.callback_token}",
    "AccountReference": account_reference[:12],  # Daraja truncates past 12
    "TransactionDesc": (transaction_desc or "Payment")[:13],
}
```

`AccountReference` and `TransactionDesc` have hard length limits that Daraja
enforces with an opaque error. Truncate here, deliberately, rather than
discovering it in production.

Persist the `MpesaTransaction` with `status="Pending"` and the returned
`CheckoutRequestID` **before** returning, so a callback that arrives before our
own commit still finds a row. Commit before the HTTP response is written.

`apply_stk_callback` order of operations, which is the safety property:

1. Extract `CheckoutRequestID` from `Body.stkCallback`.
2. Find the `Pending` transaction by that id. **No row: log and return None.** Do not create one.
3. `ResultCode != 0`: mark `Failed` with `ResultDesc`, return.
4. Read `Amount` and `MpesaReceiptNumber` from `CallbackMetadata.Item`.
5. **Compare the callback amount against `txn.amount`. Mismatch: set `status="Quarantined"`, record the claim in `result_desc`, notify `billing:manage`, return without settling.**
6. Receipt already present on another settled transaction: return, it is a replay.
7. Set `receipt_number`, `verified_at`, `verification_source="stk_callback"`, `status="Success"`, then settle.

Port `settle_invoice_match` from `services/payhero_service.py:255` largely intact
(it is correct, and idempotent on `Payment.transaction_reference`), changing the
`post_from_event` source key to `billing.payment.mpesa` and **removing the em dash
from the notification body** on that function's `receipt {…or '—'}` line: use
`"not recorded"`.

- [ ] **Step 3: Run the tests, then commit**

```bash
git commit -m "feat(daraja): STK push and query, with a settlement cross-check that distrusts callbacks"
```

---

## Task 6: C2B register, validation and confirmation

**Files:**
- Create: `backend/app/services/daraja/c2b.py`, `backend/app/services/daraja/status.py`
- Test: `backend/tests/daraja/test_c2b.py`, `backend/tests/daraja/test_status.py`

**Interfaces:**
- Produces:
  - `register_c2b_urls(db) -> dict`
  - `handle_validation(db, payload) -> bool`
  - `handle_confirmation(db, payload) -> MpesaTransaction`
  - `query_transaction_status(db, *, receipt) -> dict`
  - `verify_receipt(db, *, txn) -> bool`
  - `account_balance(db) -> dict` returning the shortcode's utility and working
    balances, so an operator can see the B2C float before promising a refund.
    Called on demand from the admin UI, never on the refund hot path: Daraja
    returns the balance asynchronously on a result callback, so this records a
    request and the value arrives like any other callback.

- [ ] **Step 1: Write the verification test first**

```python
def test_c2b_confirmation_is_not_posted_to_the_ledger_until_verified():
    """A C2B confirmation has no prior record by definition: the customer just
    walked up and paid the till. Since the callback is unsigned, the receipt is
    verified against Daraja's Transaction Status API before any money moves.
    Unverified receipts sit on the unmatched queue for a human."""
    payload = _c2b_confirmation(receipt="XYZ789", amount="1500")
    with _daraja_status_returns(found=False):
        txn = handle_confirmation(db, payload)
    assert txn.verified_at is None
    assert txn.status == "Unverified"
    assert db.query(Payment).count() == 0


def test_verified_c2b_confirmation_matches_and_settles():


def test_c2b_matching_falls_through_bill_ref_then_opd_then_phone():
    """Match order: the PayBill account number the customer typed, then an OPD
    number, then the phone. Anything unmatched goes to the queue rather than
    being guessed at."""
```

- [ ] **Step 2: Implement**

`register_c2b_urls` calls `/mpesa/c2b/v1/registerurl` with `ShortCode`,
`ResponseType: "Completed"`, `ConfirmationURL` and `ValidationURL` built from the
tenant's callback token. Record `c2b_urls_registered_at`. Note in a comment that
Safaricom only enables the validation URL on request, and until they do, only
confirmation fires; the code must work correctly in both cases.

`handle_confirmation` matches in the documented order and calls `verify_receipt`
before settling. `verify_receipt` calls Transaction Status and requires both that
Safaricom knows the receipt and that its amount equals the confirmation's claim.

- [ ] **Step 3: Run and commit**

```bash
git commit -m "feat(daraja): C2B with Transaction Status verification before settlement"
```

---

## Task 7: B2C refunds

**Files:**
- Create: `backend/app/services/daraja/b2c.py`, `backend/app/routes/mpesa_refunds.py`
- Test: `backend/tests/daraja/test_refunds.py`

**Interfaces:**
- Produces:
  - `request_refund(db, *, source_transaction_id, amount, reason, user_id) -> MpesaRefund`
  - `approve_refund(db, *, refund_id, user_id) -> MpesaRefund`
  - `dispatch_refund(db, *, refund) -> MpesaRefund`
  - `handle_b2c_result(db, payload) -> MpesaRefund | None`
  - `handle_b2c_timeout(db, payload) -> MpesaRefund | None`
  - `refundable_amount(db, *, txn) -> Decimal`

This is the only path by which money leaves a hospital. Every control below is load-bearing; none is optional.

- [ ] **Step 1: Write the control tests first**

```python
def test_refund_cannot_exceed_the_original_receipt():

def test_refund_cannot_exceed_the_receipt_minus_refunds_already_in_flight():
    """Two concurrent requests for 60% each of a receipt must not both pass.
    refundable_amount is computed under SELECT ... FOR UPDATE on the source
    transaction for exactly this reason."""

def test_over_per_transaction_cap_is_rejected():

def test_over_rolling_24h_cap_is_rejected():

def test_requester_cannot_approve_their_own_refund_above_the_threshold():

def test_refund_permission_is_separate_from_billing_manage():
    """Being able to take a payment must not imply being able to send one back."""

def test_retry_reuses_the_originator_conversation_id():
    """The primary double-refund defence: Safaricom recognises a retried
    request as the same instruction rather than a second one."""

def test_b2c_timeout_moves_to_processing_not_failed():
    """Treating a queue timeout as a failure is how a system refunds twice.
    A timeout means 'we do not know yet', and reconciliation resolves it."""
    handle_b2c_timeout(db, payload)
    assert refund.status == "Processing"

def test_b2c_result_success_records_the_receipt_and_completes():

def test_disabled_refunds_reject_at_the_service_layer_not_just_the_ui():
```

- [ ] **Step 2: Implement**

The B2C payload:

```python
payload = {
    "OriginatorConversationID": refund.originator_conversation_id,
    "InitiatorName": config.initiator_name,
    "SecurityCredential": security_credential(initiator_password, config.environment),
    # BusinessPayment is the correct code for a refund. PromotionPayment and
    # SalaryPayment produce the wrong message on the recipient's handset.
    "CommandID": "BusinessPayment",
    "Amount": int(refund.amount),
    "PartyA": config.shortcode,
    "PartyB": refund.phone_number,
    "Remarks": refund.reason[:100],
    "QueueTimeOutURL": f"{base}/api/payments/mpesa/b2c/timeout/{config.callback_token}",
    "ResultURL": f"{base}/api/payments/mpesa/b2c/result/{config.callback_token}",
    "Occasion": f"REFUND-{refund.id}",
}
```

Add `mpesa:refund` to `PERMISSION_CATALOG` in `services/tenant_provisioning.py:230`
and grant it in `ROLE_GRANTS` to Admin only, deliberately not to the billing role
that holds `billing:manage`.

- [ ] **Step 3: Run and commit**

```bash
git commit -m "feat(daraja): B2C refunds with caps, dual approval and timeout-safe state"
```

---

## Task 8: Reconciliation

**Files:**
- Create: `backend/app/services/daraja/reconcile.py`, `backend/app/cli/run_reconcile.py`
- Modify: `render.yaml`
- Test: `backend/tests/daraja/test_reconcile.py`

- [ ] **Step 1: Implement, reusing the billing-lock pattern**

Copy the advisory-lock approach from `app/services/subscription_billing.py`, including its **dedicated connection**: the lock must be taken on a connection held across every commit and closed in a `finally`, not on the pooled ORM session. Taking a session-level lock and then committing returns the connection to the pool and can strand the lock, which in the billing case would have caused a permanent silent outage. That fix is in commit `6560dae`; read it before writing this.

Resolve: transactions `Pending` over 5 minutes via STK Query, refunds `Processing` over 10 minutes via Transaction Status, and surface anything unresolved after 24 hours on the operator health panel rather than retrying forever.

Return a result object carrying per-tenant failures, following `BillingRunResult`. A reconciliation job that logs "0 resolved" and exits 0 while every tenant failed is the same silent-failure bug the receivables work already had once.

- [ ] **Step 2: Add the cron to render.yaml**

Mirror the `medifleet-billing` block. Every 15 minutes. Note in a comment, as that block does, that `DATABASE_URL` is `sync: false` and must be set in the dashboard.

- [ ] **Step 3: Run and commit**

---

## Task 9: Tenant routes

**Files:**
- Create: `backend/app/routes/mpesa_payment.py`, `backend/app/routes/mpesa_admin.py`
- Modify: `backend/app/main.py` (router registration), `backend/app/core/modules.py`
- Test: `backend/tests/daraja/test_routes.py`

- [ ] **Step 1: Port the route shapes from the Pay Hero equivalents**

`routes/payhero_payment.py` and `routes/payhero_admin.py` are the reference. Keep the background-task pattern for callback processing (acknowledge fast, work after), the unmatched queue, and the manual-assign endpoint. Replace the single callback with the five token-addressed endpoints from the spec.

Config responses must never echo a secret. Return booleans (`has_consumer_key: true`) and last-four fragments, never the value.

- [ ] **Step 2: Register the module**

In `core/modules.py`, change the `payhero` `ModuleDef` to `mpesa` with label "M-Pesa Payments", and add both `/api/admin/mpesa/` and `/api/payments/mpesa/` to the URL prefix map. Keep the legacy alias block that maps an old `mpesa` flag forward, extending it so a `payhero` flag also maps to `mpesa`. Existing hospitals must not lose the module because a key changed.

- [ ] **Step 3: Run and commit**

---

## Task 10: Superadmin and the subscription rail

**Files:**
- Create: `backend/app/routes/mpesa_superadmin.py`, `backend/app/routes/platform_mpesa.py`
- Test: `backend/tests/daraja/test_platform_rail.py`

- [ ] **Step 1: Write the cross-rail test first**

```python
def test_subscription_stk_payment_creates_an_invoice_payment_row():
    """The point of the whole platform rail: a paid subscription STK must land
    in the receivables ledger against a real invoice, not in a parallel table
    nobody ages."""
    invoice = _open_subscription_invoice(amount=Decimal("18500"))
    txn = _platform_push(invoice=invoice, amount=Decimal("18500"))
    apply_platform_callback(master_db, _stk_callback(txn, receipt="PLT123"))
    payments = master_db.query(InvoicePayment).filter_by(invoice_id=invoice.id).all()
    assert len(payments) == 1
    assert payments[0].amount == Decimal("18500")
    assert outstanding_balance(master_db, invoice) == Decimal("0")
```

Use the real `outstanding_balance` from `app/services/subscription_billing.py`, not a reimplementation. The ledger is the authority on what "paid" means.

- [ ] **Step 2: Implement, and default the platform config to sandbox**

MediFleet holds no Daraja credentials (spec, "Credentials: answered"), so the platform config ships with `environment="sandbox"` and no credentials, and the health endpoint reports it as "not configured" rather than "broken". Configuring it later is a form submission, not a deploy.

- [ ] **Step 3: Run and commit**

---

## Task 11: Frontend

**Files:**
- Rewrite: `frontend/src/pages/MpesaSettings.jsx`
- Create: `frontend/src/pages/billing/Refunds.jsx`, `frontend/src/api/mpesa.js`
- Modify: `frontend/src/components/PlatformHealth.jsx`, `App.jsx`, `MainLayout.jsx`, `ModuleGuard.jsx`, `Billing.jsx`, `Pharmacy.jsx`
- Test: `frontend/src/pages/MpesaSettings.test.jsx`, `frontend/src/pages/billing/Refunds.test.jsx`

- [ ] **Step 1: Rebuild MpesaSettings against the Daraja config**

Sections: shortcode and type, environment with an explicit warning when a production deployment holds a sandbox tenant, credentials (write-only fields showing only whether a value is set), callback URLs with a copy action and a rotate-token action behind a confirm, refund controls, and the test push.

The rotate action must state its consequence in the UI: rotating invalidates the URLs currently registered with Safaricom, so C2B URLs must be re-registered afterwards. Offer to do it in the same action.

Delete the settlement-bank section and the bank dropdown entirely.

- [ ] **Step 2: Refunds page**

List, request, approve. Hide the approve control from the requesting user above the dual-approval threshold, and rely on the server to enforce it: the UI hint is a courtesy, the server rule is the control.

- [ ] **Step 3: PlatformHealth checks**

Replace the Pay Hero blocker checks with: credentials present per tenant, C2B URLs registered, any active tenant on sandbox while the deployment is production, unresolved transactions older than 24 hours, refunds stuck in `Processing`.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run build && npx vitest run --no-file-parallelism && npm run lint
```

Run ESLint explicitly. `vite build` does not surface `no-undef`, and this task adds new imports across seven files.

- [ ] **Step 5: Commit**

---

## Task 12: Remove Pay Hero

**Files:**
- Delete: `backend/app/services/payhero_service.py`, `payhero_banks.py`, `platform_payhero_service.py`, `backend/app/core/payhero_webhook.py`, `backend/app/models/payhero.py`, `platform_payhero.py`, `backend/app/routes/payhero_admin.py`, `payhero_payment.py`, `payhero_superadmin.py`, `platform_payhero.py`
- Modify: `settings.py`, `main.py`, `modules.py`, `dependencies.py`, `circuit.py`, `migrate_all_tenants.py`, `tenant_provisioning.py`, `log_redact.py`, `accounting.py`, `billing.py`, `pharmacy.py`, `schemas/billing.py`, `schemas/pharmacy.py`, `accounting_backfill.py`, `alembic/env.py`
- Delete tests: `tests/accounting/test_payhero_callback_guards.py`, `test_payhero_webhook_ip.py` (their coverage is replaced by `tests/daraja/test_callback_auth.py`; confirm each assertion has an equivalent there before deleting, and port any that does not)

Do this LAST. Until this task, both integrations coexist and nothing is broken mid-flight.

- [ ] **Step 1: Delete the modules and drop the router registrations**

- [ ] **Step 2: Settings**

Remove every `PAYHERO_*` key. Add `DARAJA_WEBHOOK_CIDRS` and `DARAJA_TRUSTED_PROXIES`. **Keep the `PAYHERO_*` keys as declared-but-unread compat shims for one release**, exactly as the codebase already does for the legacy `MPESA_*` keys at `settings.py:208`, so a deploy against a stale `.env` does not trip pydantic's `extra="forbid"` and take the API down on boot. Comment them the same way: "NO CODE READS THESE".

- [ ] **Step 3: Remove `payhero` from the migrate script import block and the `payhero:manage` permission**

Keep `RequirePermission`'s variadic any-of accepting `mpesa:manage`, `payhero:manage` during the transition. Removing the old codename from the accept list in the same release that renames it races the permission data migration against the deploy.

- [ ] **Step 4: Sweep for em dashes in every file touched**

```bash
grep -rn "—" backend/app/services/daraja backend/app/routes/mpesa* backend/app/models/mpesa* frontend/src/pages/MpesaSettings.jsx
```

Expected: no output.

- [ ] **Step 5: Full verification and commit**

```bash
cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja tests/accounting -q
cd ../frontend && npm run build && npx vitest run --no-file-parallelism && npm run lint
```

---

## Task 13: Production smoke-test procedure

**Files:**
- Create: `docs/runbooks/daraja-go-live.md`

Nothing in this migration can be verified against production M-Pesa before merge, because neither MediFleet nor any hospital holds production credentials. The first real transaction will be a human with a handset. Write that down so it is repeatable.

- [ ] **Step 1: Write the runbook**

Cover, in order: obtaining credentials from the Safaricom portal, entering them, registering C2B URLs, confirming the callback URL is reachable from the public internet, a KES 1 STK push to a real handset, confirming the receipt lands and the invoice settles, a KES 1 refund back, confirming reconciliation resolves a deliberately-dropped callback, and the rollback (set `is_active = false`, which stops new pushes without touching data).

Include the two things that will actually go wrong: the callback URL not being publicly reachable, and the `SecurityCredential` being generated against the wrong environment's certificate.

- [ ] **Step 2: Commit**

---

## Global verification before the PR

```bash
cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja tests/accounting -q
./venv/bin/python -m alembic upgrade head          # single head
cd ../frontend && npm run build && npx vitest run --no-file-parallelism && npm run lint
grep -rn "—" backend/app/services/daraja backend/app/routes/mpesa* frontend/src/pages/MpesaSettings.jsx
```

This branch touches `backend/app/models/**` and `backend/alembic/**`, so `migrate-all-tenants` runs and is a required check. Open the PR against `development`.

---

## Task 14: Per-department tills, and safe concurrency on one till

**Runs immediately after Task 5, BEFORE Task 6.** Tasks 6, 7, 9 and 11 all consume the config-resolution seam and the transaction-to-till link this task establishes. Doing it later means reworking each of them.

**Spec:** the sections "Per-department tills" and "Many terminals, one till" in `docs/superpowers/specs/2026-08-29-daraja-migration-design.md`. Read both before starting.

**Files:**
- Create: `backend/alembic/versions/f2a3b4c5d6e7_department_tills.py` (a NEW revision on top of `e1f2a3b4c5d6`, NOT an amendment: `e1f2a3b4c5d6` has been reviewed twice against three tenant-database shapes and reopening it risks verified work)
- Modify: `backend/app/models/mpesa.py`, `backend/app/services/daraja/stk.py`, `backend/app/routes/mpesa_payment.py` (if it exists yet)
- Test: `backend/tests/daraja/test_department_tills.py`, `backend/tests/daraja/test_concurrency.py`

**Interfaces:**
- Consumes: `config_for(db, *, department_id=None)` from Task 5, `MpesaConfig`, `MpesaTransaction`.
- Produces: `config_for` with real department resolution; `MpesaTransaction.mpesa_config_id`.

- [ ] **Step 1: Schema**

On `MpesaConfig`:
```python
department_id = Column(
    Integer,
    ForeignKey("departments.department_id", ondelete="SET NULL"),
    nullable=True, index=True,
)
```
NULL means the hospital-wide default.

Two partial unique indexes, because Postgres treats NULLs as distinct so a plain unique index will NOT stop two default rows:
```sql
CREATE UNIQUE INDEX uq_mpesa_configs_department ON mpesa_configs (department_id)
    WHERE department_id IS NOT NULL;
CREATE UNIQUE INDEX uq_mpesa_configs_default ON mpesa_configs ((department_id IS NULL))
    WHERE department_id IS NULL;
```

On `MpesaTransaction`:
```python
mpesa_config_id = Column(Integer, ForeignKey("mpesa_configs.id"), index=True, nullable=True)
```
Which till took the money. Without it a refund cannot know which till to pay back from, and reconciliation cannot tell two tills apart.

The migration must backfill: every existing `mpesa_configs` row becomes the default (`department_id` stays NULL), and existing transactions point at it. Any tenant with more than one existing config row is a state that cannot occur today (the table was singleton by construction), so assert it rather than guessing: fail the migration loudly with the tenant name if found.

- [ ] **Step 2: Real resolution in `config_for`**

```python
def config_for(db: Session, *, department_id: int | None = None) -> MpesaConfig:
    """The till that should take this payment.

    A department's own till when it has one and it is active, otherwise the
    hospital-wide default. The fallback is what lets a hospital start with one
    till and split departments out later without a migration per department.
    """
```
Resolution order: the department's active row, then the default row, then raise the existing "not configured" HTTPException. An INACTIVE department row falls back to the default rather than failing: a department that switches its till off should keep collecting, not stop collecting.

- [ ] **Step 3: Concurrency guard, the partial unique index**

```sql
CREATE UNIQUE INDEX uq_mpesa_txn_one_pending_per_invoice ON mpesa_transactions (invoice_id)
    WHERE status = 'Pending' AND invoice_id IS NOT NULL;
CREATE UNIQUE INDEX uq_mpesa_txn_one_pending_per_dispense ON mpesa_transactions (dispense_id)
    WHERE status = 'Pending' AND dispense_id IS NOT NULL;
```

In `initiate_stk_push`, catch the `IntegrityError` from that index and return the EXISTING pending transaction rather than raising. A second terminal pushing the same invoice must be told "a prompt is already on its way", not handed an error, and must not cause a second prompt on the patient's handset.

Do the insert-and-catch rather than a check-then-insert: a check-then-insert has a race between the check and the insert, which is the precise failure this task exists to close.

- [ ] **Step 4: Wrap STK initiation in the EXISTING idempotency mechanism**

Use `app/core/idempotency.py` and `IdempotencyKey`. Do NOT build a second mechanism, and do NOT add an `idempotency_key` column to `mpesa_transactions`.

Read `app/core/idempotency.py` first and follow how existing endpoints use it. The scope is (user_id, endpoint, key) with a SHA-256 fingerprint of the body, and reusing a key with a different body returns 409 rather than a wrong cached answer. That per-user scope is correct: two different cashiers pressing their own buttons are two genuine actions, not one retried.

- [ ] **Step 5: Tests, and prove the concurrency ones**

```
test_department_with_its_own_till_uses_it
test_department_without_a_till_falls_back_to_the_hospital_default
test_inactive_department_till_falls_back_rather_than_failing
test_no_config_at_all_raises_not_configured
test_two_default_rows_are_rejected_by_the_database
test_two_configs_for_one_department_are_rejected_by_the_database
test_transaction_records_which_till_took_the_money

test_two_terminals_pushing_the_same_invoice_produce_one_pending_transaction
test_the_second_terminal_receives_the_existing_transaction_not_an_error
test_a_stale_pending_transaction_does_not_block_a_genuine_retry
test_repeated_submit_with_the_same_idempotency_key_pushes_once
test_same_idempotency_key_with_a_different_body_returns_409
test_two_different_cashiers_are_separate_idempotency_scopes
```

The two-terminal test must be GENUINELY concurrent: two threads, two separate database sessions and connections, and a `threading.Barrier` so both reach the insert together. Then prove it: drop the partial unique index, confirm the test fails with two pending rows, restore it, confirm it passes. Report that evidence verbatim.

A sequential test here proves nothing, because the bug only exists when two inserts overlap. This project has already shipped one concurrency test that passed against its own bug, and caught it only because a reviewer reverted the implementation.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(daraja): per-department tills with a hospital default, and one pending push per invoice"
```

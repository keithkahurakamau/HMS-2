"""Transaction Status and Account Balance, the two Daraja queries that answer
"what actually happened" rather than initiate something new.

Transaction Status is what makes C2B safe. A C2B confirmation has no prior
record: the customer just walked up and paid the till, so there is nothing
local to compare an unsigned callback against. verify_receipt closes that gap
by asking Safaricom directly, for the one receipt the confirmation claims,
before app/services/daraja/c2b.py posts anything to the ledger. It requires
BOTH that Safaricom knows the receipt and that the amount it reports equals
the amount the confirmation claimed; either failing means unverified, never
"probably fine".

Honest caveat about the real Daraja Transaction Status API: its documented
behaviour is asynchronous. The synchronous response to
POST /mpesa/transactionstatus/v1/query is only an acknowledgment that the
request was accepted for processing (or a same-request validation error);
the actual verdict is meant to arrive later on ResultURL. This module
currently treats the synchronous response itself as authoritative, which is
what lets a C2B confirmation be verified inline rather than left pending on a
callback route this task does not build. If a future task wires up a real
ResultURL handler for Transaction Status, this is the seam to revisit: the
right fix is for that handler to update MpesaTransaction.verified_at when the
async result lands, not to remove this synchronous check, since something
must still decide within handle_confirmation whether to settle immediately.

Account Balance is a genuinely async, low-frequency admin query: Safaricom
never answers it in the synchronous response either, and this module makes
no attempt to pretend otherwise. account_balance submits the request and
returns None for both balances, because a value we do not have must never be
shown as zero (a hospital reading "zero float" when the real answer is
"Safaricom has not replied yet" is a materially different, misleading fact).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.client import DarajaClient, DarajaError
from app.services.daraja.credentials import security_credential
from app.services.daraja.reservation import config_for
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

_IDENTIFIER_TYPE_SHORTCODE = "4"


def _decrypted(value: Optional[str], *, field: str) -> str:
    """Shared with c2b.py: decrypt a config secret, or raise a clear 400
    instead of letting a missing credential surface as an opaque failure
    deep inside a Daraja call."""
    plain = decrypt_data(value) if value else None
    if not plain:
        raise HTTPException(
            status_code=400,
            detail=f"M-Pesa {field} is not configured for this hospital.",
        )
    return plain


def _daraja_client(config: MpesaConfig) -> DarajaClient:
    """Build the DarajaClient for `config`. Ported verbatim from stk.py's
    helper of the same name and purpose (not imported from there: stk.py
    should not become a dependency of every other Daraja module just to
    reuse six lines, and this file needs it for Transaction Status and
    Account Balance the same way stk.py needs it for STK push and query)."""
    creds = SimpleNamespace(
        consumer_key=_decrypted(config.consumer_key_encrypted, field="consumer key"),
        consumer_secret=_decrypted(config.consumer_secret_encrypted, field="consumer secret"),
        environment=config.environment,
        shortcode=config.shortcode,
    )
    return DarajaClient(creds)


def _initiator_credentials(config: MpesaConfig) -> tuple[str, str]:
    """(Initiator, SecurityCredential) for a B2C-style command. Transaction
    Status and Account Balance both authenticate as an API operator the same
    way B2C does, not as the OAuth consumer key/secret alone."""
    if not config.initiator_name:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa initiator name is not configured for this hospital.",
        )
    initiator_password = _decrypted(
        config.initiator_password_encrypted, field="initiator password"
    )
    credential = security_credential(initiator_password, config.environment)
    return config.initiator_name, credential


def _base_hint_token(config: MpesaConfig, callback_tenant: Optional[str]) -> tuple[str, str, str]:
    """(base_url, quoted_tenant_hint, quoted_token) shared by every URL this
    module and c2b.py build. Same validation as stk.py's _callback_url: fail
    loudly on missing configuration rather than send Safaricom a broken URL.
    """
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")
    if settings.is_production and not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL must be HTTPS in production.")
    if not callback_tenant:
        raise HTTPException(
            status_code=500,
            detail="Missing tenant routing hint for the M-Pesa callback URL.",
        )
    if not config.callback_token_encrypted:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa callback token has not been generated yet for this hospital.",
        )
    token = decrypt_data(config.callback_token_encrypted)
    hint = quote(callback_tenant.strip(), safe="")
    return base, hint, quote(token, safe="")


def _flow_urls(
    config: MpesaConfig, callback_tenant: Optional[str], *, flow: str
) -> tuple[str, str]:
    """(ResultURL, QueueTimeOutURL) for an async Daraja command. `flow` is a
    path segment ("status" or "balance"), not a shortcode or receipt, so it
    never needs redaction the way a token does."""
    base, hint, token = _base_hint_token(config, callback_tenant)
    result_url = f"{base}/api/payments/mpesa/{flow}/result/{hint}/{token}"
    timeout_url = f"{base}/api/payments/mpesa/{flow}/timeout/{hint}/{token}"
    return result_url, timeout_url


def _config_for_receipt(db: Session, *, receipt: str) -> MpesaConfig:
    """The till that took `receipt`, so Transaction Status is signed with the
    same shortcode/credentials the payment actually landed on. Falls back to
    config_for's hospital default only when there is no transaction row yet
    to ask (the receipt is being verified for the very first time, from
    inside handle_confirmation, which sets mpesa_config_id before calling
    verify_receipt) or it predates mpesa_config_id."""
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.receipt_number == receipt)
        .first()
    )
    if txn is not None and txn.mpesa_config_id is not None:
        config = db.query(MpesaConfig).filter(MpesaConfig.id == txn.mpesa_config_id).first()
        if config is not None:
            return config
    return config_for(db)


def query_transaction_status(
    db: Session, *, receipt: str, callback_tenant: Optional[str] = None
) -> dict:
    """Ask Safaricom about `receipt` directly. See the module docstring's
    caveat: the synchronous response is treated as the verdict here, which is
    a simplification against Daraja's documented async behaviour.

    Returns Daraja's raw response. Does not itself decide verified or not;
    verify_receipt is what interprets the response against an expected
    amount."""
    if not receipt:
        raise HTTPException(status_code=400, detail="receipt is required")

    config = _config_for_receipt(db, receipt=receipt)
    initiator, credential = _initiator_credentials(config)
    result_url, timeout_url = _flow_urls(config, callback_tenant, flow="status")

    payload = {
        "Initiator": initiator,
        "SecurityCredential": credential,
        "CommandID": "TransactionStatusQuery",
        "TransactionID": receipt,
        "PartyA": config.shortcode,
        "IdentifierType": _IDENTIFIER_TYPE_SHORTCODE,
        "ResultURL": result_url,
        "QueueTimeOutURL": timeout_url,
        "Remarks": "C2B receipt verification",
        "Occasion": "C2B verification",
    }

    client = _daraja_client(config)
    try:
        return client.post("/mpesa/transactionstatus/v1/query", payload)
    except DarajaError as exc:
        logger.warning("Daraja Transaction Status query failed: %s", safe_repr(str(exc)))
        raise


def _status_confirms_receipt(data: dict, *, expected_amount: Decimal) -> bool:
    """True only when Safaricom's response BOTH reports success AND states an
    amount equal to what the confirmation claimed. Either half missing or
    wrong is not verified: a found-but-wrong-amount receipt is exactly the
    forged-callback shape this whole module exists to catch, and a
    ResultCode that is not success means Safaricom does not recognise the
    receipt at all."""
    if str(data.get("ResultCode")) != "0":
        return False
    raw_amount = data.get("Amount", data.get("TransactionAmount"))
    if raw_amount is None:
        return False
    try:
        reported = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError, TypeError):
        return False
    return reported == expected_amount


def verify_receipt(
    db: Session, *, txn: MpesaTransaction, callback_tenant: Optional[str] = None
) -> bool:
    """Verify `txn.receipt_number` with Safaricom before any settlement
    against it. Never raises: a Daraja failure or a missing/unparseable
    response is "not verified", the same outcome as an explicit rejection,
    because the caller (handle_confirmation) must never treat "we could not
    check" as "it is probably fine"."""
    if not txn.receipt_number:
        return False
    try:
        data = query_transaction_status(db, receipt=txn.receipt_number, callback_tenant=callback_tenant)
    except (DarajaError, HTTPException) as exc:
        logger.warning("C2B receipt verification could not reach Daraja: %s", safe_repr(str(exc)))
        return False
    return _status_confirms_receipt(data, expected_amount=Decimal(str(txn.amount or 0)))


def account_balance(
    db: Session, *, department_id: Optional[int] = None, callback_tenant: Optional[str] = None
) -> dict:
    """Request the shortcode's utility and working balances, for the admin UI
    to show an operator before they promise a refund. Never called on the
    refund hot path: see the module docstring for why the balances in the
    return value are always None here, not a stale or zero figure."""
    config = config_for(db, department_id=department_id)
    initiator, credential = _initiator_credentials(config)
    result_url, timeout_url = _flow_urls(config, callback_tenant, flow="balance")

    payload = {
        "Initiator": initiator,
        "SecurityCredential": credential,
        "CommandID": "AccountBalance",
        "PartyA": config.shortcode,
        "IdentifierType": _IDENTIFIER_TYPE_SHORTCODE,
        "Remarks": "Balance check",
        "QueueTimeOutURL": timeout_url,
        "ResultURL": result_url,
    }

    client = _daraja_client(config)
    try:
        data = client.post("/mpesa/accountbalance/v1/query", payload)
    except DarajaError as exc:
        logger.warning("Daraja Account Balance query failed: %s", safe_repr(str(exc)))
        raise

    return {
        "shortcode": config.shortcode,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "conversation_id": data.get("ConversationID"),
        "response_description": data.get("ResponseDescription"),
        # None, not 0: the figure has not arrived yet (see module docstring).
        "utility_balance": None,
        "working_balance": None,
    }

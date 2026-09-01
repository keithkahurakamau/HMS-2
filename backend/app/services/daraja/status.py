"""Transaction Status and Account Balance, the two Daraja queries that answer
"what actually happened" rather than initiate something new.

**Both are genuinely asynchronous.** This was gotten wrong in an earlier
version of this module: it treated the synchronous response to
POST /mpesa/transactionstatus/v1/query as the verdict on whether a receipt
was real. It is not. That response only acknowledges the query was queued
and hands back a ConversationID; the actual answer, whether Safaricom knows
the receipt and what amount it reports, arrives later, at a separate
ResultURL callback. Treating the acknowledgment as the verdict verifies
nothing at all: a forged confirmation would sail through it every time,
since nothing in the acknowledgment even mentions the receipt's outcome.

So this module's job is split in two, matching Safaricom's own split:

  - query_transaction_status fires the query and returns the acknowledgment
    (ConversationID, OriginatorConversationID). It decides nothing.
  - The actual verdict is handled where it is used: see
    app/services/daraja/c2b.py's handle_transaction_status_result, which
    receives Safaricom's later callback, correlates it back to the row that
    asked (by ConversationID), and is the ONLY place that decides settle,
    quarantine, or leave unverified. If no result ever arrives, the row
    stays Unverified forever rather than being resolved by a local guess:
    the exact same lesson that removed a local expiry timer from the STK
    reservation path (see reservation.py) for the same reason, silent money
    loss from a guessed outcome.

Account Balance is asynchronous the same way, and this module does not even
attempt the two-step split for it: no result-callback handler exists for
Account Balance in this codebase yet, on either endpoint family. See
account_balance's own docstring for what that means for its return value.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from types import SimpleNamespace
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
    to ask (handle_confirmation sets mpesa_config_id and flushes the row
    before firing this query) or it predates mpesa_config_id."""
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
    """Fire a Transaction Status query for `receipt` and return Safaricom's
    acknowledgment (OriginatorConversationID, ConversationID,
    ResponseDescription). This is NOT the verdict: see the module docstring.
    The caller (c2b.handle_confirmation) stores the two ids on its
    MpesaTransaction row so the later result callback can be correlated back
    to it; nothing here decides verified, matched, or settled."""
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


def _result_parameters(result: dict) -> dict:
    """Flatten Safaricom's Result.ResultParameters.ResultParameter list (the
    same shape B2C and Transaction Status results both use) into a plain
    {Key: Value} dict. Shared here rather than duplicated in c2b.py because
    a future B2C result handler (Task 7) will need the identical shape."""
    items = ((result.get("ResultParameters") or {}).get("ResultParameter")) or []
    return {
        item.get("Key"): item.get("Value")
        for item in items
        if isinstance(item, dict) and item.get("Key")
    }


def account_balance(
    db: Session, *, department_id: Optional[int] = None, callback_tenant: Optional[str] = None
) -> dict:
    """Request the shortcode's utility and working balances, for the admin UI
    to show an operator before they promise a refund. Never called on the
    refund hot path.

    NOT USABLE for its stated purpose yet. This submits the request and
    returns Safaricom's acknowledgment, but the actual balances arrive
    later on an Account Balance result callback, and no handler for that
    callback exists in this codebase (unlike Transaction Status, which
    c2b.handle_transaction_status_result now handles). Until that handler
    is built, utility_balance and working_balance are always None here,
    deliberately never a stale or zero figure standing in for an answer
    that has not arrived: showing an operator "no float" when the truth is
    "Safaricom has not replied" would be the exact wrong-fact failure this
    guards against. Treat this function today as "ask Safaricom to answer",
    not "get the answer"."""
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

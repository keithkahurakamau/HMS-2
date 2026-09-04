"""The M-Pesa event log: one emit helper, and the redaction every payload
passes through before it is ever written.

**Rule 1: redaction is an ALLOWLIST of safe fields, not a denylist of secret
ones.** This table is read by hospital staff and rendered in a browser, so a
secret stored in it is a secret disclosed. A forgotten denylist entry leaks a
credential; a forgotten allowlist entry merely omits a diagnostic field from
a page. Those failure modes are not comparable, so _SAFE_KEYS below is a
list of what is known to be harmless, never a list of what to strip. A
Daraja field renamed tomorrow, or one this module's author never thought of,
is dropped by default rather than trusted by default.

Never stored, in any form, anywhere in a payload: the STK `Password`, the
B2C `SecurityCredential`, `ConsumerKey`, `ConsumerSecret`, the passkey, and
the Daraja callback token. None of those names appear in _SAFE_KEYS. The
callback URLs (CallBackURL, ResultURL, QueueTimeOutURL, ConfirmationURL,
ValidationURL) are excluded for the same reason even though the URLs
themselves are not secrets: the token is a path segment inside them, and an
allowlist has no way to keep "the URL" while dropping "the one path segment
that matters", so the whole field is left out.

**Rule 2: emitting an event must never break a payment.** record_event
mirrors the pattern app/services/daraja/settlement.py's settle_invoice_match
already uses for its own notification: add and flush on the caller's own
session, inside a try/except that logs and swallows. A diagnostic table
that can abort a settlement or a refund is worse than no diagnostic table
at all.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.mpesa_events import MpesaEvent

logger = logging.getLogger(__name__)


# Every field name below is safe to show a hospital cashier verbatim: an
# amount, a status code, a receipt, an identifier Safaricom itself assigns.
# Matched case-insensitively, since this project's own request payloads use
# PascalCase but nothing structurally guarantees Safaricom always will.
_SAFE_KEYS = frozenset(k.lower() for k in [
    # Structural / envelope keys, not data on their own.
    "Body", "stkCallback", "Result", "ResultParameters", "ResultParameter",
    "CallbackMetadata", "Item", "Name", "Key", "Value",
    "ReferenceData", "ReferenceItem",

    # STK push / STK query.
    "BusinessShortCode", "ShortCode", "Timestamp", "TransactionType",
    "PartyA", "PartyB", "PhoneNumber", "AccountReference", "TransactionDesc",
    "MerchantRequestID", "CheckoutRequestID",
    "ResponseCode", "ResponseDescription", "CustomerMessage",

    # Common result envelope (STK callback, B2C result/timeout, Transaction
    # Status result, C2B Transaction Status ack).
    "ResultType", "ResultCode", "ResultDesc",
    "OriginatorConversationID", "ConversationID", "TransactionID",

    # STK callback metadata values.
    "Amount", "MpesaReceiptNumber", "TransactionDate", "Balance",

    # C2B validation / confirmation.
    "TransID", "TransTime", "TransAmount", "BillRefNumber", "InvoiceNumber",
    "OrgAccountBalance", "ThirdPartyTransID", "MSISDN",
    "FirstName", "MiddleName", "LastName",

    # C2B URL registration.
    "ResponseType",

    # B2C request / result. SecurityCredential and the two *URL fields are
    # deliberately absent (see the module docstring).
    "InitiatorName", "CommandID", "Remarks", "Occasion",
    "TransactionReceipt", "TransactionAmount", "ReceiptNo",
    "TransactionCompletedDateTime", "ReceiverPartyPublicName",
    "B2CWorkingAccountAvailableFunds", "B2CUtilityAccountAvailableFunds",
    "B2CChargesPaidAccountAvailableFunds", "B2CRecipientIsRegisteredCustomer",

    # Transaction Status / Account Balance. Initiator and IdentifierType
    # name WHO is asking, never a secret; SecurityCredential is absent.
    "Initiator", "IdentifierType", "DebitPartyName", "CreditPartyName",
    "DebitAccountType", "AccountBalance", "BOCompletedTime",

    # Daraja's own error envelope on a rejected/failed call.
    "errorCode", "errorMessage", "requestId",
])


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _redact_value(v)
            for k, v in value.items()
            if isinstance(k, str) and k.lower() in _SAFE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


def redact_payload(payload: Optional[dict]) -> Optional[dict]:
    """Keep only fields known to be safe, drop everything else.

    An allowlist, not a denylist: see the module docstring. `payload` is
    normally a Daraja request or response body; `None` (no payload to
    record) passes through unchanged.
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        # Defensive: every real caller passes a dict. Something else
        # arriving here is not a shape this function was written for, and
        # returning None is safer than guessing at how to filter it.
        return None
    return _redact_value(payload)


def record_event(
    db: Session,
    *,
    flow: str,
    direction: str,
    outcome: str,
    http_status: Optional[int] = None,
    daraja_result_code: Optional[str] = None,
    daraja_result_desc: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error_detail: Optional[str] = None,
    mpesa_transaction_id: Optional[int] = None,
    mpesa_refund_id: Optional[int] = None,
    mpesa_config_id: Optional[int] = None,
    checkout_request_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    receipt_number: Optional[str] = None,
    request_payload: Optional[dict] = None,
    response_payload: Optional[dict] = None,
) -> Optional[MpesaEvent]:
    """Write one mpesa_events row. Never raises.

    Adds and flushes on `db`, the caller's own session, exactly as
    settle_invoice_match's notify_permission call does for its
    notification: the row rides along with whatever commit the caller
    was already about to make, rather than this function owning a commit
    of its own (which would be wrong here regardless of the try/except:
    several call sites hold a Postgres advisory transaction lock that only
    their own commit or rollback may release).

    A failure here (a too-long field, a transient DB error, anything) is
    logged and swallowed. This function returns None in that case; no
    caller may treat that None as a reason to fail the surrounding
    payment, refund, or reconciliation step, and none do.
    """
    try:
        event = MpesaEvent(
            flow=flow,
            direction=direction,
            outcome=outcome,
            http_status=http_status,
            daraja_result_code=(
                str(daraja_result_code) if daraja_result_code is not None else None
            ),
            daraja_result_desc=(
                str(daraja_result_desc)[:255] if daraja_result_desc is not None else None
            ),
            duration_ms=duration_ms,
            error_detail=str(error_detail)[:2000] if error_detail is not None else None,
            mpesa_transaction_id=mpesa_transaction_id,
            mpesa_refund_id=mpesa_refund_id,
            mpesa_config_id=mpesa_config_id,
            checkout_request_id=checkout_request_id,
            conversation_id=conversation_id,
            receipt_number=receipt_number,
            request_payload=_dump(redact_payload(request_payload)),
            response_payload=_dump(redact_payload(response_payload)),
        )
        db.add(event)
        db.flush()
        return event
    except Exception:  # noqa: BLE001, an event write must never break a payment
        logger.warning(
            "record_event: failed to write mpesa_events row (flow=%s, "
            "direction=%s, outcome=%s)", flow, direction, outcome, exc_info=True,
        )
        return None


def _dump(payload: Optional[dict]) -> Optional[str]:
    if payload is None:
        return None
    import json
    try:
        return json.dumps(payload, default=str)[:8000]
    except Exception:  # noqa: BLE001, see record_event's own docstring
        return None


# ─── Durable inbound-callback journal ───────────────────────────────────────
#
# record_event above rides the caller's transaction by design, which is right
# for a diagnostic row: it must never own a commit that a caller's advisory
# lock depends on. But it means an inbound callback recorded that way dies
# with a rollback, and that is exactly what happened in live testing: a
# settlement raised, the session rolled back, and the only evidence Safaricom
# had ever called us went with it. Safaricom does not retry an STK callback,
# so the payment was stranded with nothing left to replay.
#
# These two functions exist for that one job. They use their OWN session and
# their OWN commit, so the record survives whatever the handler does next.
# The payload is stored through the same allowlist redaction as everything
# else (which keeps every field apply_stk_callback reads: CallbackMetadata,
# Amount, MpesaReceiptNumber, CheckoutRequestID, ResultCode), so a journalled
# callback is replayable without ever storing a field the allowlist rejects.

INBOUND_RECEIVED = "received"
INBOUND_APPLIED = "applied"


def _own_session(db_name: str) -> Session:
    from sqlalchemy.orm import sessionmaker
    from app.config.database import get_tenant_engine

    return sessionmaker(autocommit=False, autoflush=False, bind=get_tenant_engine(db_name))()


def journal_inbound(
    db_name: str,
    *,
    flow: str,
    payload: Optional[dict],
    checkout_request_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Optional[int]:
    """Commit an inbound callback to the event log before it is handled.

    Returns the event id, or None if journalling failed. Never raises: a
    journal failure must not cost us the acknowledgement to Safaricom, which
    is the one thing that stops them retrying into a duplicate.
    """
    session = None
    try:
        session = _own_session(db_name)
        event = MpesaEvent(
            flow=flow,
            direction="inbound",
            outcome=INBOUND_RECEIVED,
            checkout_request_id=checkout_request_id,
            conversation_id=conversation_id,
            request_payload=_dump(redact_payload(payload)),
        )
        session.add(event)
        session.commit()
        return event.id
    except Exception:  # noqa: BLE001, journalling must never break the ack
        logger.warning("journal_inbound: could not journal %s callback", flow, exc_info=True)
        if session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def mark_inbound_applied(db_name: str, event_id: Optional[int]) -> None:
    """Flip a journalled callback to `applied` once its handler has committed.

    Anything left at `received` past its grace period is, by definition, a
    callback we accepted and never acted on, which is what the replay pass in
    reconcile_queries.py looks for.
    """
    if event_id is None:
        return
    session = None
    try:
        session = _own_session(db_name)
        event = session.query(MpesaEvent).filter(MpesaEvent.id == event_id).first()
        if event is not None and event.outcome == INBOUND_RECEIVED:
            event.outcome = INBOUND_APPLIED
            session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("mark_inbound_applied: could not mark event %s", event_id, exc_info=True)
        if session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

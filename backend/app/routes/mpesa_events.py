"""The M-Pesa event log's read API: what happened to a payment, for a
cashier standing at a counter.

Behind the same billing permission mpesa_payment.py's own read endpoints
use (billing:read or billing:manage), not a new codename: this is a view
onto money that already moved, the same audience as an invoice's payment
history.

**Phone numbers are patient personal data.** The list view returns a
masked phone (looked up via the event's correlated MpesaTransaction or
MpesaRefund, not stored on the event itself); the detail view returns it
in full. See app/services/daraja/events.py for why the stored payloads
themselves are already safe to show in full at BOTH levels: the secrets
that would matter were never written to begin with.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.models.mpesa_events import MpesaEvent

router = APIRouter(prefix="/api/mpesa/events", tags=["Payments, M-Pesa Event Log"])

_READ = ("billing:read", "billing:manage")


def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """Same shape as app/utils/log_redact.py's own MSISDN mask: first 3,
    last 2, everything between replaced. Kept as a small local copy rather
    than importing that module's private helper, since this one only ever
    receives an already-known-to-be-a-phone-number string, not free text
    to scan for one."""
    if not phone:
        return phone
    if len(phone) < 6:
        return "***"
    return phone[:3] + "***" + phone[-2:]


def _phone_for_event(db: Session, event: MpesaEvent) -> Optional[str]:
    if event.mpesa_transaction_id:
        txn = (
            db.query(MpesaTransaction)
            .filter(MpesaTransaction.id == event.mpesa_transaction_id)
            .first()
        )
        if txn is not None:
            return txn.phone_number
    if event.mpesa_refund_id:
        refund = db.query(MpesaRefund).filter(MpesaRefund.id == event.mpesa_refund_id).first()
        if refund is not None:
            return refund.phone_number
    return None


def _amount_for_transaction(db: Session, transaction_id: Optional[int]) -> Optional[Decimal]:
    if not transaction_id:
        return None
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == transaction_id).first()
    return txn.amount if txn is not None else None


def _amount_for_refund(db: Session, refund_id: Optional[int]) -> Optional[Decimal]:
    if not refund_id:
        return None
    refund = db.query(MpesaRefund).filter(MpesaRefund.id == refund_id).first()
    return refund.amount if refund is not None else None


def _claimed_amount(response_payload: Optional[dict]) -> Optional[str]:
    """Best-effort extraction of "the amount Safaricom claimed" out of a
    redacted response/request payload, for the quarantine side-by-side
    comparison. Every shape this checks (STK CallbackMetadata.Item,
    a bare TransactionAmount/Amount) is a field this module's own
    redact_payload allowlist already keeps, so nothing extra needs
    decoding here.
    """
    if not response_payload:
        return None
    items = (
        ((response_payload.get("Body") or {}).get("stkCallback") or {})
        .get("CallbackMetadata", {})
        .get("Item", [])
    )
    for item in items or []:
        if isinstance(item, dict) and item.get("Name") == "Amount":
            return str(item.get("Value"))
    for key in ("TransactionAmount", "Amount", "TransAmount"):
        if key in response_payload:
            return str(response_payload[key])
    return None


def _parse_payload(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _list_row(db: Session, event: MpesaEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "flow": event.flow,
        "direction": event.direction,
        "outcome": event.outcome,
        "http_status": event.http_status,
        "daraja_result_code": event.daraja_result_code,
        "daraja_result_desc": event.daraja_result_desc,
        "duration_ms": event.duration_ms,
        "checkout_request_id": event.checkout_request_id,
        "conversation_id": event.conversation_id,
        "receipt_number": event.receipt_number,
        "phone_masked": _mask_phone(_phone_for_event(db, event)),
        "mpesa_transaction_id": event.mpesa_transaction_id,
        "mpesa_refund_id": event.mpesa_refund_id,
    }


@router.get("")
def list_events(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ)),
    outcome: Optional[str] = None,
    flow: Optional[str] = None,
    till: Optional[int] = Query(default=None, description="mpesa_config_id"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = Query(default=None, description="Receipt number or phone number"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
):
    q = db.query(MpesaEvent)
    if outcome:
        q = q.filter(MpesaEvent.outcome == outcome)
    if flow:
        q = q.filter(MpesaEvent.flow == flow)
    if till:
        q = q.filter(MpesaEvent.mpesa_config_id == till)
    if date_from:
        q = q.filter(MpesaEvent.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        q = q.filter(MpesaEvent.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if search:
        term = search.strip()
        txn_ids = [
            row[0] for row in
            db.query(MpesaTransaction.id).filter(MpesaTransaction.phone_number.ilike(f"%{term}%")).all()
        ]
        refund_ids = [
            row[0] for row in
            db.query(MpesaRefund.id).filter(MpesaRefund.phone_number.ilike(f"%{term}%")).all()
        ]
        clauses = [MpesaEvent.receipt_number.ilike(f"%{term}%")]
        if txn_ids:
            clauses.append(MpesaEvent.mpesa_transaction_id.in_(txn_ids))
        if refund_ids:
            clauses.append(MpesaEvent.mpesa_refund_id.in_(refund_ids))
        q = q.filter(or_(*clauses))

    total = q.count()
    rows = (
        q.order_by(MpesaEvent.created_at.desc(), MpesaEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_list_row(db, event) for event in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{event_id}")
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ)),
):
    event = db.query(MpesaEvent).filter(MpesaEvent.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")

    request_payload = _parse_payload(event.request_payload)
    response_payload = _parse_payload(event.response_payload)

    detail = {
        "id": event.id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "flow": event.flow,
        "direction": event.direction,
        "outcome": event.outcome,
        "http_status": event.http_status,
        "daraja_result_code": event.daraja_result_code,
        "daraja_result_desc": event.daraja_result_desc,
        "duration_ms": event.duration_ms,
        "error_detail": event.error_detail,
        "mpesa_transaction_id": event.mpesa_transaction_id,
        "mpesa_refund_id": event.mpesa_refund_id,
        "mpesa_config_id": event.mpesa_config_id,
        "checkout_request_id": event.checkout_request_id,
        "conversation_id": event.conversation_id,
        "receipt_number": event.receipt_number,
        # Full phone number here, unlike the list view: this is the one
        # place a cashier is allowed to see it, gated by the same
        # permission that already governs billing.
        "phone_number": _phone_for_event(db, event),
        "request_payload": request_payload,
        "response_payload": response_payload,
    }

    if event.outcome == "quarantined":
        requested = (
            _amount_for_transaction(db, event.mpesa_transaction_id)
            if event.mpesa_transaction_id
            else _amount_for_refund(db, event.mpesa_refund_id)
        )
        detail["requested_amount"] = str(requested) if requested is not None else None
        detail["claimed_amount"] = (
            _claimed_amount(response_payload) or _claimed_amount(request_payload)
        )

    return detail

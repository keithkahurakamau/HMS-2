"""Daraja (M-Pesa) payment routes: the tenant-facing STK push surface, and
every inbound Safaricom callback except B2C (see mpesa_refunds.py) and the
two already-wired B2C paths there.

Two shapes of endpoint, deliberately kept apart, the same split
mpesa_refunds.py documents:

  * Permission-gated, session-authenticated endpoints (push, status) under
    /api/payments/mpesa. CSRF applies here like any other state-changing,
    session-authenticated route.

  * Public, unauthenticated Safaricom callbacks, token-addressed with a
    tenant routing hint, CSRF-exempt (see app/main.py's _CSRF_EXEMPT_PATHS).
    Authenticated instead by the source IP allow-list plus the unguessable
    callback token, per app/core/daraja_callback.py's ordering invariant:
    verify_daraja_source MUST run before resolve_tenant_by_hint.

Every callback follows the same acknowledgement contract
(app/core/daraja_callback.py's ACK_OK / ACK_REJECT / TenantLookupUnavailable
docstrings): a payload we could not evaluate at all (a master- or tenant-DB
failure) is answered with a non-200 so Safaricom retries; a payload we
evaluated and rejected (an unknown or spoofed tenant hint/token pair) is
answered 200, Safaricom does not retry a decision we already made; a
handler exception is logged and still acknowledged, never surfaced as a
non-200. C2B validation is the one exception to "reject means ACK_REJECT
or a decline": see c2b_validation's own docstring below.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, condecimal
from sqlalchemy.orm import Session, sessionmaker

from app.config.database import MasterSessionLocal, get_db, get_tenant_engine
from app.core import daraja_callback as dc
from app.core.daraja_callback import (
    ACK_C2B_DECLINE,
    ACK_OK,
    ACK_REJECT,
    TenantLookupUnavailable,
    resolve_tenant_by_hint,
    verify_daraja_source,
)
from app.core.dependencies import RequirePermission
from app.core.limiter import limiter
from app.models.billing import Invoice
from app.models.mpesa import MpesaTransaction
from app.services.daraja.c2b import handle_confirmation, handle_validation
from app.services.daraja.platform import apply_platform_stk_callback
from app.services.daraja.settlement import apply_stk_callback
from app.services.daraja.status import (
    handle_transaction_status_result,
    handle_transaction_status_timeout,
)
from app.services.daraja.stk import initiate_stk_push, query_stk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments/mpesa", tags=["Payments, M-Pesa"])


# ─── Schemas ────────────────────────────────────────────────────────────────


class STKPushRequest(BaseModel):
    phone_number: str
    invoice_id: int
    # Money is Decimal, never float: a float amount at this boundary is
    # exactly the anti-pattern flagged elsewhere in this migration (a float
    # that cannot round-trip exactly through a KES 12,2 column).
    amount: condecimal(gt=0, max_digits=12, decimal_places=2)
    # Real idempotency: forwarded to initiate_stk_push, which scopes the
    # (user_id, endpoint, key) cache via app/core/idempotency.py. A repeated
    # key with the same body replays the first response instead of pushing a
    # second prompt; the same key with a different body is a 409.
    idempotency_key: str


# ─── Authenticated: STK push + status ───────────────────────────────────────


@router.post("/stk-push")
@limiter.limit("5/minute")
def trigger_stk_push(
    request: Request,
    payload: STKPushRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("billing:manage")),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")

    # Never push an amount the invoice can't justify: the callback trusts the
    # initiated figure, so this is the one place that validates against the
    # invoice. Mirrors the Pay Hero route's M-2 guard.
    outstanding = Decimal(str(invoice.total_amount or 0)) - Decimal(str(invoice.amount_paid or 0))
    if outstanding <= 0:
        raise HTTPException(status_code=400, detail="Invoice has no outstanding balance.")
    if payload.amount > outstanding:
        raise HTTPException(
            status_code=400,
            detail=f"Amount {payload.amount} exceeds the invoice outstanding balance {outstanding}.",
        )

    return initiate_stk_push(
        db,
        phone_number=payload.phone_number,
        amount=payload.amount,
        invoice_id=payload.invoice_id,
        callback_tenant=request.headers.get("X-Tenant-ID"),
        user_id=current_user["user_id"],
        idempotency_key=payload.idempotency_key,
    )


@router.get("/status/{checkout_request_id}")
def get_payment_status(
    checkout_request_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("billing:manage")),
):
    """Live poll against Daraja itself (STK Query). Never settles anything:
    only apply_stk_callback's cross-checked path does that."""
    return query_stk(db, checkout_request_id=checkout_request_id)


@router.get("/invoice-status/{invoice_id}")
def invoice_payment_status(
    invoice_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("billing:read", "billing:manage")),
):
    """DB-backed status the cashier screen polls while an STK push is
    pending. Reads our own transaction row (updated by the verified
    callback) rather than Daraja's live API, mirroring the Pay Hero route
    of the same name and purpose."""
    invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    latest = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.invoice_id == invoice_id)
        .order_by(MpesaTransaction.id.desc())
        .first()
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.status,
        "amount_paid": str(invoice.amount_paid or 0),
        "total_amount": str(invoice.total_amount or 0),
        "mpesa_status": latest.status if latest else None,
        "mpesa_receipt_number": latest.receipt_number if latest else None,
        "mpesa_result_desc": latest.result_desc if latest else None,
    }


# ─── Safaricom callbacks (public, token-authenticated) ──────────────────────


def _tenant_session(db_name: str) -> Session:
    engine = get_tenant_engine(db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _resolve_or_none(tenant_hint: str, token: str, *, label: str) -> Optional[str]:
    """Shared resolution step for every tenant-scoped callback below.
    Raises HTTPException(503) on TenantLookupUnavailable (never
    acknowledged: Safaricom must retry a payload we could not evaluate at
    all); returns None for an evaluated non-match (the caller acknowledges
    with ACK_REJECT, HTTP 200 — the same JSON body as ACK_OK, so Safaricom
    never treats this as a decline, only as "do not retry")."""
    try:
        return resolve_tenant_by_hint(tenant_hint, token)
    except TenantLookupUnavailable:
        logger.error("%s: tenant lookup unavailable, cannot evaluate callback", label)
        raise HTTPException(status_code=503, detail="Temporarily unable to process callback.")


@router.post("/stk/callback/{tenant_hint}/{token}")
async def stk_callback(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = _resolve_or_none(tenant_hint, token, label="STK callback")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("STK callback: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        apply_stk_callback(db, payload)
    except Exception:  # noqa: BLE001 — always acknowledge; the failure is ours to chase.
        logger.exception("STK callback: handler raised")
    finally:
        db.close()
    return ACK_OK


@router.post("/c2b/validation/{tenant_hint}/{token}")
async def c2b_validation(tenant_hint: str, token: str, request: Request):
    """The one Daraja path where a rejection reaches a real patient standing
    at a counter. handle_validation already fails toward accept on anything
    it cannot be certain is wrong (see its own docstring); this route
    preserves that on the one failure mode the service layer cannot see:
    an exception evaluating the payload here must default to accept, never
    ACK_C2B_DECLINE. ACK_C2B_DECLINE is reserved for a genuinely evaluated,
    deliberate rejection (handle_validation returning False)."""
    body = await verify_daraja_source(request)
    db_name = _resolve_or_none(tenant_hint, token, label="C2B validation")
    if db_name is None:
        # An unrecognised hint/token pair, not a payment decision: ACK_REJECT
        # carries the identical accepting body Safaricom sees for ACK_OK.
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("C2B validation: unparseable JSON body; accepted, not evaluated")
        return ACK_OK

    db = _tenant_session(db_name)
    accepted = True
    try:
        accepted = handle_validation(db, payload)
    except Exception:  # noqa: BLE001 — never let an internal error decline a real payment.
        logger.exception("C2B validation: handler raised; accepting by default")
        accepted = True
    finally:
        db.close()
    return ACK_OK if accepted else ACK_C2B_DECLINE


@router.post("/c2b/confirmation/{tenant_hint}/{token}")
async def c2b_confirmation(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = _resolve_or_none(tenant_hint, token, label="C2B confirmation")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("C2B confirmation: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        handle_confirmation(db, payload, callback_tenant=tenant_hint)
    except Exception:  # noqa: BLE001 — confirmation is real money already at
        # the till; a malformed payload or handler bug is ours to chase from
        # the logs, never Safaricom's to retry into a duplicate delivery.
        logger.exception("C2B confirmation: handler raised")
    finally:
        db.close()
    return ACK_OK


@router.post("/status/result/{tenant_hint}/{token}")
async def status_result(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = _resolve_or_none(tenant_hint, token, label="Transaction Status result")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Transaction Status result: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        handle_transaction_status_result(db, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Transaction Status result: handler raised")
    finally:
        db.close()
    return ACK_OK


@router.post("/status/timeout/{tenant_hint}/{token}")
async def status_timeout(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = _resolve_or_none(tenant_hint, token, label="Transaction Status timeout")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Transaction Status timeout: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        handle_transaction_status_timeout(db, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Transaction Status timeout: handler raised")
    finally:
        db.close()
    return ACK_OK


@router.post("/platform/stk/callback/{tenant_hint}/{token}")
async def platform_stk_callback(tenant_hint: str, token: str, request: Request):
    """The operator's own subscription-billing STK callback. Settles against
    the MASTER database (platform_mpesa_transactions), never a tenant DB.

    tenant_hint must resolve to exactly the reserved platform hint
    (app/core/daraja_callback.py's _PLATFORM_HINT): resolve_tenant_by_hint
    checks that reserved value against PlatformMpesaConfig BEFORE it ever
    tries a tenant lookup, so a real tenant's own STK callback token can
    never be replayed here and mistaken for a platform settlement — this
    route double-checks that identity explicitly rather than trusting
    "resolved is not None" alone.
    """
    body = await verify_daraja_source(request)
    resolved = _resolve_or_none(tenant_hint, token, label="Platform STK callback")
    if resolved != dc._PLATFORM_HINT:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Platform STK callback: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = MasterSessionLocal()
    try:
        apply_platform_stk_callback(db, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Platform STK callback: handler raised")
    finally:
        db.close()
    return ACK_OK

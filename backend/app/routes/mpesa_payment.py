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
from fastapi.concurrency import run_in_threadpool
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
    # I4: forwarded to config_for (via initiate_stk_push), which resolves
    # the department's own active till when one exists, otherwise the
    # hospital default. Without this, config_for always falls through to
    # the default and per-department tills (Task 14) can never be reached
    # from this route. None (the default) is the hospital-wide till.
    department_id: Optional[int] = None
    # Real idempotency: forwarded to initiate_stk_push, which scopes the
    # (user_id, endpoint, key) cache via app/core/idempotency.py. A repeated
    # key with the same body replays the first response instead of pushing a
    # second prompt; the same key with a different body is a 409.
    # department_id is already part of that fingerprint (initiate_stk_push
    # includes it in idempotency_body), so no other change is needed here.
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
        department_id=payload.department_id,
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


async def _resolve_or_none(tenant_hint: str, token: str, *, label: str) -> Optional[str]:
    """Shared resolution step for every tenant-scoped callback below.

    Every one of these handlers is `async def` because verify_daraja_source
    awaits the request body; resolve_tenant_by_hint itself is synchronous,
    blocking DB work (it opens a tenant engine and queries, or queries
    master for the platform hint). Run it in the threadpool rather than
    inline: an unguarded synchronous call here blocks the whole event loop
    for the duration of that query, on every single callback, which is
    exactly the query-cost denial of service the IP allow-list exists to
    keep affordable. See run_in_threadpool's use throughout this module.

    Raises HTTPException(503) on TenantLookupUnavailable (never
    acknowledged: Safaricom must retry a payload we could not evaluate at
    all); returns None for an evaluated non-match (the caller acknowledges
    with ACK_REJECT, HTTP 200, the same JSON body as ACK_OK, so Safaricom
    never treats this as a decline, only as "do not retry")."""
    try:
        return await run_in_threadpool(resolve_tenant_by_hint, tenant_hint, token)
    except TenantLookupUnavailable:
        logger.error("%s: tenant lookup unavailable, cannot evaluate callback", label)
        raise HTTPException(status_code=503, detail="Temporarily unable to process callback.")


async def _run_handler_and_ack(db: Session, func, *args, label: str, **kwargs) -> None:
    """Shared tail for every callback below except C2B validation (which
    needs the handler's return value to decide ACK_OK vs ACK_C2B_DECLINE,
    and its own accept-on-error rule; see c2b_validation).

    Runs `func` off the event loop (it does blocking DB work, and for
    handle_confirmation a live outbound HTTPS call to Safaricom with its
    own timeouts), logs and swallows any exception per the acknowledgement
    contract (a handler exception is ours to chase, never surfaced as a
    non-200), and closes the session in the threadpool too: a session with
    an open transaction can issue a real network round trip (an implicit
    rollback) on close, the same blocking shape as everything else here.
    """
    try:
        await run_in_threadpool(func, db, *args, **kwargs)
    except Exception:  # noqa: BLE001, always acknowledge; the failure is ours to chase.
        logger.exception("%s: handler raised", label)
    finally:
        await run_in_threadpool(db.close)


@router.post("/stk/callback/{tenant_hint}/{token}")
async def stk_callback(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = await _resolve_or_none(tenant_hint, token, label="STK callback")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("STK callback: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = await run_in_threadpool(_tenant_session, db_name)
    await _run_handler_and_ack(db, apply_stk_callback, payload, label="STK callback")
    return ACK_OK


@router.post("/c2b/validation/{tenant_hint}/{token}")
async def c2b_validation(tenant_hint: str, token: str, request: Request):
    """The one Daraja path where a rejection reaches a real patient standing
    at a counter, and the one route where the ordering invariant's usual
    503-on-TenantLookupUnavailable rule and the never-decline rule
    conflict. Never-decline wins here, deliberately diverging from every
    other callback in this module:

      * TenantLookupUnavailable (a master- or tenant-DB failure) accepts,
        it does not 503. A 503 buys nothing on this route: validation is
        synchronous and one-shot, so there is no retry to gain, and the
        customer's transaction is already decided by the time any retry
        could land. The confirmation that follows carries the same hint
        and token, hits the same lookup, and IS retried if it 503s, so the
        record is not lost, only the (already loose) validation check.
      * handle_validation already fails toward accept on anything it
        cannot be certain is wrong (see its own docstring); an exception
        evaluating the payload here must default to accept the same way,
        never ACK_C2B_DECLINE.

    ACK_C2B_DECLINE is reserved for a genuinely evaluated, deliberate
    rejection: handle_validation returning False.
    """
    body = await verify_daraja_source(request)
    try:
        db_name = await run_in_threadpool(resolve_tenant_by_hint, tenant_hint, token)
    except TenantLookupUnavailable:
        logger.error(
            "C2B validation: tenant lookup unavailable; accepting by default "
            "(see this route's own docstring for why 503 is wrong here)"
        )
        return ACK_OK
    if db_name is None:
        # An unrecognised hint/token pair, not a payment decision: ACK_REJECT
        # carries the identical accepting body Safaricom sees for ACK_OK.
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("C2B validation: unparseable JSON body; accepted, not evaluated")
        return ACK_OK

    db = await run_in_threadpool(_tenant_session, db_name)
    accepted = True
    try:
        accepted = await run_in_threadpool(handle_validation, db, payload)
    except Exception:  # noqa: BLE001, never let an internal error decline a real payment.
        logger.exception("C2B validation: handler raised; accepting by default")
        accepted = True
    finally:
        await run_in_threadpool(db.close)
    return ACK_OK if accepted else ACK_C2B_DECLINE


@router.post("/c2b/confirmation/{tenant_hint}/{token}")
async def c2b_confirmation(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = await _resolve_or_none(tenant_hint, token, label="C2B confirmation")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("C2B confirmation: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = await run_in_threadpool(_tenant_session, db_name)
    # confirmation is real money already at the till; a malformed payload
    # or handler bug is ours to chase from the logs, never Safaricom's to
    # retry into a duplicate delivery. handle_confirmation also makes a
    # live outbound HTTPS call to Safaricom (Transaction Status), which is
    # exactly why this runs off the event loop like every other handler
    # here.
    await _run_handler_and_ack(
        db, handle_confirmation, payload, label="C2B confirmation", callback_tenant=tenant_hint,
    )
    return ACK_OK


@router.post("/status/result/{tenant_hint}/{token}")
async def status_result(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = await _resolve_or_none(tenant_hint, token, label="Transaction Status result")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Transaction Status result: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = await run_in_threadpool(_tenant_session, db_name)
    await _run_handler_and_ack(db, handle_transaction_status_result, payload, label="Transaction Status result")
    return ACK_OK


@router.post("/status/timeout/{tenant_hint}/{token}")
async def status_timeout(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    db_name = await _resolve_or_none(tenant_hint, token, label="Transaction Status timeout")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Transaction Status timeout: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = await run_in_threadpool(_tenant_session, db_name)
    await _run_handler_and_ack(db, handle_transaction_status_timeout, payload, label="Transaction Status timeout")
    return ACK_OK


@router.post("/platform/stk/callback/{tenant_hint}/{token}")
async def platform_stk_callback(tenant_hint: str, token: str, request: Request):
    """The operator's own subscription-billing STK callback. Settles against
    the MASTER database (platform_mpesa_transactions), never a tenant DB.

    tenant_hint must resolve to exactly the reserved platform hint
    (app/core/daraja_callback.py's PLATFORM_HINT): resolve_tenant_by_hint
    checks that reserved value against PlatformMpesaConfig BEFORE it ever
    tries a tenant lookup, so a real tenant's own STK callback token can
    never be replayed here and mistaken for a platform settlement. This
    route double-checks that identity explicitly rather than trusting
    "resolved is not None" alone.
    """
    body = await verify_daraja_source(request)
    resolved = await _resolve_or_none(tenant_hint, token, label="Platform STK callback")
    if resolved != dc.PLATFORM_HINT:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("Platform STK callback: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = await run_in_threadpool(MasterSessionLocal)
    await _run_handler_and_ack(db, apply_platform_stk_callback, payload, label="Platform STK callback")
    return ACK_OK

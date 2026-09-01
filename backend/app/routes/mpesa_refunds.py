"""B2C refund routes.

Two shapes of endpoint here, deliberately kept apart:

  * Permission-gated, session-authenticated endpoints (request, approve,
    dispatch retry, read) under /api/payments/mpesa/refunds. These require
    the mpesa:refund permission specifically, never billing:manage: being
    able to take a payment must not imply being able to send one back
    (see app/services/daraja/b2c.py's module docstring). CSRF applies here
    the same as any other session-authenticated, state-changing route.

  * Public, unauthenticated Safaricom callbacks under /api/payments/mpesa/
    b2c/result and /b2c/timeout, token-addressed with a tenant routing hint,
    the same family as every other Daraja callback. CSRF-exempt (see
    app/main.py's _CSRF_EXEMPT_PATHS); authenticated instead by the source
    IP allow-list plus the unguessable callback token, per
    app/core/daraja_callback.py's ordering invariant: verify_daraja_source
    MUST run before resolve_tenant_by_hint.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.config.database import get_db, get_tenant_engine
from app.core.daraja_callback import (
    ACK_OK,
    ACK_REJECT,
    TenantLookupUnavailable,
    resolve_tenant_by_hint,
    verify_daraja_source,
)
from app.core.dependencies import RequirePermission
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import (
    approve_refund,
    dispatch_refund,
    handle_b2c_result,
    handle_b2c_timeout,
    refundable_amount,
    request_refund,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments/mpesa", tags=["Payments, M-Pesa Refunds"])


# ─── Schemas ────────────────────────────────────────────────────────────────


class RefundRequest(BaseModel):
    source_transaction_id: int
    amount: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=255)


def _refund_view(refund: MpesaRefund) -> dict:
    return {
        "id": refund.id,
        "source_transaction_id": refund.source_transaction_id,
        "invoice_id": refund.invoice_id,
        "phone_number": refund.phone_number,
        "amount": str(refund.amount),
        "reason": refund.reason,
        "status": refund.status,
        "originator_conversation_id": refund.originator_conversation_id,
        "conversation_id": refund.conversation_id,
        "transaction_receipt": refund.transaction_receipt,
        "result_desc": refund.result_desc,
        "requested_by": refund.requested_by,
        "approved_by": refund.approved_by,
        "requested_at": refund.requested_at.isoformat() if refund.requested_at else None,
        "approved_at": refund.approved_at.isoformat() if refund.approved_at else None,
        "completed_at": refund.completed_at.isoformat() if refund.completed_at else None,
    }


# ─── Permission-gated endpoints ─────────────────────────────────────────────


@router.post("/refunds")
def create_refund(
    body: RefundRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("mpesa:refund")),
):
    refund = request_refund(
        db,
        source_transaction_id=body.source_transaction_id,
        amount=body.amount,
        reason=body.reason,
        user_id=user["user_id"],
    )
    return _refund_view(refund)


@router.post("/refunds/{refund_id}/approve")
def approve_and_dispatch_refund(
    refund_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("mpesa:refund")),
):
    """Approve a Requested refund, then attempt to submit it to Safaricom.

    Approval and dispatch stay separate service calls (approve_refund,
    dispatch_refund) so a dispatch that never reached Safaricom, a network
    error rather than a rejection, can be retried via retry-dispatch below
    without re-running approval or its two-person check.
    """
    refund = approve_refund(db, refund_id=refund_id, user_id=user["user_id"])
    tenant_hint = request.headers.get("X-Tenant-ID")
    refund = dispatch_refund(db, refund=refund, callback_tenant=tenant_hint)
    return _refund_view(refund)


@router.post("/refunds/{refund_id}/retry-dispatch")
def retry_dispatch_refund(
    refund_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("mpesa:refund")),
):
    """Retry submitting an already-approved refund whose previous dispatch
    attempt could not reach Safaricom. Reuses the same
    OriginatorConversationID minted at request time, on every attempt."""
    refund = db.query(MpesaRefund).filter(MpesaRefund.id == refund_id).first()
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found.")
    tenant_hint = request.headers.get("X-Tenant-ID")
    refund = dispatch_refund(db, refund=refund, callback_tenant=tenant_hint)
    return _refund_view(refund)


@router.get("/refunds/{refund_id}")
def get_refund(
    refund_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("mpesa:refund", "billing:read")),
):
    refund = db.query(MpesaRefund).filter(MpesaRefund.id == refund_id).first()
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found.")
    return _refund_view(refund)


@router.get("/transactions/{transaction_id}/refundable")
def get_refundable_amount(
    transaction_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("mpesa:refund", "billing:read")),
):
    """The balance still refundable on a receipt, for a refund form to show
    before anything is submitted. Read-only: does not lock the row, since
    nothing here is acted on. request_refund performs the real, locked
    check at the moment it actually matters."""
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == transaction_id).first()
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"refundable_amount": str(refundable_amount(db, txn=txn))}


# ─── Safaricom callbacks (public, token-authenticated) ─────────────────────


def _tenant_session(db_name: str) -> Session:
    engine = get_tenant_engine(db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


@router.post("/b2c/result/{tenant_hint}/{token}")
async def b2c_result(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    try:
        db_name = resolve_tenant_by_hint(tenant_hint, token)
    except TenantLookupUnavailable:
        # We could not evaluate this callback at all (a master- or
        # tenant-DB failure), a different fact from "evaluated and did not
        # match". A non-200 here is deliberate: Safaricom retries a result
        # we never got to look at, rather than losing it to a transient
        # outage on our side.
        logger.error("B2C result: tenant lookup unavailable, cannot evaluate callback")
        raise HTTPException(status_code=503, detail="Temporarily unable to process callback.")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("B2C result: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        handle_b2c_result(db, payload)
    except Exception:  # noqa: BLE001, never let a handler bug surface as a
        # non-200 to Safaricom; the callback is always acknowledged, the
        # failure is ours to chase from the logs.
        logger.exception("B2C result: handler raised")
    finally:
        db.close()
    return ACK_OK


@router.post("/b2c/timeout/{tenant_hint}/{token}")
async def b2c_timeout(tenant_hint: str, token: str, request: Request):
    body = await verify_daraja_source(request)
    try:
        db_name = resolve_tenant_by_hint(tenant_hint, token)
    except TenantLookupUnavailable:
        logger.error("B2C timeout: tenant lookup unavailable, cannot evaluate callback")
        raise HTTPException(status_code=503, detail="Temporarily unable to process callback.")
    if db_name is None:
        return ACK_REJECT

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("B2C timeout: unparseable JSON body; acknowledged, not processed")
        return ACK_OK

    db = _tenant_session(db_name)
    try:
        handle_b2c_timeout(db, payload)
    except Exception:  # noqa: BLE001, same reasoning as b2c_result above.
        logger.exception("B2C timeout: handler raised")
    finally:
        db.close()
    return ACK_OK

"""Pay Hero payment routes — replaces the legacy Daraja-only endpoints.

Webhook flow (PAY-002, PAY-003):
  1. verify_payhero() validates HMAC signature + source IP, fail-closed.
  2. The route ACKs immediately (200) and queues the body for asynchronous
     processing via BackgroundTasks so Pay Hero never blocks on our DB.
  3. The worker function takes a Postgres advisory lock on the receipt
     reference before mutating state. UNIQUE(receipt_number) on
     payhero_transactions is the last line of defence (migration aa1f53d20611).
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db, get_tenant_engine
from app.core.dependencies import RequirePermission
from app.core.limiter import limiter
from app.core.payhero_webhook import verify_payhero
from app.models.billing import Invoice
from app.models.payhero import PayHeroTransaction
from app.services.payhero_service import (
    check_payment_status,
    initiate_stk_push as payhero_stk_push,
    settle_invoice_match,
)
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments/payhero", tags=["Payments — Pay Hero"])


class STKPushRequest(BaseModel):
    phone_number: str
    amount: float
    invoice_id: int


@router.post("/stk-push", dependencies=[Depends(RequirePermission("billing:manage"))])
@limiter.limit("5/minute")
def trigger_stk_push(
    request: Request,
    payload: STKPushRequest,
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invoice is already fully paid")
    return payhero_stk_push(
        db,
        phone_number=payload.phone_number,
        amount=payload.amount,
        invoice_id=payload.invoice_id,
    )


@router.get("/status/{reference}", dependencies=[Depends(RequirePermission("billing:manage"))])
def get_payment_status(reference: str, db: Session = Depends(get_db)):
    return check_payment_status(db, reference=reference)


# ─── Webhook callback ──────────────────────────────────────────────────────


@router.post("/callback")
async def payhero_callback(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive a Pay Hero callback, verify it, and queue it for processing.

    The HTTP response is fast (verify + 200) so Pay Hero never times out and
    retries. State mutations happen in a background task that takes an
    advisory lock on the receipt and is idempotent against the UNIQUE
    receipt_number index.
    """
    raw = await verify_payhero(request)
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        logger.error("Pay Hero webhook had non-JSON body after signature check passed")
        return {"status": "ignored", "reason": "non-json"}

    logger.info("Pay Hero callback verified: %s", safe_repr(payload))

    tenant_db = request.headers.get("X-Tenant-ID", "")
    background_tasks.add_task(_apply_callback_async, payload, tenant_db)
    return {"status": "queued"}


def _open_tenant_session(tenant_db: str) -> Session:
    from sqlalchemy.orm import sessionmaker
    from app.config.database import DefaultSessionLocal

    if not tenant_db:
        return DefaultSessionLocal()
    engine = get_tenant_engine(tenant_db)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _apply_callback_async(payload: dict[str, Any], tenant_db: str) -> None:
    """Background worker — runs after the response is sent.

    Idempotent via:
      * Postgres advisory lock on the receipt reference (serialises retries)
      * UNIQUE(receipt_number) on payhero_transactions (last-resort guard).
    """
    db = _open_tenant_session(tenant_db)
    try:
        # Pay Hero callback fields (per docs):
        #   response.ExternalReference, response.MpesaReceiptNumber,
        #   response.Amount, response.Phone, response.ResultCode
        resp = payload.get("response") or payload
        external_ref = resp.get("ExternalReference") or resp.get("external_reference") or ""
        receipt_no = resp.get("MpesaReceiptNumber") or resp.get("receipt_number")
        amount = Decimal(str(resp.get("Amount") or resp.get("amount") or 0))
        result_code = resp.get("ResultCode")
        result_desc = resp.get("ResultDesc") or resp.get("status") or ""

        if not receipt_no and result_code not in (0, "0"):
            logger.info("Pay Hero callback failure or no-receipt: %s", safe_repr(resp))
            _mark_failed(db, external_ref, result_desc)
            return

        lock_id = int(hashlib.sha1((receipt_no or external_ref).encode()).hexdigest()[:15], 16)
        db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

        if receipt_no:
            existing = (
                db.query(PayHeroTransaction)
                .filter(PayHeroTransaction.receipt_number == receipt_no)
                .first()
            )
            if existing:
                db.commit()
                return

        # Match the pending row by external_reference (the anchor we minted
        # at initiate-time). Fall back to bill_ref_number for older rows.
        txn = (
            db.query(PayHeroTransaction)
            .filter(PayHeroTransaction.external_reference == external_ref)
            .first()
        )
        if not txn:
            txn = (
                db.query(PayHeroTransaction)
                .filter(PayHeroTransaction.bill_ref_number == external_ref)
                .first()
            )

        if not txn:
            txn = PayHeroTransaction(
                phone_number=str(resp.get("Phone") or "")[:20],
                amount=amount,
                receipt_number=receipt_no,
                external_reference=external_ref or None,
                status="Success" if result_code in (0, "0") else "Failed",
                transaction_type="STK",
                bill_ref_number=external_ref or None,
                match_basis="unmatched",
                result_desc=str(result_desc)[:255],
            )
            db.add(txn)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            return

        txn.receipt_number = receipt_no
        txn.amount = amount or txn.amount
        txn.status = "Success" if result_code in (0, "0") else "Failed"
        txn.result_desc = str(result_desc)[:255]
        if not txn.external_reference:
            txn.external_reference = external_ref or None

        if txn.status == "Success" and txn.invoice_id:
            invoice = (
                db.query(Invoice)
                .filter(Invoice.invoice_id == txn.invoice_id)
                .with_for_update()
                .first()
            )
            if invoice and amount > 0:
                settle_invoice_match(
                    db,
                    invoice=invoice,
                    txn=txn,
                    match_basis="external_reference",
                )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    except Exception:  # noqa: BLE001 — never propagate from the background task
        db.rollback()
        logger.exception("Pay Hero callback worker raised")
    finally:
        db.close()


def _mark_failed(db: Session, external_ref: str, desc: str) -> None:
    if not external_ref:
        return
    txn = (
        db.query(PayHeroTransaction)
        .filter(PayHeroTransaction.external_reference == external_ref)
        .first()
    )
    if not txn:
        txn = (
            db.query(PayHeroTransaction)
            .filter(PayHeroTransaction.bill_ref_number == external_ref)
            .first()
        )
    if txn:
        txn.status = "Failed"
        txn.result_desc = (desc or "Failed")[:255]
        db.commit()

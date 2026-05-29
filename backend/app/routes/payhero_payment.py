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
from app.models.payhero import PayHeroConfig, PayHeroTransaction
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
        callback_tenant=request.headers.get("X-Tenant-ID"),
    )


@router.get("/status/{reference}", dependencies=[Depends(RequirePermission("billing:manage"))])
def get_payment_status(reference: str, db: Session = Depends(get_db)):
    return check_payment_status(db, reference=reference)


@router.get(
    "/invoice-status/{invoice_id}",
    dependencies=[Depends(RequirePermission("billing:read", "billing:manage"))],
)
def invoice_payment_status(invoice_id: int, db: Session = Depends(get_db)):
    """DB-backed status the cashier screen polls while an STK push is pending.

    Reads our own transaction row (updated by the verified webhook) rather
    than Pay Hero's live API, so a confirmed-then-settled payment is reflected
    the instant the callback commits — mirrors the pharmacy dispense poll.
    """
    invoice = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    latest = (
        db.query(PayHeroTransaction)
        .filter(PayHeroTransaction.invoice_id == invoice_id)
        .order_by(PayHeroTransaction.id.desc())
        .first()
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.status,
        "amount_paid": float(invoice.amount_paid or 0),
        "total_amount": float(invoice.total_amount or 0),
        "mpesa_status": latest.status if latest else None,
        "mpesa_receipt_number": latest.receipt_number if latest else None,
        "mpesa_result_desc": latest.result_desc if latest else None,
    }


# ─── Webhook callback ──────────────────────────────────────────────────────


@router.post("/callback")
@router.post("/callback/{tenant_db}")
async def payhero_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_db: str = "",
):
    """Receive a Pay Hero callback, verify it, and queue it for processing.

    The tenant is taken from the URL path (``/callback/{tenant_db}``) — that
    segment was baked into the callback URL at STK-push time, because Pay Hero
    echoes the URL back but cannot send our ``X-Tenant-ID`` header. We fall
    back to the header for any legacy push that used the bare ``/callback``.

    The HTTP response is fast (verify + 200) so Pay Hero never times out and
    retries. State mutations happen in a background task that takes an
    advisory lock on the receipt and is idempotent against the UNIQUE
    receipt_number index.
    """
    # Resolve the tenant FIRST (cheap, read-only) so we can pick that
    # hospital's own webhook secret before verifying the signature. Each
    # hospital owns its Pay Hero account, so each signs with its own secret;
    # _tenant_webhook_secret returns None for tenants that set none, and
    # verify_payhero then falls back to the global operator secret.
    resolved = _resolve_tenant_db(tenant_db or request.headers.get("X-Tenant-ID", ""))
    expected_secret = _tenant_webhook_secret(resolved) if resolved else None

    raw = await verify_payhero(request, expected_secret=expected_secret)
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        logger.error("Pay Hero webhook had non-JSON body after signature check passed")
        return {"status": "ignored", "reason": "non-json"}

    logger.info("Pay Hero callback verified (tenant=%s): %s", tenant_db or "?", safe_repr(payload))

    if not resolved:
        # No recognised tenant means we have nowhere to apply the receipt.
        # ACK 200 so Pay Hero doesn't hammer retries, but surface it loudly —
        # an operator needs to reconcile it manually.
        logger.error(
            "Pay Hero callback could not be routed to a tenant (path/header gave %r). "
            "Receipt will not auto-settle.", tenant_db,
        )
        return {"status": "ignored", "reason": "unknown-tenant"}

    background_tasks.add_task(_apply_callback_async, payload, resolved)
    return {"status": "queued"}


def _resolve_tenant_db(candidate: str) -> str | None:
    """Validate a tenant db_name against the master registry before we open an
    engine against it — defends against connecting to an arbitrary database
    name and confirms the tenant is real + active."""
    candidate = (candidate or "").strip()
    if not candidate:
        return None
    from app.config.database import MasterSessionLocal
    from app.models.master import Tenant

    master = MasterSessionLocal()
    try:
        t = (
            master.query(Tenant)
            .filter(Tenant.db_name == candidate, Tenant.is_active == True)  # noqa: E712
            .first()
        )
        return candidate if t else None
    except Exception:  # noqa: BLE001 — master lookup must never crash the webhook
        logger.exception("Pay Hero callback tenant lookup failed for %r", candidate)
        return None
    finally:
        master.close()


def _open_tenant_session(tenant_db: str) -> Session:
    from sqlalchemy.orm import sessionmaker

    engine = get_tenant_engine(tenant_db)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _tenant_webhook_secret(tenant_db: str) -> str | None:
    """Return the tenant's own Pay Hero webhook secret (decrypted), or None.

    Each hospital owns its Pay Hero account and signs callbacks with its own
    HMAC secret. None means the tenant configured no secret, so verify_payhero
    falls back to the global settings.PAYHERO_WEBHOOK_SECRET. Best-effort: a
    lookup failure returns None (→ global fallback) rather than crashing the
    webhook — the signature check still gates, fail-closed, in production.
    """
    if not tenant_db:
        return None
    try:
        db = _open_tenant_session(tenant_db)
    except Exception:  # noqa: BLE001
        logger.exception("Could not open tenant session for webhook-secret lookup: %s", tenant_db)
        return None
    try:
        from app.utils.encryption import decrypt_data

        cfg = db.query(PayHeroConfig).first()
        if cfg and cfg.payhero_webhook_secret_encrypted:
            return decrypt_data(cfg.payhero_webhook_secret_encrypted)
        return None
    except Exception:  # noqa: BLE001
        logger.exception("Per-tenant webhook-secret lookup failed for %s", tenant_db)
        return None
    finally:
        db.close()


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
            _mark_failed(db, external_ref, result_desc, tenant_db)
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
        snapshot = _txn_snapshot(txn)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            snapshot = None
        if snapshot:
            _notify_payment(tenant_db, snapshot)
    except Exception:  # noqa: BLE001 — never propagate from the background task
        db.rollback()
        logger.exception("Pay Hero callback worker raised")
    finally:
        db.close()


def _mark_failed(db: Session, external_ref: str, desc: str, tenant_db: str = "") -> None:
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
        snapshot = _txn_snapshot(txn)
        db.commit()
        _notify_payment(tenant_db, snapshot)


def _txn_snapshot(txn: PayHeroTransaction) -> dict[str, Any]:
    """Plain-value snapshot taken before commit (avoids a post-commit reload)
    so we can broadcast the outcome after the session closes."""
    return {
        "type": "payment_update",
        "invoice_id": txn.invoice_id,
        "dispense_id": txn.dispense_id,
        "external_reference": txn.external_reference,
        "status": txn.status,
        "receipt_number": txn.receipt_number,
        "result_desc": txn.result_desc,
        "amount": float(txn.amount or 0),
    }


def _notify_payment(tenant_db: str, snapshot: dict[str, Any] | None) -> None:
    """Push a live payment update to the tenant's checkout screens. Best-effort:
    a failure here must never affect settlement (polling is the fallback)."""
    if not tenant_db or not snapshot:
        return
    try:
        from app.core.websocket import manager
        manager.publish_topic_threadsafe(f"payment:{tenant_db}", {**snapshot, "tenant": tenant_db})
    except Exception:  # noqa: BLE001
        logger.exception("Payment WS notify failed for tenant=%s", tenant_db)

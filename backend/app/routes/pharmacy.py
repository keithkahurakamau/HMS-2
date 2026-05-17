from decimal import Decimal
from typing import List, Union
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
# ADDED Location to the imports here
from app.models.inventory import InventoryItem, StockBatch, DispenseLog, Location
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.idempotency import IdempotencyKey
from app.models.mpesa import MpesaTransaction
from app.schemas.pharmacy import (
    CashPaymentResponse,
    DispensePaymentRequest,
    DispenseRequest,
    DispenseResponse,
    MpesaInitResponse,
)
from app.core.dependencies import get_current_user, RequirePermission
from app.services.accounting_posting import (
    payment_method_to_key,
    post_dispense_pair,
    post_from_event,
)
from app.services.mpesa_service import initiate_stk_push
from app.utils.audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pharmacy", tags=["Pharmacy"])

@router.get("/inventory", dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_pharmacy_inventory(db: Session = Depends(get_db)):
    """Fetches all stock currently physically located in the Pharmacy."""
    # Find the Pharmacy location
    pharmacy_location = db.query(Location).filter(Location.name == "Pharmacy").first()
    if not pharmacy_location:
        return []

    # Join StockBatch with Master Inventory to get names, prices, and batches
    inventory = db.query(
        InventoryItem.item_id,
        InventoryItem.name,
        InventoryItem.category,
        InventoryItem.unit_price,
        StockBatch.batch_id,
        StockBatch.batch_number,
        StockBatch.quantity,
        StockBatch.expiry_date
    ).join(
        StockBatch, InventoryItem.item_id == StockBatch.item_id
    ).filter(
        StockBatch.location_id == pharmacy_location.location_id,
        StockBatch.quantity > 0
    ).order_by(StockBatch.expiry_date.asc()).all()

    return [dict(item._mapping) for item in inventory]

@router.post("/dispense", response_model=DispenseResponse, dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def dispense_drug(req: DispenseRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        # 1. Idempotency Check (Prevent accidental double-clicks from charging twice)
        idem_key = db.query(IdempotencyKey).filter(IdempotencyKey.key == req.idempotency_key).first()
        if idem_key:
            return json.loads(idem_key.response_body) # Return the exact same response as the first time

        # 2. Inventory Check & Deduction (Using Specific StockBatch for FEFO)
        batch = db.query(StockBatch).with_for_update().filter(StockBatch.batch_id == req.batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Stock batch not found in Pharmacy.")
        if batch.quantity < req.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Only {batch.quantity} remaining in batch {batch.batch_number}.")
            
        # Fetch the master catalog item to get pricing
        item = db.query(InventoryItem).filter(InventoryItem.item_id == batch.item_id).first()
        
        # Deduct Physical Stock
        batch.quantity -= req.quantity
        total_cost = float(item.unit_price) * req.quantity

        # 3. Create Dispense Log
        log_entry = DispenseLog(
            item_id=item.item_id, batch_id=batch.batch_id, patient_id=req.patient_id, record_id=req.record_id,
            quantity_dispensed=req.quantity, total_cost=total_cost,
            dispensed_by=current_user["user_id"], notes=req.notes
        )
        db.add(log_entry)
        db.flush()

        # 4. Billing Integration (If patient is known, route to their bill)
        if req.patient_id:
            # Find an active pending invoice or create one
            invoice = db.query(Invoice).filter(Invoice.patient_id == req.patient_id, Invoice.status == "Pending").first()
            if not invoice:
                invoice = Invoice(patient_id=req.patient_id, total_amount=0, created_by=current_user["user_id"])
                db.add(invoice)
                db.flush()
            
            invoice.total_amount += total_cost
            
            # Add line item detailing the exact drug dispensed
            line_item = InvoiceItem(
                invoice_id=invoice.invoice_id,
                description=f"Pharmacy: {item.name} x{req.quantity}",
                amount=total_cost, item_type="Pharmacy", reference_id=log_entry.dispense_id
            )
            db.add(line_item)

        # 4b. Auto-post the dispensation to the ledger.
        # Revenue side uses unit_price (what we charged), COGS side uses
        # unit_cost (what we paid). Both post in the same transaction.
        cogs_amount = float(item.unit_cost or 0) * req.quantity
        post_dispense_pair(
            db,
            dispense_id=log_entry.dispense_id,
            revenue_amount=total_cost,
            cogs_amount=cogs_amount,
            memo=f"Pharmacy: {item.name} x{req.quantity}",
            user_id=current_user["user_id"],
        )

        # 5. Audit & Idempotency Save.
        # Always include the invoice context in the response so the frontend
        # can immediately prompt for payment collection — None for walk-ins.
        invoice_id = invoice.invoice_id if req.patient_id and invoice else None
        invoice_balance = None
        if invoice_id is not None:
            invoice_balance = float((invoice.total_amount or Decimal(0)) - (invoice.amount_paid or Decimal(0)))

        resp_data = {
            "dispense_id": log_entry.dispense_id,
            "item_id": item.item_id,
            "quantity_dispensed": req.quantity,
            "total_cost": total_cost,
            "dispensed_at": str(log_entry.dispensed_at),
            "invoice_id": invoice_id,
            "invoice_balance": invoice_balance,
        }

        db.add(IdempotencyKey(key=req.idempotency_key, response_body=json.dumps(resp_data)))
        log_audit(db, current_user["user_id"], "CREATE", "DispenseLog", log_entry.dispense_id, None, {"item": item.name, "qty": req.quantity}, request.client.host)

        db.commit()
        return resp_data

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Payment collection (post-dispense) ─────────────────────────────────────

def _resolve_dispense_invoice(db: Session, dispense_id: int) -> tuple[DispenseLog, Invoice]:
    """Common lookup: dispense + its linked invoice. Walk-in dispenses (no
    invoice) cannot be paid via this flow — they're cash-on-counter and
    can be recorded via the cashier module."""
    dispense = db.query(DispenseLog).filter(DispenseLog.dispense_id == dispense_id).first()
    if not dispense:
        raise HTTPException(404, detail="Dispense record not found.")
    if not dispense.patient_id:
        raise HTTPException(
            400,
            detail="This dispense has no linked patient/invoice — collect payment manually via the cashier.",
        )
    invoice = (
        db.query(Invoice)
        .join(InvoiceItem, InvoiceItem.invoice_id == Invoice.invoice_id)
        .filter(InvoiceItem.reference_id == dispense.dispense_id,
                InvoiceItem.item_type == "Pharmacy")
        .order_by(Invoice.invoice_id.desc())
        .first()
    )
    if not invoice:
        raise HTTPException(404, detail="No invoice found for this dispense.")
    return dispense, invoice


@router.post(
    "/dispense/{dispense_id}/pay",
    response_model=Union[CashPaymentResponse, MpesaInitResponse],
    dependencies=[Depends(RequirePermission("pharmacy:manage"))],
)
def collect_dispense_payment(
    dispense_id: int,
    req: DispensePaymentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Collect payment for a pharmacy dispensation.

    cash    — record a Payment row, mark invoice (partially) paid,
              post billing.payment.cash to the ledger. Idempotent on the
              Payment.transaction_reference if supplied.
    mpesa   — initiate an STK push tied to (dispense_id, invoice_id).
              Returns checkout_request_id; the actual ledger posting
              happens in the M-Pesa callback when the customer confirms.
    card    — returns 501 for now; integration in a future PR.
    """
    if req.method == "card":
        raise HTTPException(
            status_code=501,
            detail="Card payments are not yet integrated. Use Cash or M-Pesa.",
        )

    dispense, invoice = _resolve_dispense_invoice(db, dispense_id)

    if invoice.status == "Paid":
        raise HTTPException(400, detail="Invoice is already fully paid.")

    amt = Decimal(str(req.amount))
    outstanding = (invoice.total_amount or Decimal(0)) - (invoice.amount_paid or Decimal(0))
    if amt > outstanding:
        raise HTTPException(
            400,
            detail=f"Amount {amt} exceeds outstanding balance {outstanding}.",
        )

    # ── Cash ────────────────────────────────────────────────────────────────
    if req.method == "cash":
        payment = Payment(
            invoice_id=invoice.invoice_id,
            amount=amt,
            payment_method="Cash",
            transaction_reference=req.transaction_reference,
        )
        db.add(payment)
        db.flush()

        invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amt
        invoice.status = "Paid" if invoice.amount_paid >= invoice.total_amount else "Partially Paid"
        if invoice.status == "Paid":
            invoice.payment_method = "Cash"

        # Ledger: Dr Cash / Cr AR via the auto-posting bridge.
        post_from_event(
            db,
            source_key=payment_method_to_key("Cash"),
            source_id=payment.payment_id,
            amount=amt,
            memo=f"Pharmacy dispense #{dispense_id} — cash payment",
            reference=f"INV-{invoice.invoice_id}",
            user_id=current_user["user_id"],
        )

        log_audit(db, current_user["user_id"], "CREATE", "Payment", payment.payment_id, None,
                  {"dispense_id": dispense_id, "amount": float(amt), "method": "Cash"},
                  request.client.host)
        db.commit()
        return CashPaymentResponse(
            status="paid" if invoice.status == "Paid" else "partial",
            payment_id=payment.payment_id,
            invoice_id=invoice.invoice_id,
            amount_paid_total=float(invoice.amount_paid),
            invoice_status=invoice.status,
        )

    # ── M-Pesa ──────────────────────────────────────────────────────────────
    # method == 'mpesa'
    if not req.phone_number:
        raise HTTPException(400, detail="phone_number is required for M-Pesa payments.")

    # Idempotency: if there's an existing pending STK for this dispense, return it.
    existing = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.dispense_id == dispense_id,
            MpesaTransaction.status == "Pending",
        )
        .first()
    )
    if existing and existing.checkout_request_id:
        return MpesaInitResponse(
            status="stk_push_sent",
            checkout_request_id=existing.checkout_request_id,
            mpesa_transaction_id=existing.id,
        )

    # Build a callback URL. Production: the operator wires PUBLIC_BASE_URL.
    base = os.environ.get("PUBLIC_BASE_URL", request.base_url.rstrip("/") if hasattr(request, "base_url") else "")
    callback_url = f"{base}/api/payments/mpesa/callback" if base else "https://placeholder.invalid/callback"

    try:
        txn_payload = initiate_stk_push(
            db=db,
            phone_number=req.phone_number,
            amount=float(amt),
            invoice_id=invoice.invoice_id,
            callback_url=callback_url,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Pharmacy M-Pesa STK push failed for dispense=%s", dispense_id)
        raise HTTPException(status_code=502, detail=f"Could not contact M-Pesa: {exc}")

    # initiate_stk_push inserted a row keyed by invoice_id; attach the
    # dispense_id back-ref so the callback can resolve to this dispense.
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == txn_payload.get("checkout_request_id"))
        .order_by(MpesaTransaction.id.desc())
        .first()
    )
    if txn:
        txn.dispense_id = dispense_id
        db.commit()

    log_audit(db, current_user["user_id"], "CREATE", "MpesaTransaction", txn.id if txn else 0, None,
              {"dispense_id": dispense_id, "amount": float(amt), "phone": req.phone_number},
              request.client.host)

    return MpesaInitResponse(
        status="stk_push_sent",
        checkout_request_id=txn_payload.get("checkout_request_id", ""),
        mpesa_transaction_id=txn.id if txn else 0,
    )


@router.get(
    "/dispense/{dispense_id}/payment-status",
    dependencies=[Depends(RequirePermission("pharmacy:read"))],
)
def dispense_payment_status(dispense_id: int, db: Session = Depends(get_db)):
    """Lightweight status endpoint the frontend can poll while waiting for
    an STK push to resolve."""
    _, invoice = _resolve_dispense_invoice(db, dispense_id)
    pending_mpesa = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.dispense_id == dispense_id)
        .order_by(MpesaTransaction.id.desc())
        .first()
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.status,
        "amount_paid": float(invoice.amount_paid or 0),
        "total_amount": float(invoice.total_amount or 0),
        "mpesa_status": pending_mpesa.status if pending_mpesa else None,
        "mpesa_receipt_number": pending_mpesa.receipt_number if pending_mpesa else None,
        "mpesa_result_desc": pending_mpesa.result_desc if pending_mpesa else None,
    }
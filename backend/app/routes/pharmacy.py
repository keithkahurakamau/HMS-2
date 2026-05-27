from decimal import Decimal
from typing import Union
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.idempotency import idempotent_guard
from app.models.inventory import InventoryItem, StockBatch, DispenseLog, Location
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.payhero import PayHeroTransaction
from app.schemas.pharmacy import (
    CashPaymentResponse,
    DispensePaymentRequest,
    DispenseRequest,
    DispenseResponse,
    PayHeroInitResponse,
)
from app.core.dependencies import get_current_user, RequirePermission
from app.services.accounting_posting import (
    payment_method_to_key,
    post_dispense_pair,
    post_from_event,
)
from app.services.payhero_service import initiate_stk_push
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
        # 1. Idempotency Check (IDEM-001 scoped per-user + advisory lock)
        cached, persist = idempotent_guard(
            db,
            user_id=current_user["user_id"],
            endpoint="pharmacy.dispense",
            key=req.idempotency_key,
            body=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
        )
        if cached is not None:
            return cached

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
        # Money stays in Decimal so the Numeric(10,2) columns aren't silently
        # upcast to float — that mismatch broke (total_amount - amount_paid)
        # below when one operand had been mutated to float.
        total_cost = Decimal(item.unit_price) * req.quantity

        # 3. Create Dispense Log
        log_entry = DispenseLog(
            item_id=item.item_id, batch_id=batch.batch_id, patient_id=req.patient_id, record_id=req.record_id,
            quantity_dispensed=req.quantity, total_cost=total_cost,
            dispensed_by=current_user["user_id"], notes=req.notes
        )
        db.add(log_entry)
        db.flush()

        # 4. Billing Integration — always create an invoice so the same
        # payment + receipt pipeline works for walk-in OTC and patient Rx
        # alike. For known patients we roll into their open Pending
        # invoice; for walk-ins we mint a fresh single-dispense invoice
        # with patient_id NULL.
        if req.patient_id:
            # SELECT ... FOR UPDATE so two concurrent dispenses against the
            # same patient can't both miss the existing Pending invoice and
            # each create a new one (which would leave the patient with
            # duplicate Pending invoices and split payment allocation).
            invoice = (
                db.query(Invoice)
                .filter(Invoice.patient_id == req.patient_id, Invoice.status == "Pending")
                .order_by(Invoice.invoice_id.asc())
                .with_for_update()
                .first()
            )
            if not invoice:
                invoice = Invoice(patient_id=req.patient_id, total_amount=0,
                                  created_by=current_user["user_id"])
                db.add(invoice)
                db.flush()
        else:
            # Walk-in: by design we mint a fresh per-dispense invoice so
            # each retail sale has its own receipt. No aggregation.
            invoice = Invoice(patient_id=None, total_amount=0,
                              created_by=current_user["user_id"])
            db.add(invoice)
            db.flush()

        invoice.total_amount += total_cost
        db.add(InvoiceItem(
            invoice_id=invoice.invoice_id,
            description=f"Pharmacy: {item.name} x{req.quantity}",
            amount=total_cost, item_type="Pharmacy",
            reference_id=log_entry.dispense_id,
        ))

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
        invoice_id = invoice.invoice_id
        invoice_balance = float((invoice.total_amount or Decimal(0)) - (invoice.amount_paid or Decimal(0)))

        resp_data = {
            "dispense_id": log_entry.dispense_id,
            "item_id": item.item_id,
            "quantity_dispensed": req.quantity,
            "total_cost": float(total_cost),
            "dispensed_at": str(log_entry.dispensed_at),
            "invoice_id": invoice_id,
            "invoice_balance": invoice_balance,
        }

        persist(resp_data)
        log_audit(db, current_user["user_id"], "CREATE", "DispenseLog", log_entry.dispense_id, None, {"item": item.name, "qty": req.quantity}, request.client.host)

        db.commit()
        return resp_data

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("pharmacy.dispense failed (idem=%s)", getattr(req, "idempotency_key", None))
        raise HTTPException(status_code=500, detail=str(e))


# ─── Payment collection (post-dispense) ─────────────────────────────────────

def _resolve_dispense_invoice(db: Session, dispense_id: int) -> tuple[DispenseLog, Invoice]:
    """Find a dispense and the invoice that holds its line item.
    Works for both known-patient and walk-in dispenses — both now have
    an Invoice row (walk-ins have patient_id NULL)."""
    dispense = db.query(DispenseLog).filter(DispenseLog.dispense_id == dispense_id).first()
    if not dispense:
        raise HTTPException(404, detail="Dispense record not found.")
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
    response_model=Union[CashPaymentResponse, PayHeroInitResponse],
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

    cash  — record a Payment row, mark invoice (partially) paid, post
            billing.payment.cash to the ledger.
    card  — same shape as cash, but payment_method='Card' and posts
            billing.payment.bank (cards settle into the bank account
            same as bank transfers). transaction_reference holds the
            card terminal auth code if supplied.
    mpesa — initiate a Pay Hero STK push tied to (dispense_id, invoice_id).
            "mpesa" remains the customer-facing label because that is
            what the patient sees on their phone; the rail is Pay Hero.
            The actual ledger posting happens in the Pay Hero callback
            when the customer confirms the prompt.
    """
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

    # ── Cash + Card (immediate settlement) ──────────────────────────────────
    if req.method in ("cash", "card"):
        method_label = "Cash" if req.method == "cash" else "Card"
        payment = Payment(
            invoice_id=invoice.invoice_id,
            amount=amt,
            payment_method=method_label,
            transaction_reference=req.transaction_reference,
        )
        db.add(payment)
        db.flush()

        invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amt
        invoice.status = "Paid" if invoice.amount_paid >= invoice.total_amount else "Partially Paid"
        if invoice.status == "Paid":
            invoice.payment_method = method_label

        # Ledger: cash → 1110 Cash; card → 1120 Bank (settles into bank
        # account same as a transfer). payment_method_to_key picks the
        # right source_key for each.
        post_from_event(
            db,
            source_key=payment_method_to_key(method_label),
            source_id=payment.payment_id,
            amount=amt,
            memo=f"Pharmacy dispense #{dispense_id} — {method_label.lower()} payment",
            reference=f"INV-{invoice.invoice_id}",
            user_id=current_user["user_id"],
        )

        log_audit(db, current_user["user_id"], "CREATE", "Payment", payment.payment_id, None,
                  {"dispense_id": dispense_id, "amount": float(amt), "method": method_label},
                  request.client.host)
        db.commit()
        return CashPaymentResponse(
            status="paid" if invoice.status == "Paid" else "partial",
            payment_id=payment.payment_id,
            invoice_id=invoice.invoice_id,
            amount_paid_total=float(invoice.amount_paid),
            invoice_status=invoice.status,
        )

    # ── M-Pesa via Pay Hero aggregator ──────────────────────────────────
    # method == 'mpesa' (customer-facing label; the rail is Pay Hero)
    if not req.phone_number:
        raise HTTPException(400, detail="phone_number is required for M-Pesa payments.")

    # Idempotency: if there's an existing pending STK for this dispense, return it.
    existing = (
        db.query(PayHeroTransaction)
        .filter(
            PayHeroTransaction.dispense_id == dispense_id,
            PayHeroTransaction.status == "Pending",
        )
        .first()
    )
    if existing and existing.external_reference:
        return PayHeroInitResponse(
            status="stk_push_sent",
            external_reference=existing.external_reference,
            payhero_reference=existing.payhero_reference,
            transaction_id=existing.id,
        )

    try:
        txn_payload = initiate_stk_push(
            db,
            phone_number=req.phone_number,
            amount=float(amt),
            invoice_id=invoice.invoice_id,
            dispense_id=dispense_id,
            callback_tenant=request.headers.get("X-Tenant-ID"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Pay Hero STK push failed for dispense=%s", dispense_id)
        raise HTTPException(status_code=502, detail=f"Could not contact Pay Hero: {exc}")

    log_audit(
        db,
        current_user["user_id"],
        "CREATE",
        "PayHeroTransaction",
        txn_payload.get("transaction_id") or 0,
        None,
        {"dispense_id": dispense_id, "amount": float(amt), "phone": req.phone_number},
        request.client.host,
    )

    return PayHeroInitResponse(
        status="stk_push_sent",
        external_reference=txn_payload.get("external_reference", ""),
        payhero_reference=txn_payload.get("reference"),
        transaction_id=txn_payload.get("transaction_id") or 0,
    )


@router.get(
    "/dispense/{dispense_id}/payment-status",
    dependencies=[Depends(RequirePermission("pharmacy:read"))],
)
def dispense_payment_status(dispense_id: int, db: Session = Depends(get_db)):
    """Lightweight status endpoint the frontend can poll while waiting for
    an STK push to resolve."""
    _, invoice = _resolve_dispense_invoice(db, dispense_id)
    pending = (
        db.query(PayHeroTransaction)
        .filter(PayHeroTransaction.dispense_id == dispense_id)
        .order_by(PayHeroTransaction.id.desc())
        .first()
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.status,
        "amount_paid": float(invoice.amount_paid or 0),
        "total_amount": float(invoice.total_amount or 0),
        "mpesa_status": pending.status if pending else None,
        "mpesa_receipt_number": pending.receipt_number if pending else None,
        "mpesa_result_desc": pending.result_desc if pending else None,
    }


# ─── Receipt ────────────────────────────────────────────────────────────────

@router.get(
    "/dispense/{dispense_id}/receipt",
    dependencies=[Depends(RequirePermission("pharmacy:read"))],
)
def dispense_receipt(dispense_id: int, db: Session = Depends(get_db)):
    """Receipt payload for printing. Includes hospital branding settings,
    all line items on the invoice, all payments collected, and totals.

    The frontend renders this through utils/printTemplates so the look
    stays consistent with prescriptions / cheques / etc."""
    dispense, invoice = _resolve_dispense_invoice(db, dispense_id)

    items = (
        db.query(InvoiceItem)
        .filter(InvoiceItem.invoice_id == invoice.invoice_id)
        .order_by(InvoiceItem.id)
        .all()
    )
    payments = (
        db.query(Payment)
        .filter(Payment.invoice_id == invoice.invoice_id)
        .order_by(Payment.payment_id)
        .all()
    )

    # Hospital branding from settings — fall back gracefully if not set.
    from app.models.settings import HospitalSetting
    branding = {
        row.key: row.value
        for row in db.query(HospitalSetting)
        .filter(HospitalSetting.category == "branding").all()
    }
    receipt_no = f"RCP-{invoice.invoice_id:08d}"

    cashier = None
    if invoice.created_by:
        from app.models.user import User
        u = db.query(User).filter(User.user_id == invoice.created_by).first()
        cashier = u.full_name if u else None

    patient_label = "Walk-in"
    if dispense.patient_id:
        from app.models.patient import Patient
        p = db.query(Patient).filter(Patient.patient_id == dispense.patient_id).first()
        if p:
            patient_label = f"{p.surname}, {p.other_names}".strip(", ")

    return {
        "receipt_no": receipt_no,
        "invoice_id": invoice.invoice_id,
        "issued_at": invoice.billing_date.isoformat() if invoice.billing_date else None,
        "dispense_id": dispense.dispense_id,
        "patient": patient_label,
        "cashier": cashier,
        "hospital": {
            "name": branding.get("hospital_name") or "MediFleet",
            "tagline": branding.get("tagline") or "",
            "logo_url": branding.get("logo_url") or "",
        },
        "items": [
            {
                "description": it.description,
                "amount": float(it.amount),
                "item_type": it.item_type,
            } for it in items
        ],
        "payments": [
            {
                "method": p.payment_method,
                "amount": float(p.amount),
                "reference": p.transaction_reference,
                "paid_at": p.payment_date.isoformat() if p.payment_date else None,
            } for p in payments
        ],
        "totals": {
            "total": float(invoice.total_amount or 0),
            "paid": float(invoice.amount_paid or 0),
            "balance": float((invoice.total_amount or Decimal(0))
                             - (invoice.amount_paid or Decimal(0))),
            "status": invoice.status,
        },
    }


# ─── Transaction ledger ────────────────────────────────────────────────────

@router.get(
    "/transactions",
    dependencies=[Depends(RequirePermission("pharmacy:read"))],
)
def pharmacy_transactions(
    db: Session = Depends(get_db),
    from_date: str | None = None,
    to_date: str | None = None,
    method: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Paginated ledger of pharmacy transactions.

    One row per dispense: rolls up its invoice + payments. Filters:
    - from_date / to_date (YYYY-MM-DD) match against dispensed_at
    - method matches the *primary* (first) payment method on the invoice
      ('Cash', 'M-Pesa', 'Card', or 'Unpaid' for no-payment-yet)
    - status: 'Paid' | 'Partially Paid' | 'Pending' | 'Pending M-Pesa'

    All filters apply in SQL **before** pagination so each page reliably
    returns up to `limit` rows that match, and ``total`` reflects the
    filtered cardinality.
    """
    from datetime import date as _date, timedelta, datetime
    from sqlalchemy import func, and_
    from app.models.user import User

    limit = max(1, min(limit, 500))

    # Parse the date range strictly as YYYY-MM-DD so to_date doesn't quietly
    # accept a full ISO timestamp and read past the user's intent.
    parsed_from = parsed_to_cutoff = None
    if from_date:
        try:
            parsed_from = _date.fromisoformat(from_date)
        except ValueError:
            raise HTTPException(400, detail=f"Bad from_date: {from_date} (expected YYYY-MM-DD)")
    if to_date:
        try:
            parsed_to_cutoff = datetime.combine(_date.fromisoformat(to_date), datetime.min.time()) + timedelta(days=1)
        except ValueError:
            raise HTTPException(400, detail=f"Bad to_date: {to_date} (expected YYYY-MM-DD)")

    # Correlated subquery: the first payment_method for each invoice. NULL
    # when no Payment row exists yet (= "Unpaid"). LIMIT 1 keeps it cheap;
    # the index on payments.invoice_id makes it index-only.
    first_pm_subq = (
        db.query(Payment.payment_method)
        .filter(Payment.invoice_id == Invoice.invoice_id)
        .order_by(Payment.payment_id.asc())
        .limit(1)
        .correlate(Invoice)
        .scalar_subquery()
    )

    # Base join — DispenseLog left-joined to its invoice (some dispenses may
    # predate the always-create-an-invoice contract), item, cashier.
    q = (
        db.query(DispenseLog, Invoice, InventoryItem, User, first_pm_subq.label("primary_method"))
        .outerjoin(InvoiceItem, and_(
            InvoiceItem.reference_id == DispenseLog.dispense_id,
            InvoiceItem.item_type == "Pharmacy",
        ))
        .outerjoin(Invoice, Invoice.invoice_id == InvoiceItem.invoice_id)
        .outerjoin(InventoryItem, InventoryItem.item_id == DispenseLog.item_id)
        .outerjoin(User, User.user_id == DispenseLog.dispensed_by)
    )

    if parsed_from is not None:
        q = q.filter(DispenseLog.dispensed_at >= parsed_from)
    if parsed_to_cutoff is not None:
        q = q.filter(DispenseLog.dispensed_at < parsed_to_cutoff)

    if status:
        # Treat missing invoice as 'Pending' so the filter is honest for
        # legacy rows that pre-date the always-mint-an-invoice contract.
        q = q.filter(func.coalesce(Invoice.status, "Pending") == status)

    if method:
        if method == "Unpaid":
            q = q.filter(first_pm_subq.is_(None))
        else:
            q = q.filter(first_pm_subq == method)

    # Total reflects the same filter set; skip on offset>0 to save the
    # round-trip when the frontend is just paging deeper. Computed *before*
    # the ORDER BY is added — Postgres rejects an ORDER BY on a non-grouped
    # column when the SELECT collapses to an aggregate.
    total = q.with_entities(func.count(DispenseLog.dispense_id)).scalar() if offset == 0 else None

    rows = q.order_by(DispenseLog.dispensed_at.desc()).offset(offset).limit(limit).all()

    out = []
    for d, invoice, item, cashier, primary_method in rows:
        # Payment count comes from a single targeted query rather than
        # joining payments into the main query, which would multiply rows.
        payment_count = (
            db.query(func.count(Payment.payment_id))
              .filter(Payment.invoice_id == invoice.invoice_id)
              .scalar()
            if invoice else 0
        )
        out.append({
            "dispense_id": d.dispense_id,
            "dispensed_at": d.dispensed_at.isoformat() if d.dispensed_at else None,
            "item_name": item.name if item else "—",
            "quantity": d.quantity_dispensed,
            "total_cost": float(d.total_cost),
            "patient_id": d.patient_id,
            "cashier": cashier.full_name if cashier else None,
            "invoice_id": invoice.invoice_id if invoice else None,
            "invoice_status": invoice.status if invoice else "Pending",
            "amount_paid": float(invoice.amount_paid or 0) if invoice else 0,
            "payment_method": primary_method,
            "payment_count": payment_count,
        })

    return {"items": out, "total": total, "limit": limit, "offset": offset}
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal, InvalidOperation

from app.config.database import get_db
from app.models.billing import Invoice, InvoiceItem, Payment
from app.core.idempotency import idempotent_guard
from app.schemas.billing import PaymentRequest, InvoiceResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.services.accounting_posting import post_from_event, payment_method_to_key
from app.utils.audit import log_audit
from pydantic import BaseModel
from sqlalchemy.orm import joinedload, selectinload

class ConsultationFeeRequest(BaseModel):
    patient_id: int
    amount: float = 1000.0

router = APIRouter(prefix="/api/billing", tags=["Billing & Cashier"])


def _money(value) -> Decimal:
    """Coerce an inbound amount to a 2dp Decimal.

    CORRECTNESS (C1): payment amounts arrive as JSON floats but invoice columns
    are ``Numeric`` → psycopg2 hands them back as ``Decimal``. ``Decimal + float``
    raises ``TypeError`` (pharmacy hit this exact bug; billing had not been
    fixed), so every inbound amount is normalised to ``Decimal`` here before it
    touches a money column. Rejects non-positive / non-numeric values (H4).
    """
    try:
        amt = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payment amount.")
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")
    return amt

@router.get("/queue", response_model=List[InvoiceResponse], dependencies=[Depends(RequirePermission("billing:manage"))])
def get_billing_queue(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Returns all patients with Pending invoices.

    DB-002: eagerly loads patient + items so the per-row attribute accesses
    in the loop below don't trigger N+1 queries (one per invoice).
    """
    invoices = (
        db.query(Invoice)
        .options(joinedload(Invoice.patient), selectinload(Invoice.items))
        .filter(Invoice.status.in_(["Pending", "Partially Paid", "Pending M-Pesa"]))
        .order_by(Invoice.billing_date.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    result = []
    for inv in invoices:
        inv_dict = {
            "invoice_id": inv.invoice_id,
            "patient_id": inv.patient_id,
            "patient_name": f"{inv.patient.surname}, {inv.patient.other_names}" if inv.patient else "Unknown",
            "patient_opd": inv.patient.outpatient_no if inv.patient else "N/A",
            "total_amount": float(inv.total_amount),
            "amount_paid": float(inv.amount_paid),
            "status": inv.status,
            "billing_date": inv.billing_date,
            "items": [{"id": i.id, "description": i.description, "amount": float(i.amount), "item_type": i.item_type} for i in inv.items]
        }
        result.append(inv_dict)
    return result

@router.post("/process-payment", dependencies=[Depends(RequirePermission("billing:manage"))])
def process_cash_card_payment(req: PaymentRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        # IDEM-001: scoped to (user_id, endpoint, key) so attackers can't
        # replay another user's key. idempotent_guard also takes a pg
        # advisory lock to serialise concurrent duplicates.
        cached, persist = idempotent_guard(
            db,
            user_id=current_user["user_id"],
            endpoint="billing.process-payment",
            key=req.idempotency_key,
            body=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
        )
        if cached is not None:
            return cached

        amt = _money(req.amount)

        invoice = db.query(Invoice).with_for_update().filter(Invoice.invoice_id == req.invoice_id).first()
        if not invoice or invoice.status == "Paid":
            raise HTTPException(status_code=400, detail="Invalid or already paid invoice")

        invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amt
        if invoice.amount_paid >= invoice.total_amount:
            invoice.status = "Paid"
        else:
            invoice.status = "Partially Paid"

        payment = Payment(invoice_id=invoice.invoice_id, amount=amt, payment_method=req.payment_method)
        db.add(payment)
        db.flush()

        # Auto-post to the ledger. Wrapped in the same transaction so
        # the entry rolls back with the payment if the commit fails.
        post_from_event(
            db,
            source_key=payment_method_to_key(req.payment_method),
            source_id=payment.payment_id,
            amount=amt,
            memo=f"Payment against Invoice #{invoice.invoice_id}",
            reference=f"INV-{invoice.invoice_id}",
            user_id=current_user.get("user_id"),
        )

        resp_data = {"status": "Success", "invoice_status": invoice.status, "payment_id": payment.payment_id}
        persist(resp_data)
        log_audit(db, current_user["user_id"], "CREATE", "Payment", payment.payment_id, None, {"amount": float(amt), "method": req.payment_method}, request.client.host)

        db.commit()
        return resp_data

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/consultation-fee", dependencies=[Depends(RequirePermission("clinical:write"))])
def charge_consultation_fee(req: ConsultationFeeRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # CORRECTNESS (C2): coerce to Decimal (was Decimal += float TypeError),
    # lock the existing Pending invoice to serialise concurrent fee charges,
    # and wrap in try/except rollback so a mid-handler failure can't leave the
    # session poisoned for the unguarded commit.
    amt = _money(req.amount)
    try:
        invoice = (
            db.query(Invoice)
            .with_for_update()
            .filter(Invoice.patient_id == req.patient_id, Invoice.status == "Pending")
            .first()
        )

        if not invoice:
            invoice = Invoice(
                patient_id=req.patient_id,
                total_amount=Decimal(0),
                status="Pending",
                created_by=current_user["user_id"]
            )
            db.add(invoice)
            db.flush()

        invoice.total_amount = (invoice.total_amount or Decimal(0)) + amt

        item = InvoiceItem(
            invoice_id=invoice.invoice_id,
            description="Doctor Consultation Fee",
            amount=amt,
            item_type="Consultation"
        )
        db.add(item)
        db.flush()  # ensure item.id is available for the posting source_id

        # Auto-post invoice charge to the ledger (Dr AR / Cr revenue per mapping).
        post_from_event(
            db,
            source_key="billing.invoice.created",
            source_id=item.id,
            amount=amt,
            memo=f"Consultation fee · Invoice #{invoice.invoice_id}",
            reference=f"INV-{invoice.invoice_id}",
            user_id=current_user["user_id"],
        )

        log_audit(db, current_user["user_id"], "CREATE", "InvoiceItem", item.id, None, {"amount": float(amt), "type": "Consultation"}, request.client.host)

        db.commit()
        return {"message": "Consultation fee successfully charged."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/mpesa-transactions", dependencies=[Depends(RequirePermission("billing:read"))])
def get_billing_mpesa_transactions(db: Session = Depends(get_db)):
    """Returns Pay Hero (M-Pesa rail) transactions for cashiers to verify receipts.

    Route path keeps the legacy ``/mpesa-transactions`` name for frontend
    compatibility; the rail is Pay Hero. AUTH-002 hardened access to
    ``billing:read`` (Doctor / Pharmacist / Receptionist / Accountant).
    """
    from app.models.payhero import PayHeroTransaction
    transactions = (
        db.query(PayHeroTransaction)
        .order_by(PayHeroTransaction.transaction_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": txn.id,
            "invoice_id": txn.invoice_id,
            "phone_number": txn.phone_number,
            "amount": float(txn.amount) if txn.amount else None,
            "status": txn.status,
            "receipt_number": txn.receipt_number,
            "result_desc": txn.result_desc,
            "created_at": txn.transaction_date.isoformat() if txn.transaction_date else None,
        }
        for txn in transactions
    ]
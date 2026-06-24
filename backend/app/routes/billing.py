from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal, InvalidOperation

from app.config.database import get_db
from app.models.accounting import PriceListItem, JournalEntry
from app.models.billing import Invoice, InvoiceItem, Payment
from app.services.accounting import reverse_entry
from app.core.idempotency import idempotent_guard
from app.schemas.billing import PaymentRequest, InvoiceResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.services.accounting_posting import post_from_event, payment_method_to_key
from app.utils.audit import log_audit
from pydantic import BaseModel
from sqlalchemy.orm import joinedload, selectinload

class ConsultationFeeRequest(BaseModel):
    patient_id: int
    # Legacy fallback only: when the charging doctor has a saved per-doctor
    # fee, the server-side price wins — a tampered client amount can't
    # change what gets invoiced.
    amount: Optional[float] = None


class SetMyConsultationFeeRequest(BaseModel):
    amount: float


# Charged when a doctor has not configured a personal fee yet (legacy
# behaviour — this was previously hard-coded in the frontend).
DEFAULT_CONSULTATION_FEE = Decimal("1000.00")


def _doctor_fee_code(user_id: int) -> str:
    """Per-doctor consultation fees live in the master price list as ordinary
    rows keyed by this service code — no schema change, and admins can see /
    edit them in Accounting → Config → Price list alongside everything else."""
    return f"CONSULT-DR-{user_id}"


def _doctor_fee_row(db: Session, user_id: int) -> Optional[PriceListItem]:
    return (
        db.query(PriceListItem)
        .filter(
            PriceListItem.service_code == _doctor_fee_code(user_id),
            PriceListItem.is_active == True,  # noqa: E712
        )
        .first()
    )

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

        # ACCURACY: never book more than is owed. A keying slip (10000 vs
        # 1000) would otherwise silently overstate both the invoice and the
        # revenue ledger. The row lock above makes this check race-safe.
        outstanding = (invoice.total_amount or Decimal(0)) - (invoice.amount_paid or Decimal(0))
        if amt > outstanding:
            raise HTTPException(
                status_code=400,
                detail=f"Payment of {amt} exceeds the outstanding balance of {outstanding}.",
            )

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
        # Memo names the method so the transaction log reads as a cashflow
        # story ("Cash payment…", "M-Pesa payment…") without cross-referencing.
        post_from_event(
            db,
            source_key=payment_method_to_key(req.payment_method),
            source_id=payment.payment_id,
            amount=amt,
            memo=f"{req.payment_method or 'Cash'} payment against Invoice #{invoice.invoice_id}",
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

@router.get("/consultation-fee/me", dependencies=[Depends(RequirePermission("clinical:read"))])
def get_my_consultation_fee(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """The logged-in doctor's own consultation fee (falls back to the
    tenant-wide default when they haven't set one)."""
    row = _doctor_fee_row(db, current_user["user_id"])
    if row:
        return {"amount": float(row.unit_price), "is_custom": True}
    return {"amount": float(DEFAULT_CONSULTATION_FEE), "is_custom": False}


@router.put("/consultation-fee/me", dependencies=[Depends(RequirePermission("clinical:write"))])
def set_my_consultation_fee(
    req: SetMyConsultationFeeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Doctor self-service: upserts their personal fee into the price list.

    Deliberately scoped to *their own* fee (the row is keyed by the caller's
    user_id), so clinical:write is enough — no accounting permission needed.
    """
    amt = _money(req.amount)
    try:
        code = _doctor_fee_code(current_user["user_id"])
        row = db.query(PriceListItem).filter(PriceListItem.service_code == code).first()
        if row:
            before = {"unit_price": float(row.unit_price), "is_active": row.is_active}
            row.unit_price = amt
            row.is_active = True
            action = "UPDATE"
        else:
            before = None
            row = PriceListItem(
                service_code=code,
                name=f"Consultation — {current_user.get('full_name') or 'Doctor'}"[:200],
                category="Consultation",
                unit_price=amt,
            )
            db.add(row)
            action = "CREATE"
        db.flush()

        log_audit(
            db, current_user["user_id"], action, "PriceListItem", str(row.price_id),
            before, {"service_code": code, "unit_price": float(amt)},
            request.client.host if request.client else None,
        )
        db.commit()
        return {"amount": float(amt), "is_custom": True}
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
    try:
        # The charging doctor's saved fee takes precedence; the request
        # amount is only honoured for doctors with no fee on file.
        fee_row = _doctor_fee_row(db, current_user["user_id"])
        if fee_row:
            amt = Decimal(fee_row.unit_price).quantize(Decimal("0.01"))
            if amt <= 0:
                raise HTTPException(status_code=400, detail="Configured consultation fee must be greater than zero.")
        elif req.amount is not None:
            amt = _money(req.amount)
        else:
            amt = DEFAULT_CONSULTATION_FEE
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

        # Naming the doctor on the line item lets multi-doctor hospitals
        # reconcile consultation revenue per clinician from the invoice alone.
        item = InvoiceItem(
            invoice_id=invoice.invoice_id,
            description=f"Doctor Consultation Fee — {current_user.get('full_name') or 'Doctor'}"[:255],
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

@router.get("/transactions", dependencies=[Depends(RequirePermission("billing:read"))])
def get_payment_transactions(db: Session = Depends(get_db), limit: int = Query(200, ge=1, le=1000)):
    """Unified cashflow ledger for the cashier: every settled payment (cash,
    card/bank, M-Pesa) plus Pay Hero attempts that never settled (pending
    STK pushes, failures, quarantined mismatches) so M-Pesa status is never
    invisible. Each row carries a type, a receipt reference, a status, and a
    human-readable description.
    """
    from app.models.patient import Patient
    from app.models.payhero import PayHeroTransaction

    rows = (
        db.query(Payment, Invoice, Patient)
        .join(Invoice, Payment.invoice_id == Invoice.invoice_id)
        .outerjoin(Patient, Invoice.patient_id == Patient.patient_id)
        .order_by(Payment.payment_date.desc())
        .limit(limit)
        .all()
    )

    out = []
    settled_receipts = set()
    for pay, _inv, pat in rows:
        if pay.transaction_reference:
            settled_receipts.add(pay.transaction_reference)
        patient_name = f"{pat.surname}, {pat.other_names}" if pat else "Unknown"
        method = pay.payment_method or "Cash"
        out.append({
            "id": f"payment-{pay.payment_id}",
            "date": pay.payment_date.isoformat() if pay.payment_date else None,
            "type": method,
            "invoice_id": pay.invoice_id,
            "patient": patient_name,
            "phone_number": None,
            "amount": float(pay.amount),
            # Cash/card have no gateway receipt — the payment id is the
            # receipt reference the cashier can quote.
            "receipt": pay.transaction_reference or f"PAY-{pay.payment_id}",
            "status": "Completed",
            "description": f"{method} payment · Invoice #{pay.invoice_id} · {patient_name}",
        })

    unsettled = (
        db.query(PayHeroTransaction)
        .order_by(PayHeroTransaction.transaction_date.desc())
        .limit(limit)
        .all()
    )
    for t in unsettled:
        # Settled receipts already appear above as Payment rows.
        if t.receipt_number and t.receipt_number in settled_receipts:
            continue
        status = t.status or "Pending"
        out.append({
            "id": f"payhero-{t.id}",
            "date": t.transaction_date.isoformat() if t.transaction_date else None,
            "type": "M-Pesa",
            "invoice_id": t.invoice_id,
            "patient": None,
            "phone_number": t.phone_number,
            "amount": float(t.amount) if t.amount is not None else None,
            "receipt": t.receipt_number or t.external_reference or "—",
            "status": status,
            "description": t.result_desc or (
                "STK push awaiting confirmation" if status == "Pending"
                else f"M-Pesa transaction · {status}"
            ),
        })

    out.sort(key=lambda r: r["date"] or "", reverse=True)
    return out[:limit]


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


class VoidInvoiceRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/invoices/{invoice_id}/void", dependencies=[Depends(RequirePermission("billing:manage"))])
def void_invoice(
    invoice_id: int,
    payload: VoidInvoiceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Void a fully-unpaid Pending invoice and reverse its ledger posting.

    Only Pending (nothing collected) invoices are voidable — Paid / Partially
    Paid involve collected money and need a refund/credit-note flow instead."""
    invoice = db.query(Invoice).with_for_update().filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status != "Pending":
        raise HTTPException(
            status_code=400,
            detail=f"Only fully-unpaid Pending invoices can be voided; this one is '{invoice.status}'.",
        )

    # Reverse every posted GL entry for this invoice's items so A/R + revenue
    # net to zero. reverse_entry requires status='posted', so already-reversed
    # entries are skipped — keeping the void idempotent at the ledger level.
    item_ids = [it.id for it in invoice.items]
    if item_ids:
        posted = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.source_type == "billing.invoice.created",
                JournalEntry.source_id.in_(item_ids),
                JournalEntry.status == "posted",
            )
            .all()
        )
        for entry in posted:
            reverse_entry(db, entry.entry_id, current_user["user_id"], payload.reason or "Invoice voided")

    old = {"status": invoice.status}
    invoice.status = "Cancelled"
    log_audit(
        db, current_user["user_id"], "UPDATE", "Invoice", str(invoice_id),
        old, {"status": "Cancelled", "reason": payload.reason},
        request.client.host if request.client else None,
    )
    db.commit()
    return {"message": "Invoice voided.", "invoice_id": invoice_id}

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
import json

from app.config.database import get_db
from app.models.billing import Invoice, Payment
from app.models.idempotency import IdempotencyKey
from app.schemas.billing import PaymentRequest, MPesaRequest, InvoiceResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.services.payment_service import mpesa_service
from app.utils.audit import log_audit
from pydantic import BaseModel

class ConsultationFeeRequest(BaseModel):
    patient_id: int
    amount: float = 1000.0

router = APIRouter(prefix="/api/billing", tags=["Billing & Cashier"])

@router.get("/queue", response_model=List[InvoiceResponse], dependencies=[Depends(RequirePermission("billing:process"))])
def get_billing_queue(db: Session = Depends(get_db)):
    """Returns all patients with Pending invoices."""
    invoices = db.query(Invoice).filter(Invoice.status.in_(["Pending", "Partially Paid", "Pending M-Pesa"])).order_by(Invoice.billing_date.asc()).all()
    
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

@router.post("/process-payment", dependencies=[Depends(RequirePermission("billing:process"))])
def process_cash_card_payment(req: PaymentRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        idem_key = db.query(IdempotencyKey).filter(IdempotencyKey.key == req.idempotency_key).first()
        if idem_key:
            return json.loads(idem_key.response_body)

        invoice = db.query(Invoice).with_for_update().filter(Invoice.invoice_id == req.invoice_id).first()
        if not invoice or invoice.status == "Paid":
            raise HTTPException(status_code=400, detail="Invalid or already paid invoice")

        invoice.amount_paid += req.amount
        if invoice.amount_paid >= invoice.total_amount:
            invoice.status = "Paid"
        else:
            invoice.status = "Partially Paid"

        payment = Payment(invoice_id=invoice.invoice_id, amount=req.amount, payment_method=req.payment_method)
        db.add(payment)
        db.flush()

        resp_data = {"status": "Success", "invoice_status": invoice.status, "payment_id": payment.payment_id}
        db.add(IdempotencyKey(key=req.idempotency_key, response_body=json.dumps(resp_data)))
        log_audit(db, current_user["user_id"], "CREATE", "Payment", payment.payment_id, None, {"amount": req.amount, "method": req.payment_method}, request.client.host)
        
        db.commit()
        return resp_data

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/process-mpesa", dependencies=[Depends(RequirePermission("billing:process"))])
def initiate_mpesa_payment(req: MPesaRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(Invoice.invoice_id == req.invoice_id).first()
    if not invoice or invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invalid or already paid invoice")

    # Trigger STK Push
    response = mpesa_service.trigger_stk_push(
        phone_number=req.phone_number,
        amount=req.amount,
        reference=f"INV-{invoice.invoice_id}",
        description="Hospital Bill Payment"
    )

    if response.get("ResponseCode") == "0":
        invoice.status = "Pending M-Pesa"
        db.commit()
        return {"status": "STK Push Sent", "checkout_request_id": response.get("CheckoutRequestID")}
    
    
    raise HTTPException(status_code=400, detail="M-Pesa request failed")

@router.post("/consultation-fee", dependencies=[Depends(RequirePermission("clinical:write"))])
def charge_consultation_fee(req: ConsultationFeeRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Check if a pending invoice already exists for this patient, else create one
    invoice = db.query(Invoice).filter(Invoice.patient_id == req.patient_id, Invoice.status == "Pending").first()
    
    if not invoice:
        invoice = Invoice(
            patient_id=req.patient_id,
            total_amount=0,
            status="Pending",
            created_by=current_user["user_id"]
        )
        db.add(invoice)
        db.flush()
        
    invoice.total_amount += req.amount
    
    item = InvoiceItem(
        invoice_id=invoice.invoice_id,
        description="Doctor Consultation Fee",
        amount=req.amount,
        item_type="Consultation"
    )
    db.add(item)
    
    log_audit(db, current_user["user_id"], "CREATE", "InvoiceItem", item.id, None, {"amount": req.amount, "type": "Consultation"}, request.client.host)
    
    db.commit()
    return {"message": "Consultation fee successfully charged."}
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

router = APIRouter(prefix="/api/billing", tags=["Billing & Cashier"])

@router.get("/queue", response_model=List[InvoiceResponse], dependencies=[Depends(RequirePermission("billing:process"))])
def get_billing_queue(db: Session = Depends(get_db)):
    """Returns all patients with Pending invoices."""
    return db.query(Invoice).filter(Invoice.status == "Pending").order_by(Invoice.billing_date.asc()).all()

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
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.mpesa_service import initiate_stk_push
from app.models.mpesa import MpesaTransaction
from app.models.billing import Invoice
from pydantic import BaseModel
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments/mpesa", tags=["M-Pesa Payments"])

class STKPushRequest(BaseModel):
    phone_number: str
    amount: float
    invoice_id: int
    callback_url: str

import requests
from app.config.settings import settings

def get_ngrok_url():
    """Automatically fetches the active Ngrok HTTPS URL for local testing"""
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        tunnels = r.json().get("tunnels", [])
        for t in tunnels:
            if t.get("public_url", "").startswith("https"):
                return t["public_url"]
    except Exception:
        pass
    return None

@router.post("/stk-push")
def trigger_stk_push(payload: STKPushRequest, db: Session = Depends(get_db)):
    """
    Triggers an M-Pesa STK push to the provided phone number.
    Automatically resolves Ngrok URL during local sandbox testing.
    """
    # Verify invoice exists
    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Auto-resolve Ngrok callback URL
    callback_url = payload.callback_url
    if settings.MPESA_ENV.lower() == "sandbox":
        ngrok_url = get_ngrok_url()
        if ngrok_url:
            callback_url = f"{ngrok_url}/api/payments/mpesa/callback"
            logger.info(f"Auto-resolved Ngrok Callback URL: {callback_url}")
            
    return initiate_stk_push(
        db=db,
        phone_number=payload.phone_number,
        amount=payload.amount,
        invoice_id=payload.invoice_id,
        callback_url=callback_url
    )

@router.post("/callback")
async def mpesa_callback(request: Request, db: Session = Depends(get_db)):
    """
    Safaricom Daraja API Webhook Callback.
    Receives the result of the STK Push asynchronously.
    """
    try:
        payload = await request.json()
        logger.info(f"M-Pesa Callback Received: {payload}")
        
        body = payload.get("Body", {}).get("stkCallback", {})
        checkout_request_id = body.get("CheckoutRequestID")
        result_code = body.get("ResultCode")
        result_desc = body.get("ResultDesc")
        
        # Find the pending transaction
        txn = db.query(MpesaTransaction).filter(MpesaTransaction.checkout_request_id == checkout_request_id).first()
        
        if not txn:
            logger.warning(f"M-Pesa Callback received for unknown CheckoutRequestID: {checkout_request_id}")
            return {"ResultCode": 0, "ResultDesc": "Success"} # Always return 0 to Daraja to acknowledge receipt
            
        txn.result_desc = result_desc
        
        if result_code == 0:
            # Transaction Successful
            txn.status = "Success"
            
            # Extract receipt number and amount from CallbackMetadata
            metadata = body.get("CallbackMetadata", {}).get("Item", [])
            for item in metadata:
                if item.get("Name") == "MpesaReceiptNumber":
                    txn.receipt_number = item.get("Value")
                if item.get("Name") == "Amount":
                    txn.amount = item.get("Value")
                    
            # Update the associated Invoice
            if txn.invoice_id:
                invoice = db.query(Invoice).filter(Invoice.invoice_id == txn.invoice_id).first()
                if invoice:
                    invoice.status = "Paid"
                    invoice.amount_paid = txn.amount
                    invoice.payment_method = "M-Pesa"
        else:
            # Transaction Failed (e.g., cancelled by user, insufficient funds)
            txn.status = "Failed"
            
        db.commit()
        return {"ResultCode": 0, "ResultDesc": "Success"}
        
    except Exception as e:
        logger.error(f"Error processing M-Pesa Callback: {e}")
        return {"ResultCode": 1, "ResultDesc": "Error processing callback"}

@router.get("/status/{checkout_request_id}")
def check_transaction_status(checkout_request_id: str, db: Session = Depends(get_db)):
    """
    Allows the frontend to poll for the real-time status of the STK push
    """
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.checkout_request_id == checkout_request_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    return {
        "status": txn.status,
        "receipt_number": txn.receipt_number,
        "result_desc": txn.result_desc
    }

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.mpesa import MpesaConfig
from app.utils.encryption import encrypt_data
from pydantic import BaseModel
from app.core.dependencies import RequirePermission

router = APIRouter(prefix="/api/admin/mpesa", tags=["M-Pesa Admin Settings"])

class MpesaConfigSchema(BaseModel):
    paybill_number: str
    consumer_key: str
    consumer_secret: str
    passkey: str
    account_reference: str = "HMS-BILLING"
    transaction_desc: str = "Hospital Bill Payment"
    kcb_account_number: str = None

@router.get("/config")
def get_mpesa_config(db: Session = Depends(get_db), user: dict = Depends(RequirePermission("settings:read"))):
    """
    Returns the public M-Pesa configuration.
    CRITICAL: Does NOT return the decrypted Consumer Key, Secret, or Passkey.
    """
    config = db.query(MpesaConfig).first()
    if not config:
        return {"configured": False}
        
    return {
        "configured": True,
        "paybill_number": config.paybill_number,
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "kcb_account_number": config.kcb_account_number,
        "is_active": config.is_active,
    }

@router.post("/config")
def update_mpesa_config(
    payload: MpesaConfigSchema, 
    db: Session = Depends(get_db), 
    user: dict = Depends(RequirePermission("settings:write"))
):
    """
    Updates or creates the M-Pesa settings dynamically.
    Encrypts sensitive data before saving to the database.
    """
    config = db.query(MpesaConfig).first()
    if not config:
        config = MpesaConfig()
        db.add(config)
        
    config.paybill_number = payload.paybill_number
    # ENCRYPTING SECRETS
    config.consumer_key_encrypted = encrypt_data(payload.consumer_key)
    config.consumer_secret_encrypted = encrypt_data(payload.consumer_secret)
    config.passkey_encrypted = encrypt_data(payload.passkey)
    
    config.account_reference = payload.account_reference
    config.transaction_desc = payload.transaction_desc
    config.kcb_account_number = payload.kcb_account_number
    config.updated_by = user["user_id"]
    
    db.commit()
    return {"message": "M-Pesa configuration updated and securely encrypted."}

@router.get("/transactions")
def get_mpesa_transactions(db: Session = Depends(get_db), user: dict = Depends(RequirePermission("settings:read"))):
    """
    Returns all M-Pesa transactions for auditing and tracking.
    """
    from app.models.mpesa import MpesaTransaction
    transactions = db.query(MpesaTransaction).order_by(MpesaTransaction.transaction_date.desc()).limit(100).all()
    
    return [
        {
            "id": txn.id,
            "invoice_id": txn.invoice_id,
            "phone_number": txn.phone_number,
            "amount": float(txn.amount) if txn.amount else None,
            "status": txn.status,
            "receipt_number": txn.receipt_number,
            "result_desc": txn.result_desc,
            "created_at": txn.transaction_date.isoformat() if txn.transaction_date else None
        }
        for txn in transactions
    ]

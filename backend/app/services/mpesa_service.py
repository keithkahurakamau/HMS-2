import requests
import base64
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.utils.encryption import decrypt_data
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

# Replace with "https://api.safaricom.co.ke" for production
DARAJA_BASE_URL = "https://sandbox.safaricom.co.ke"

def get_mpesa_config(db: Session):
    config = db.query(MpesaConfig).first()
    if not config or not config.is_active:
        raise HTTPException(status_code=400, detail="M-Pesa is not configured or is inactive.")
    return config

def get_daraja_access_token(db: Session):
    """Generates an OAuth access token from Safaricom"""
    config = get_mpesa_config(db)
    
    consumer_key = decrypt_data(config.consumer_key_encrypted)
    consumer_secret = decrypt_data(config.consumer_secret_encrypted)
    
    api_url = f"{DARAJA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    try:
        r = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=10)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        logger.error(f"Failed to get Daraja token: {e}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with Safaricom Daraja API")

def initiate_stk_push(db: Session, phone_number: str, amount: float, invoice_id: int, callback_url: str):
    """Triggers the Safaricom STK Push to the customer's phone"""
    config = get_mpesa_config(db)
    access_token = get_daraja_access_token(db)
    
    passkey = decrypt_data(config.passkey_encrypted)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Generate Password
    password_str = config.paybill_number + passkey + timestamp
    password = base64.b64encode(password_str.encode("utf-8")).decode("utf-8")
    
    api_url = f"{DARAJA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Format Phone Number (convert 07... to 2547...)
    formatted_phone = phone_number
    if formatted_phone.startswith("0"):
        formatted_phone = "254" + formatted_phone[1:]
    elif formatted_phone.startswith("+"):
        formatted_phone = formatted_phone[1:]
        
    payload = {
        "BusinessShortCode": config.paybill_number,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": formatted_phone,
        "PartyB": config.paybill_number,
        "PhoneNumber": formatted_phone,
        "CallBackURL": callback_url,
        "AccountReference": config.account_reference,
        "TransactionDesc": config.transaction_desc
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get("ResponseCode") == "0":
            # Successfully sent prompt to phone, save pending transaction
            txn = MpesaTransaction(
                invoice_id=invoice_id,
                phone_number=formatted_phone,
                amount=amount,
                merchant_request_id=response_data.get("MerchantRequestID"),
                checkout_request_id=response_data.get("CheckoutRequestID"),
                status="Pending"
            )
            db.add(txn)
            db.commit()
            return {"message": "STK Push sent successfully", "checkout_request_id": response_data.get("CheckoutRequestID")}
        else:
            logger.error(f"STK Push Failed: {response_data}")
            raise HTTPException(status_code=400, detail=response_data.get("errorMessage", "STK Push Failed"))
            
    except Exception as e:
        logger.error(f"STK Push Request Exception: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate STK Push. Please try again.")

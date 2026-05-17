"""Per-tenant M-Pesa (Safaricom Daraja) integration.

Each tenant has its own MpesaConfig row carrying paybill/till, encrypted
Daraja credentials, environment (sandbox/production), and the C2B
register state. The helpers in this module read that row and call the
right Daraja endpoint for the configured environment.

Public surface:
  - get_mpesa_config(db) → MpesaConfig (raises 400 if missing/inactive)
  - get_daraja_access_token(db) → OAuth bearer string
  - initiate_stk_push(...)     → push an STK to the customer's phone
  - test_stk_push(...)         → admin sanity-check (KES 1 to admin phone)
  - register_c2b_urls(...)     → tell Daraja where to send direct-to-till
                                  payments (confirmation + validation URLs)
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Optional

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.utils.encryption import decrypt_data

logger = logging.getLogger(__name__)

SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE = "https://api.safaricom.co.ke"


# ─── Config + auth ──────────────────────────────────────────────────────────

def get_mpesa_config(db: Session) -> MpesaConfig:
    config = db.query(MpesaConfig).first()
    if not config or not config.is_active:
        raise HTTPException(status_code=400, detail="M-Pesa is not configured or is inactive.")
    return config


def _base_url(config: MpesaConfig) -> str:
    return PRODUCTION_BASE if (config.environment or "sandbox").lower() == "production" else SANDBOX_BASE


def get_daraja_access_token(db: Session) -> str:
    config = get_mpesa_config(db)
    consumer_key = decrypt_data(config.consumer_key_encrypted)
    consumer_secret = decrypt_data(config.consumer_secret_encrypted)
    api_url = f"{_base_url(config)}/oauth/v1/generate?grant_type=client_credentials"
    try:
        r = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=10)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        logger.error("Failed to get Daraja token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to authenticate with Safaricom Daraja API")


# ─── Helpers ────────────────────────────────────────────────────────────────

def _format_phone(phone: str) -> str:
    p = (phone or "").strip().replace(" ", "")
    if p.startswith("0"):
        return "254" + p[1:]
    if p.startswith("+"):
        return p[1:]
    return p


def _stk_password(config: MpesaConfig, timestamp: str) -> str:
    passkey = decrypt_data(config.passkey_encrypted)
    return base64.b64encode((config.paybill_number + passkey + timestamp).encode()).decode()


def _stk_transaction_type(config: MpesaConfig) -> str:
    """Daraja accepts CustomerPayBillOnline for paybills and
    CustomerBuyGoodsOnline for tills."""
    if (config.shortcode_type or "paybill").lower() == "till":
        return "CustomerBuyGoodsOnline"
    return "CustomerPayBillOnline"


# ─── STK Push (we → customer) ───────────────────────────────────────────────

def initiate_stk_push(
    db: Session,
    phone_number: str,
    amount: float,
    invoice_id: Optional[int],
    callback_url: str,
    *,
    account_reference: Optional[str] = None,
    transaction_desc: Optional[str] = None,
):
    config = get_mpesa_config(db)
    access_token = get_daraja_access_token(db)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = _stk_password(config, timestamp)

    api_url = f"{_base_url(config)}/mpesa/stkpush/v1/processrequest"
    formatted_phone = _format_phone(phone_number)
    payload = {
        "BusinessShortCode": config.paybill_number,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": _stk_transaction_type(config),
        "Amount": int(amount),
        "PartyA": formatted_phone,
        "PartyB": config.paybill_number,
        "PhoneNumber": formatted_phone,
        "CallBackURL": callback_url,
        "AccountReference": account_reference or config.account_reference,
        "TransactionDesc": transaction_desc or config.transaction_desc,
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        data = response.json()
        if response.status_code == 200 and data.get("ResponseCode") == "0":
            txn = MpesaTransaction(
                invoice_id=invoice_id,
                phone_number=formatted_phone,
                amount=amount,
                merchant_request_id=data.get("MerchantRequestID"),
                checkout_request_id=data.get("CheckoutRequestID"),
                status="Pending",
                transaction_type="STK",
            )
            db.add(txn)
            db.commit()
            return {
                "message": "STK Push sent successfully",
                "checkout_request_id": data.get("CheckoutRequestID"),
            }
        logger.error("STK Push Failed: %s", data)
        raise HTTPException(status_code=400, detail=data.get("errorMessage", "STK Push Failed"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("STK Push Request Exception")
        raise HTTPException(status_code=500, detail=f"Failed to initiate STK Push: {exc}")


def test_stk_push(db: Session, *, phone_number: str, callback_url: str) -> dict:
    """Sends a KES 1 STK push to the supplied phone using the configured
    credentials. Used by the admin UI to prove the till works end-to-end.

    Writes back to MpesaConfig.last_test_at / last_test_status /
    last_test_message so the result is visible in the UI without polling
    Daraja."""
    config = get_mpesa_config(db)
    try:
        resp = initiate_stk_push(
            db,
            phone_number=phone_number,
            amount=1.0,
            invoice_id=None,
            callback_url=callback_url,
            account_reference="TEST",
            transaction_desc="MediFleet M-Pesa test",
        )
        config.last_test_at = datetime.utcnow()
        config.last_test_status = "STK Push Sent"
        config.last_test_message = (
            f"Test KES 1 STK push dispatched to {_format_phone(phone_number)}. "
            f"Customer must approve on phone to complete the test."
        )
        db.commit()
        return resp
    except HTTPException as exc:
        config.last_test_at = datetime.utcnow()
        config.last_test_status = f"Failed ({exc.status_code})"
        config.last_test_message = str(exc.detail)[:1000]
        db.commit()
        raise
    except Exception as exc:
        config.last_test_at = datetime.utcnow()
        config.last_test_status = "Failed"
        config.last_test_message = str(exc)[:1000]
        db.commit()
        raise HTTPException(500, detail=f"Test STK push failed: {exc}")


# ─── C2B (customer → till, direct, no STK) ──────────────────────────────────

def register_c2b_urls(db: Session, *, confirmation_url: str, validation_url: str) -> dict:
    """Tell Safaricom where to send direct-to-till payment callbacks.

    Must be called once per shortcode (and again any time the URLs change).
    Both URLs must be HTTPS-reachable from the public internet — Safaricom
    rejects local/private addresses.
    """
    config = get_mpesa_config(db)
    access_token = get_daraja_access_token(db)
    shortcode = config.c2b_short_code or config.paybill_number
    api_url = f"{_base_url(config)}/mpesa/c2b/v1/registerurl"
    payload = {
        "ShortCode": shortcode,
        "ResponseType": config.c2b_response_type or "Completed",
        "ConfirmationURL": confirmation_url,
        "ValidationURL": validation_url,
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=15)
        data = r.json()
        if r.status_code == 200 and (data.get("ResponseCode") == "0"
                                     or data.get("ResponseDescription", "").lower().startswith("success")):
            config.c2b_registered_at = datetime.utcnow()
            db.commit()
            return {"status": "registered", "response": data}
        raise HTTPException(status_code=400, detail=data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Daraja RegisterURL failed")
        raise HTTPException(status_code=502, detail=f"Daraja RegisterURL failed: {exc}")

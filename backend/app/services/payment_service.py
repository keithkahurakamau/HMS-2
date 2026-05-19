"""Legacy MPesaService stub kept alive only because backend/app/routes/billing.py
imports the module-level ``mpesa_service`` symbol. The real Daraja integration
lives in app/services/mpesa_service.py — this stub is a no-op that returns a
synthetic success response for code paths the new service has not yet reached.

Audit SEC-003 / RES-003: previously this stub print()-ed the formatted phone
number and amount of every STK push to stdout, which on Render lands in the
platform log store unredacted. Now it logs at debug only and never emits the
phone number — diagnostics belong in structured logs, not stdout.
"""
import base64
import logging
from datetime import datetime

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MPesaService:
    def __init__(self):
        self.env = settings.MPESA_ENV
        self.base_url = "https://sandbox.safaricom.co.ke" if self.env == "sandbox" else "https://api.safaricom.co.ke"
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY

    def format_phone_number(self, phone: str) -> str:
        """Normalizes 07XX to 2547XX per Safaricom specs."""
        phone = phone.strip()
        if phone.startswith("0"):
            return "254" + phone[1:]
        if phone.startswith("+254"):
            return phone[1:]
        return phone

    def get_password(self, timestamp: str) -> str:
        data_to_encode = self.shortcode + self.passkey + timestamp
        return base64.b64encode(data_to_encode.encode()).decode('utf-8')

    def trigger_stk_push(self, phone_number: str, amount: float, reference: str, description: str):
        """Stub — see module docstring. Returns a synthetic Safaricom-shaped
        success envelope so the billing flow can complete in dev."""
        _ = self.format_phone_number(phone_number)  # validate shape, discard
        _ = datetime.now().strftime('%Y%m%d%H%M%S')
        logger.debug("MPesaService stub STK push: ref=%s amount=%s", reference, amount)
        return {
            "ResponseCode": "0",
            "CheckoutRequestID": "ws_CO_1234567890",
            "CustomerMessage": "Success. Request accepted for processing",
        }


mpesa_service = MPesaService()
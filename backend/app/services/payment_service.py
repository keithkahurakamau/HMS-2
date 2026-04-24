import base64
from datetime import datetime
import requests
from app.config.settings import settings

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
        """
        Triggers the STK push prompt on the patient's phone.
        NOTE: You will need to implement the actual OAuth token generation here 
        using MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET.
        """
        # Placeholder for actual API call to keep MVP running
        formatted_phone = self.format_phone_number(phone_number)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        print(f"💰 M-PESA STK PUSH TRIGGERED:")
        print(f"Phone: {formatted_phone} | Amount: KES {amount} | Ref: {reference}")
        
        # In production, return the response from Safaricom:
        # return response.json()
        return {"ResponseCode": "0", "CheckoutRequestID": "ws_CO_1234567890", "CustomerMessage": "Success. Request accepted for processing"}

mpesa_service = MPesaService()
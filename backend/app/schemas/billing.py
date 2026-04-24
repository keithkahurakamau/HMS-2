from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class PaymentRequest(BaseModel):
    idempotency_key: str
    invoice_id: int
    amount: float
    payment_method: str # "Cash" or "Card" (M-Pesa uses a different route)

class MPesaRequest(BaseModel):
    idempotency_key: str
    invoice_id: int
    phone_number: str # e.g., 0712345678 or 254712345678
    amount: float

class InvoiceItemResponse(BaseModel):
    id: int
    description: str
    amount: float
    item_type: str
    
    class Config:
        from_attributes = True

class InvoiceResponse(BaseModel):
    invoice_id: int
    patient_id: int
    total_amount: float
    amount_paid: float
    status: str
    billing_date: datetime
    items: Optional[List[InvoiceItemResponse]] = []
    
    class Config:
        from_attributes = True
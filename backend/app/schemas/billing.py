from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class PaymentRequest(BaseModel):
    idempotency_key: str
    invoice_id: int
    amount: float
    payment_method: str  # "Cash" or "Card"; M-Pesa flows via /api/payments/payhero/stk-push

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
    patient_name: Optional[str] = None
    patient_opd: Optional[str] = None
    total_amount: float
    amount_paid: float
    status: str
    billing_date: datetime
    items: Optional[List[InvoiceItemResponse]] = []
    
    class Config:
        from_attributes = True
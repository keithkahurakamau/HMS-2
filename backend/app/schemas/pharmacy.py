from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class DrugCreate(BaseModel):
    brand_name: str
    generic_name: str
    category: str
    dosage_form: str
    strength: str
    unit_price: float
    stock_quantity: int
    reorder_level: int = 10
    requires_prescription: bool = False


class DrugResponse(DrugCreate):
    drug_id: int
    last_restocked: Optional[datetime] = None

    class Config:
        from_attributes = True


class DispenseRequest(BaseModel):
    idempotency_key: str   # prevents double-charging on a retry
    batch_id: int          # specific StockBatch to deduct from (FEFO picked client-side)
    quantity: int = Field(gt=0)
    patient_id: Optional[int] = None  # None for walk-in OTC sale
    record_id: Optional[int] = None   # links to a clinical encounter when set
    notes: Optional[str] = None


class DispenseResponse(BaseModel):
    dispense_id: int
    item_id: int
    quantity_dispensed: int
    total_cost: float
    dispensed_at: datetime
    # Present when the dispense was tied to a patient (= an Invoice exists
    # for payment collection). Null for walk-in OTC sales.
    invoice_id: Optional[int] = None
    invoice_balance: Optional[float] = None  # remaining unpaid amount on the invoice

    class Config:
        from_attributes = True


# ─── Payment ────────────────────────────────────────────────────────────────

PaymentMethod = Literal["cash", "mpesa", "card"]


class DispensePaymentRequest(BaseModel):
    method: PaymentMethod
    amount: float = Field(gt=0)
    # Required when method == 'mpesa'.
    phone_number: Optional[str] = None
    # Optional human-friendly reference (receipt no., card auth code, etc.).
    transaction_reference: Optional[str] = None


class CashPaymentResponse(BaseModel):
    status: Literal["paid", "partial"]
    payment_id: int
    invoice_id: int
    amount_paid_total: float
    invoice_status: str


class MpesaInitResponse(BaseModel):
    status: Literal["stk_push_sent"]
    checkout_request_id: str
    mpesa_transaction_id: int

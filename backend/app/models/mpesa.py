from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class MpesaConfig(Base):
    """Per-tenant M-Pesa credentials. One row per tenant DB."""
    __tablename__ = "mpesa_configs"
    id = Column(Integer, primary_key=True)

    # Safaricom credentials.
    paybill_number = Column(String(20), nullable=False)
    consumer_key_encrypted = Column(String(255), nullable=False)
    consumer_secret_encrypted = Column(String(255), nullable=False)
    passkey_encrypted = Column(String(255), nullable=False)

    # 'sandbox' = Daraja test env; 'production' = live tills.
    environment = Column(String(20), nullable=False, default="sandbox")
    # 'paybill' (Lipa na M-Pesa PayBill: paybill + account #) or
    # 'till' (Buy Goods: till # only).
    shortcode_type = Column(String(20), nullable=False, default="paybill")
    # Optional separate shortcode for C2B collections. Falls back to
    # paybill_number when blank.
    c2b_short_code = Column(String(20), nullable=True)
    c2b_response_type = Column(String(20), nullable=False, default="Completed")
    c2b_registered_at = Column(DateTime(timezone=True), nullable=True)

    # Customization
    account_reference = Column(String(50), default="HMS-BILLING")
    transaction_desc = Column(String(100), default="Hospital Bill Payment")
    is_active = Column(Boolean, default=True)

    # Bank account where Safaricom settles the till proceeds. Not
    # API-controlled — configured on the Safaricom side at merchant
    # onboarding; stored here for operator reference + receipts.
    kcb_account_number = Column(String(50), nullable=True)

    # Test STK results — surfaced on the admin UI so operators can see
    # at a glance whether the configured credentials actually work.
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

class MpesaTransaction(Base):
    __tablename__ = "mpesa_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)
    # Optional link back to the pharmacy dispense that initiated the STK push.
    # Lets the callback close out the dispense + ledger entry without
    # having to query the invoice graph for context.
    dispense_id = Column(Integer, ForeignKey("dispense_logs.dispense_id"), index=True, nullable=True)

    phone_number = Column(String(20), index=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)

    # STK Push Identifiers (returned by Safaricom instantly)
    merchant_request_id = Column(String(100), index=True, nullable=True)
    checkout_request_id = Column(String(100), index=True, nullable=True)

    # Safaricom Callback Data (populated via Webhook)
    receipt_number = Column(String(50), unique=True, index=True, nullable=True) # e.g. QKT123456
    status = Column(String(50), default="Pending", index=True) # Pending, Success, Failed, Timeout
    result_desc = Column(String(255), nullable=True) # Safaricom's explanation (e.g., "The balance is insufficient")

    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 'STK' = customer prompted via STK push (we initiated);
    # 'C2B' = direct-to-till payment (customer initiated; we received via webhook).
    transaction_type = Column(String(10), nullable=False, default="STK", index=True)
    # The 'account number' the customer typed at the till (paybill flow).
    # NULL for tills (Buy Goods) where there's no account-ref field.
    bill_ref_number = Column(String(80), nullable=True, index=True)
    # How a C2B payment was matched to an invoice:
    # 'invoice_id' | 'opd_number' | 'phone' | 'manual' | 'unmatched'.
    match_basis = Column(String(20), nullable=True, index=True)

    invoice = relationship("Invoice", backref="mpesa_transactions")

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class MpesaConfig(Base):
    __tablename__ = "mpesa_configs"
    id = Column(Integer, primary_key=True)
    
    # Safaricom Credentials (Singleton per Tenant DB)
    paybill_number = Column(String(20), nullable=False)
    consumer_key_encrypted = Column(String(255), nullable=False)
    consumer_secret_encrypted = Column(String(255), nullable=False)
    passkey_encrypted = Column(String(255), nullable=False)
    
    # Customization
    account_reference = Column(String(50), default="HMS-BILLING")
    transaction_desc = Column(String(100), default="Hospital Bill Payment")
    is_active = Column(Boolean, default=True)
    
    # Future-proofing: KCB Bank Integration (Reconciliation)
    kcb_account_number = Column(String(50), nullable=True)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

class MpesaTransaction(Base):
    __tablename__ = "mpesa_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)
    
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
    
    invoice = relationship("Invoice", backref="mpesa_transactions")

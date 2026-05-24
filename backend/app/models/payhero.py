"""Per-tenant Pay Hero configuration + transaction ledger.

Replaces the legacy ``app/models/mpesa.py`` Daraja schema. Each tenant
configures the Safaricom Paybill / Buy-Goods till they already own plus
the bank account where Pay Hero settles the proceeds — Pay Hero acts as
the aggregator so we don't speak Daraja directly.

Tables are named ``payhero_configs`` and ``payhero_transactions`` (an
alembic migration renames the prior ``mpesa_configs`` / ``mpesa_transactions``
tables in place — see versions/aa2b7c3d8e91_payhero_full_swap.py).
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class PayHeroConfig(Base):
    """Per-tenant Pay Hero settings. One row per tenant DB."""

    __tablename__ = "payhero_configs"
    id = Column(Integer, primary_key=True)

    # The Safaricom shortcode the customer types into M-Pesa. This is the
    # tenant's existing PayBill or Buy-Goods till — they don't create it
    # via this UI; they enter the one they already have.
    shortcode = Column(String(20), nullable=False)
    # 'paybill' (PayBill + account #) or 'till' (Buy-Goods, no account #).
    shortcode_type = Column(String(20), nullable=False, default="paybill")

    # Pay Hero binds each shortcode to an internal channel; the operator
    # pastes the channel id from the Pay Hero dashboard after onboarding.
    payhero_channel_id = Column(String(40), nullable=True)

    # Optional per-tenant API creds (override the platform default in
    # settings.PAYHERO_USERNAME / PAYHERO_PASSWORD). Encrypted at rest with
    # the same Fernet key used for everything else in app.utils.encryption.
    payhero_username_encrypted = Column(String(255), nullable=True)
    payhero_password_encrypted = Column(String(255), nullable=True)

    # Settlement bank — Pay Hero deposits the till proceeds here on the
    # schedule the tenant selected at onboarding. Stored for receipts and
    # operator reference; Pay Hero is the system of record for the schedule.
    settlement_bank_code = Column(String(20), nullable=False)
    settlement_bank_name = Column(String(80), nullable=False)
    settlement_account_number = Column(String(40), nullable=False)
    settlement_account_name = Column(String(120), nullable=True)

    # Customisation — surfaced on the customer's STK prompt + on receipts.
    account_reference = Column(String(50), default="HMS-BILLING")
    transaction_desc = Column(String(100), default="Hospital Bill Payment")
    is_active = Column(Boolean, default=True)

    # Test-push status — surfaced on the admin UI so operators can see at a
    # glance whether the configured shortcode + Pay Hero credentials work.
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)


class PayHeroTransaction(Base):
    """Inbound + outbound Pay Hero transaction log.

    M-Pesa is still the underlying payment rail the customer uses; we keep
    the M-Pesa receipt number (``receipt_number``) as the canonical anchor
    because that's what the customer's SMS shows. Pay Hero's own reference
    (``payhero_reference``) lets us call back into the aggregator API for
    status lookups; ``external_reference`` is our idempotency anchor that
    we minted before initiating the push.
    """

    __tablename__ = "payhero_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(
        Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True
    )
    dispense_id = Column(
        Integer, ForeignKey("dispense_logs.dispense_id"), index=True, nullable=True
    )

    phone_number = Column(String(20), index=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)

    # Pay Hero references
    payhero_reference = Column(String(100), index=True, nullable=True)
    external_reference = Column(String(100), index=True, nullable=True)

    # Safaricom-side data populated via Pay Hero's webhook
    receipt_number = Column(String(50), unique=True, index=True, nullable=True)
    status = Column(String(50), default="Pending", index=True)
    result_desc = Column(String(255), nullable=True)

    transaction_date = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # 'STK' = we pushed an STK prompt; 'C2B' = customer paid the till directly.
    transaction_type = Column(String(10), nullable=False, default="STK", index=True)
    # PayBill account ref the customer typed (NULL for tills).
    bill_ref_number = Column(String(80), nullable=True, index=True)
    # How a C2B/inbound was matched to an invoice:
    # 'external_reference' | 'invoice_id' | 'opd_number' | 'phone' | 'manual' | 'unmatched'.
    match_basis = Column(String(20), nullable=True, index=True)

    invoice = relationship("Invoice", backref="payhero_transactions")

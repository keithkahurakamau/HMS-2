"""Per-tenant Daraja configuration, transaction ledger and refund register.

Replaces app/models/payhero.py. Table names go back to provider-neutral
mpesa_* because M-Pesa is the rail no matter who fronts it, and the next
provider change should not rename tables a third time.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class MpesaConfig(Base):
    """One row per tenant. Every secret column is Fernet-encrypted."""

    __tablename__ = "mpesa_configs"
    id = Column(Integer, primary_key=True)

    # The hospital's own PayBill or Buy Goods till. They already own it; this
    # UI records it, it does not create it.
    shortcode = Column(String(20), nullable=False)
    shortcode_type = Column(String(20), nullable=False, default="paybill")

    # 'sandbox' or 'production', per tenant: hospitals complete Safaricom
    # Go-Live on their own schedule, so a hospital sitting in sandbox while
    # its Go-Live is pending is a normal state, not a misconfiguration.
    environment = Column(String(20), nullable=False, default="sandbox")

    consumer_key_encrypted = Column(String(255), nullable=True)
    consumer_secret_encrypted = Column(String(255), nullable=True)
    passkey_encrypted = Column(String(255), nullable=True)

    # B2C only. initiator_password is stored (encrypted) rather than a
    # pre-generated SecurityCredential so a Safaricom certificate rotation is
    # a redeploy instead of a support ticket to every hospital.
    initiator_name = Column(String(80), nullable=True)
    initiator_password_encrypted = Column(String(255), nullable=True)

    # Daraja does not sign callbacks, so this unguessable token in the callback
    # path is one of the three things standing between us and a forged payment.
    # Rotatable, because a token in a URL leaks through logs and proxies in a
    # way a header secret does not.
    #
    # Stored as two columns because neither a plaintext column nor a single
    # encrypted column can serve both directions this token is used in:
    #   - callback_token_encrypted: Fernet ciphertext of the token. Reversible,
    #     so an outbound STK push can decrypt it back to build its CallBackURL.
    #   - callback_token_lookup: a deterministic HMAC-SHA256 hex digest of the
    #     token. Fernet is non-deterministic (the same token encrypts to
    #     different ciphertext each time), so the encrypted column cannot be
    #     looked up by equality; this column is what an inbound callback is
    #     resolved to a tenant by.
    # See app/services/daraja/tokens.py, which is the only place that should
    # write these two columns: it keeps them in sync so neither is ever set
    # without the other.
    callback_token_encrypted = Column(String(255), nullable=True)
    callback_token_lookup = Column(String(64), unique=True, index=True, nullable=True)
    callback_token_rotated_at = Column(DateTime(timezone=True), nullable=True)

    # Refund controls. Caps are enforced server-side, never in the UI alone.
    refunds_enabled = Column(Boolean, nullable=False, default=False)
    refund_max_amount = Column(Numeric(12, 2), nullable=False, default=10000)
    refund_daily_cap = Column(Numeric(12, 2), nullable=False, default=50000)
    refund_dual_approval_above = Column(Numeric(12, 2), nullable=False, default=5000)

    account_reference = Column(String(50), default="HMS-BILLING")
    transaction_desc = Column(String(100), default="Hospital Bill Payment")
    is_active = Column(Boolean, default=True)

    c2b_urls_registered_at = Column(DateTime(timezone=True), nullable=True)
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)


class MpesaTransaction(Base):
    """Inbound M-Pesa transaction log: STK pushes and direct-to-till payments."""

    __tablename__ = "mpesa_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)
    dispense_id = Column(Integer, ForeignKey("dispense_logs.dispense_id"), index=True, nullable=True)

    phone_number = Column(String(20), index=True, nullable=False)
    # The amount WE requested. The settlement cross-check compares the
    # callback's claimed amount against this and refuses to settle a mismatch.
    amount = Column(Numeric(12, 2), nullable=False)

    checkout_request_id = Column(String(100), index=True, nullable=True)
    merchant_request_id = Column(String(100), index=True, nullable=True)
    external_reference = Column(String(100), index=True, nullable=True)

    receipt_number = Column(String(50), unique=True, index=True, nullable=True)
    status = Column(String(50), default="Pending", index=True)
    result_desc = Column(String(255), nullable=True)

    # Proof the receipt was confirmed with Safaricom rather than merely
    # asserted by an unsigned callback. NULL means unverified: a C2B receipt
    # in that state is shown to a human and never posted to the ledger.
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_source = Column(String(30), nullable=True)  # 'stk_query' | 'transaction_status'

    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    transaction_type = Column(String(10), nullable=False, default="STK", index=True)
    bill_ref_number = Column(String(80), nullable=True, index=True)
    match_basis = Column(String(20), nullable=True, index=True)

    invoice = relationship("Invoice", backref="mpesa_transactions")

    __table_args__ = (
        Index("ix_mpesa_txn_status_date", "status", "transaction_date"),
    )


class MpesaRefund(Base):
    """B2C refund register. The only path by which money leaves a hospital."""

    __tablename__ = "mpesa_refunds"
    id = Column(Integer, primary_key=True)

    # Every refund points at the inbound receipt it reverses. The refundable
    # amount is that receipt minus refunds already completed or in flight,
    # computed under a row lock at approval time.
    source_transaction_id = Column(
        Integer, ForeignKey("mpesa_transactions.id"), index=True, nullable=False
    )
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)

    phone_number = Column(String(20), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(String(255), nullable=False)

    # Requested -> Approved -> Processing -> Completed | Failed | Reversed
    status = Column(String(20), nullable=False, default="Requested", index=True)

    # Minted once at creation and reused on every retry, so Safaricom
    # recognises a retried request as the same instruction rather than a
    # second one. This is the primary double-refund defence.
    originator_conversation_id = Column(String(64), unique=True, nullable=False)
    conversation_id = Column(String(64), index=True, nullable=True)
    transaction_receipt = Column(String(50), unique=True, index=True, nullable=True)
    result_desc = Column(String(255), nullable=True)

    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    source_transaction = relationship("MpesaTransaction")

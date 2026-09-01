"""Per-tenant Daraja configuration, transaction ledger and refund register.

Replaces app/models/payhero.py. Table names go back to provider-neutral
mpesa_* because M-Pesa is the rail no matter who fronts it, and the next
provider change should not rename tables a third time.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, text,
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
    # app/services/daraja/tokens.py is the intended writer for these two
    # columns: it keeps them in sync so neither is ever set without the
    # other. That is a convention, not an enforcement mechanism, so a
    # database CHECK backs it (see __table_args__ below): a direct attribute
    # write, a raw SQL UPDATE, or a hand-applied data fix cannot leave the
    # pair half-set, even if it skips this module entirely.
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

    # NULL means the hospital-wide default. A department with its own row
    # overrides the default; a department without one falls back to it.
    # See config_for() in app/services/daraja/stk.py for the resolution
    # order and why an inactive department row also falls back rather
    # than failing.
    department_id = Column(
        Integer,
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    c2b_urls_registered_at = Column(DateTime(timezone=True), nullable=True)
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        # Both columns NULL (no token minted yet) or both NOT NULL (a
        # complete pair) are the only valid states. Enforced in the
        # database, not just in app/services/daraja/tokens.py, because a
        # half-written pair fails silently either way it happens: a
        # lookup with no recoverable token cannot build an outbound
        # CallBackURL, and a token with no lookup hash cannot resolve its
        # own inbound callbacks.
        CheckConstraint(
            "(callback_token_encrypted IS NULL) = (callback_token_lookup IS NULL)",
            name="ck_mpesa_configs_callback_token_pair",
        ),
        # Two partial unique indexes, not one: Postgres treats NULL as
        # distinct in a plain unique index, so a single index on
        # department_id would happily allow two default (NULL) rows.
        # Enforced in Postgres via the alembic revision that introduced
        # this column; declared here for create_all parity on fresh
        # bootstraps.
        Index(
            "uq_mpesa_configs_department", "department_id",
            unique=True, postgresql_where=text("department_id IS NOT NULL"),
        ),
        Index(
            "uq_mpesa_configs_default", text("(department_id IS NULL)"),
            unique=True, postgresql_where=text("department_id IS NULL"),
        ),
    )


class MpesaTransaction(Base):
    """Inbound M-Pesa transaction log: STK pushes and direct-to-till payments."""

    __tablename__ = "mpesa_transactions"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id"), index=True, nullable=True)
    dispense_id = Column(Integer, ForeignKey("dispense_logs.dispense_id"), index=True, nullable=True)

    # Which till took the money. Without this a refund cannot know which
    # till to pay back from, and reconciliation cannot tell two tills apart.
    mpesa_config_id = Column(Integer, ForeignKey("mpesa_configs.id"), index=True, nullable=True)

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

    # C2B verification is asynchronous: a Transaction Status query is fired
    # for a receipt, and the real verdict arrives later on a separate result
    # callback identified by conversation_id, not by receipt or invoice
    # (the receipt is exactly what that callback is trying to confirm).
    # Neither is unique here: unlike MpesaRefund's originator_conversation_id
    # (which IS a retry-idempotency key), a status query is fire-and-forget
    # from this table's point of view.
    conversation_id = Column(String(64), index=True, nullable=True)
    originator_conversation_id = Column(String(64), nullable=True)

    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    transaction_type = Column(String(10), nullable=False, default="STK", index=True)
    bill_ref_number = Column(String(80), nullable=True, index=True)
    match_basis = Column(String(20), nullable=True, index=True)

    invoice = relationship("Invoice", backref="mpesa_transactions")

    __table_args__ = (
        Index("ix_mpesa_txn_status_date", "status", "transaction_date"),
        # At most one Pending push per invoice, and per dispense, across
        # every gunicorn worker and every terminal. This is the guard that
        # stops two cashiers on two machines both sending an STK prompt for
        # the same invoice: app/services/daraja/stk.py inserts and catches
        # the conflict rather than checking then inserting. Enforced in
        # Postgres via the alembic revision that introduced this; declared
        # here for create_all parity on fresh bootstraps.
        Index(
            "uq_mpesa_txn_one_pending_per_invoice", "invoice_id",
            unique=True,
            postgresql_where=text("status = 'Pending' AND invoice_id IS NOT NULL"),
        ),
        Index(
            "uq_mpesa_txn_one_pending_per_dispense", "dispense_id",
            unique=True,
            postgresql_where=text("status = 'Pending' AND dispense_id IS NOT NULL"),
        ),
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

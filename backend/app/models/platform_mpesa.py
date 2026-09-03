"""Platform-level Daraja: the operator's OWN subscription billing rail.

Lives in the MASTER database only, never a tenant database. The superadmin
pushes a subscription STK charge to a tenant's billing contact MSISDN
directly against Safaricom (no aggregator), the funds land on MediFleet's
own shortcode, and Safaricom settles them on MediFleet's own schedule. This
is the mirror of ``platform_payhero`` under the Daraja migration, and it is
deliberately absent from ``backend/scripts/migrate_all_tenants.py``'s model
import block for the same reason ``platform_payhero`` is: that import feeds
an unfiltered ``Base.metadata.create_all()`` run against every tenant
engine, so registering a master-only model there would create the
operator's own billing tables inside every hospital database. This schema
instead arrives through ``MASTER_DB_PATCHES`` in that script.

Separation of concerns:
  * ``mpesa_configs``          (tenant DB): hospital shortcode + credentials
  * ``platform_mpesa_configs`` (master DB): MediFleet's own shortcode + credentials

MediFleet holds no Daraja credentials of its own yet: Safaricom Go-Live for
the MediFleet shortcode has not been completed. An unconfigured platform
config (environment="sandbox", every credential column NULL) is therefore a
normal, expected state, reported as "not configured", not an error.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, text,
)
from sqlalchemy.sql import func

from app.config.database import Base


class PlatformMpesaConfig(Base):
    """Singleton row holding the platform's own Daraja credentials.

    Column-for-column with ``app.models.mpesa.MpesaConfig`` minus the
    fields that only make sense for a hospital's own operational rail:
    C2B till registration (the platform never takes walk-in patient
    payments) and the refund controls (B2C refunds reverse a hospital's
    patient receipt, not a subscription charge).
    """

    __tablename__ = "platform_mpesa_configs"
    id = Column(Integer, primary_key=True)

    # The MediFleet-owned PayBill/Buy Goods till that a tenant's STK prompt
    # displays. Same shape as the tenant config so the form UI can be reused.
    shortcode = Column(String(20), nullable=False, default="")
    shortcode_type = Column(String(20), nullable=False, default="paybill")

    # Defaults to sandbox with no credentials: MediFleet has not completed
    # Safaricom Go-Live for its own shortcode yet. Not an error state.
    environment = Column(String(20), nullable=False, default="sandbox")

    consumer_key_encrypted = Column(String(255), nullable=True)
    consumer_secret_encrypted = Column(String(255), nullable=True)
    passkey_encrypted = Column(String(255), nullable=True)

    # B2C only, kept for shape parity with the tenant config even though the
    # platform rail has no refund register today.
    initiator_name = Column(String(80), nullable=True)
    initiator_password_encrypted = Column(String(255), nullable=True)

    # Same two-column pattern as MpesaConfig, and for the same reason:
    # Daraja does not sign callbacks, so this unguessable token in the
    # callback path is one of the things standing between the platform and
    # a forged subscription payment. callback_token_encrypted is reversible
    # (Fernet) so an outbound STK push can rebuild its CallBackURL;
    # callback_token_lookup is a deterministic HMAC digest so an inbound
    # callback can be resolved by an indexed equality lookup, which Fernet's
    # non-deterministic ciphertext cannot support.
    # app/services/daraja/tokens.py is the intended writer of both columns
    # for the tenant config; the platform config is expected to reuse the
    # same helpers, keeping the pair in sync. The CHECK constraint below
    # backs that at the database level regardless of write path.
    callback_token_encrypted = Column(String(255), nullable=True)
    callback_token_lookup = Column(String(64), unique=True, index=True, nullable=True)
    callback_token_rotated_at = Column(DateTime(timezone=True), nullable=True)

    account_reference = Column(String(50), default="MEDIFLEET")
    transaction_desc = Column(String(100), default="MediFleet Subscription")
    is_active = Column(Boolean, default=True)

    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(callback_token_encrypted IS NULL) = (callback_token_lookup IS NULL)",
            name="ck_platform_mpesa_configs_callback_token_pair",
        ),
    )


class PlatformMpesaTransaction(Base):
    """Every platform-level STK push and its lifecycle outcome.

    ``subscription_invoice_id`` is the whole point of this table: it is
    what lets a subscription STK payment land as an ``InvoicePayment`` row
    against a real invoice in the receivables ledger
    (``app.models.subscription_billing``), instead of sitting here as an
    untracked receipt that nothing ages or reconciles against what the
    hospital actually owes. It is nullable because a transaction can be
    initiated (or can arrive as an unsolicited callback) before it has been
    matched to an invoice.
    """

    __tablename__ = "platform_mpesa_transactions"
    id = Column(Integer, primary_key=True)

    # Which tenant we charged.
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), index=True, nullable=False)

    # The receivables-ledger invoice this payment settles, once matched.
    subscription_invoice_id = Column(
        Integer, ForeignKey("subscription_invoices.id"), index=True, nullable=True
    )

    phone_number = Column(String(20), index=True, nullable=False)
    # The amount WE requested. Settlement compares the callback's claimed
    # amount against this and refuses to settle a mismatch.
    amount = Column(Numeric(12, 2), nullable=False)

    checkout_request_id = Column(String(100), index=True, nullable=True)
    merchant_request_id = Column(String(100), index=True, nullable=True)
    external_reference = Column(String(100), index=True, nullable=False, unique=True)

    receipt_number = Column(String(50), unique=True, index=True, nullable=True)
    status = Column(String(50), default="Pending", index=True)
    result_desc = Column(String(255), nullable=True)

    # Free-text label the superadmin set on the charge, e.g. "May 2026, Premium".
    period_label = Column(String(120), nullable=True)

    initiated_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)
    initiated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # CRITICAL fix, round 1 review: at most one Pending platform charge
        # per subscription invoice, across every worker. Without this, a
        # superadmin double-click (or any other path that ends up pushing
        # twice for one invoice) sends two real STK prompts; two genuine
        # approvals produce two different Safaricom receipts, so the
        # receipt-keyed replay check in
        # app/services/daraja/platform.py's apply_platform_stk_callback
        # never catches either one, and both would reach settlement.
        # app/services/daraja/platform_stk.py's _reserve_pending inserts
        # and catches the conflict rather than checking then inserting,
        # exactly the discipline app/models/mpesa.py's
        # uq_mpesa_txn_one_pending_per_invoice already uses for the tenant
        # rail; declared here for create_all parity, applied to the real
        # master DB via MASTER_DB_PATCHES in scripts/migrate_all_tenants.py.
        # A charge with no subscription_invoice_id (a bare connectivity
        # test) is outside this guard, matching the WHERE clause.
        Index(
            "uq_platform_mpesa_txn_one_pending_per_invoice", "subscription_invoice_id",
            unique=True,
            postgresql_where=text("status = 'Pending' AND subscription_invoice_id IS NOT NULL"),
        ),
    )

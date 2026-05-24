"""Platform-level Pay Hero — singleton config + STK-push transaction log.

Lives in the MASTER database (not per-tenant). The platform owns one Pay Hero
account + one settlement bank, used by the superadmin to push subscription
charges to each tenant's billing contact MSISDN. The tenant-level
``app/models/payhero.py`` schema is unchanged and continues to handle the
hospital → patient payment rail.

Separation of concerns:
  * ``payhero_configs``           (tenant DB) — hospital till + hospital bank
  * ``platform_payhero_configs``  (master DB) — MediFleet till + MediFleet bank
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
from sqlalchemy.sql import func

from app.config.database import Base


class PlatformPayHeroConfig(Base):
    """Singleton row holding the platform's Pay Hero credentials + bank."""

    __tablename__ = "platform_payhero_configs"
    id = Column(Integer, primary_key=True)

    # The MediFleet-owned PayBill / Buy-Goods till that customers' STK prompts
    # display. Same shape as the tenant config so the form UI can be reused.
    shortcode = Column(String(20), nullable=False, default="")
    shortcode_type = Column(String(20), nullable=False, default="paybill")
    payhero_channel_id = Column(String(40), nullable=True)

    # Optional override of the platform default in settings.PAYHERO_USERNAME /
    # PAYHERO_PASSWORD. Encrypted at rest with the same Fernet key as the
    # tenant config.
    payhero_username_encrypted = Column(String(255), nullable=True)
    payhero_password_encrypted = Column(String(255), nullable=True)

    # MediFleet's settlement bank — Pay Hero deposits subscription proceeds
    # here on the schedule agreed during onboarding.
    settlement_bank_code = Column(String(20), nullable=False, default="")
    settlement_bank_name = Column(String(80), nullable=False, default="")
    settlement_account_number = Column(String(40), nullable=False, default="")
    settlement_account_name = Column(String(120), nullable=True)

    # STK customisation surfaced on the tenant's phone prompt.
    account_reference = Column(String(50), default="MEDIFLEET")
    transaction_desc = Column(String(100), default="MediFleet Subscription")
    is_active = Column(Boolean, default=True)

    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(40), nullable=True)
    last_test_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)


class PlatformPayHeroTransaction(Base):
    """Every platform-level STK push and its lifecycle outcome.

    Anchored on ``external_reference`` minted at initiate time as
    ``PLAT-<tenant_id>-<nonce>``. The webhook router uses that prefix to
    decide whether a callback belongs to the master DB (this table) or a
    tenant DB (the per-hospital ``payhero_transactions`` table).
    """

    __tablename__ = "platform_payhero_transactions"
    id = Column(Integer, primary_key=True)

    # Which tenant we charged.
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), index=True, nullable=False)

    phone_number = Column(String(20), index=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)

    # Pay Hero references.
    payhero_reference = Column(String(100), index=True, nullable=True)
    external_reference = Column(String(100), index=True, nullable=False, unique=True)

    # M-Pesa-side data populated by the Pay Hero webhook.
    receipt_number = Column(String(50), unique=True, index=True, nullable=True)
    status = Column(String(50), default="Pending", index=True)
    result_desc = Column(String(255), nullable=True)

    # Free-text label the superadmin set on the charge, e.g. "May 2026 — Premium".
    period_label = Column(String(120), nullable=True)

    initiated_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)
    initiated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)

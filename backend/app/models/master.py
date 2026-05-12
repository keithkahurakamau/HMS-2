from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.config.database import Base


class Tenant(Base):
    """Central registry of all hospital instances on the platform."""
    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False)
    db_name = Column(String(100), unique=True, nullable=False)
    theme_color = Column(String(50), default="blue")
    is_premium = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Flexible per-tenant configuration. Both columns hold JSON-encoded strings
    # so we can add new flags without further migrations. The Tenants Manager
    # UI surfaces them as toggles + numeric inputs.
    #   feature_flags  → {"radiology": true, "telemedicine": false, ...}
    #   plan_limits    → {"max_users": 50, "max_patients": 10000, "storage_gb": 100}
    feature_flags = Column(Text, nullable=True)
    plan_limits = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SuperAdmin(Base):
    """Platform-level superadmin who manages all tenants. Lives in master DB only."""
    __tablename__ = "superadmins"

    admin_id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

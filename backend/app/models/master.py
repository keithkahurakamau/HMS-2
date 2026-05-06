from sqlalchemy import Column, Integer, String, Boolean, DateTime
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

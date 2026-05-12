"""Per-tenant hospital settings.

A flat key/value store keyed by ``category`` + ``key``. Each row carries its
own ``data_type`` (``string``, ``number``, ``boolean``, ``json``) and a JSON
``value`` so the frontend can render the right input control and parse the
payload uniformly. Keeping it flat avoids the schema-creep of a typed table
per concern (branding, billing, lab, …) while still letting the API expose
grouped views.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from app.config.database import Base


class HospitalSetting(Base):
    __tablename__ = "hospital_settings"
    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_hospital_settings_category_key"),
    )

    setting_id = Column(Integer, primary_key=True)
    category = Column(String(60), nullable=False, index=True)
    key = Column(String(120), nullable=False, index=True)
    label = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    data_type = Column(String(20), nullable=False, server_default="string")  # string|number|boolean|json|secret
    value = Column(Text, nullable=True)
    is_sensitive = Column(Boolean, nullable=False, server_default="false")   # don't surface in plaintext if true
    sort_order = Column(Integer, nullable=False, server_default="0")
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

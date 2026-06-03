from sqlalchemy.orm import Session
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from app.models.audit import AuditLog

def log_audit(db: Session, user_id: int, action: str, entity_type: str, entity_id: str, old_value: dict = None, new_value: dict = None, ip_address: str = None):
    """Utility to log all database write operations.

    old_value/new_value land in JSONB columns, so they must contain only
    JSON-serializable primitives. Callers routinely pass raw ORM/model values —
    e.g. a patient's ``date_of_birth`` is a ``datetime.date``, money is a
    ``Decimal`` — which the JSONB serializer can't encode and which would
    otherwise raise mid-commit and 500 the whole request. Run both payloads
    through ``jsonable_encoder`` (date/datetime -> ISO string, Decimal -> float,
    etc.) so audit logging can never be the thing that breaks a write.
    """
    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_value=jsonable_encoder(old_value) if old_value is not None else None,
        new_value=jsonable_encoder(new_value) if new_value is not None else None,
        ip_address=ip_address
    )
    db.add(audit_entry)
    # We do NOT commit here. The calling route will commit the transaction and the audit log together.
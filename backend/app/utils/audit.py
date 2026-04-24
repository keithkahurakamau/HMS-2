from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from fastapi import Request

def log_audit(db: Session, user_id: int, action: str, entity_type: str, entity_id: str, old_value: dict = None, new_value: dict = None, ip_address: str = None):
    """Utility to log all database write operations."""
    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address
    )
    db.add(audit_entry)
    # We do NOT commit here. The calling route will commit the transaction and the audit log together.
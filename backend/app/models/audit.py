from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.config.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    log_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), index=True, nullable=True)
    
    action = Column(String(20), index=True, nullable=False) # CREATE/UPDATE/DELETE
    entity_type = Column(String(50), index=True, nullable=False) 
    entity_id = Column(String(50), index=True, nullable=False)
    
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
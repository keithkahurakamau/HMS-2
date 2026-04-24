from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.config.database import Base

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    
    # This line prevents the "already defined" error
    __table_args__ = {'extend_existing': True}

    key = Column(String(255), primary_key=True)
    response_body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
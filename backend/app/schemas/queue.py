from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class QueueBase(BaseModel):
    patient_id: int
    department: str
    acuity_level: int = 3 # 1=Emergency, 2=Urgent, 3=Standard
    notes: Optional[str] = None

class QueueCreate(QueueBase):
    pass

class QueueResponse(QueueBase):
    queue_id: int
    status: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class QueueEndOfDay(BaseModel):
    # Optional department filter — omit to clear the whole active queue. When
    # set, only that department's waiting patients are checked out (e.g. the
    # doctor closing the Consultation clinic for the day).
    department: Optional[str] = None

class QueueCheckoutResult(BaseModel):
    checked_out: int
    department: Optional[str] = None
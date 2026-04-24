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
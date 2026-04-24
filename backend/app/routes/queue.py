from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.models.clinical import PatientQueue
from app.schemas.queue import QueueCreate, QueueResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/queue", tags=["Triage Queue"])

@router.post("/", response_model=QueueResponse, dependencies=[Depends(RequirePermission("patients:write"))])
def add_to_queue(queue_in: QueueCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_queue = PatientQueue(**queue_in.model_dump())
    db.add(new_queue)
    db.flush()

    log_audit(db, current_user["user_id"], "CREATE", "Queue", new_queue.queue_id, None, queue_in.model_dump(), request.client.host)
    db.commit()
    db.refresh(new_queue)
    return new_queue

@router.get("/", response_model=List[QueueResponse])
def get_active_queue(department: str = None, db: Session = Depends(get_db)):
    query = db.query(PatientQueue).filter(PatientQueue.status != "Completed")
    if department:
        query = query.filter(PatientQueue.department == department)
    return query.order_by(PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc()).all()
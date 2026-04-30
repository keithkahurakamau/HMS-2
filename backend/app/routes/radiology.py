from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.models.radiology import RadiologyRequest, RadiologyResult
from app.models.patient import Patient
from app.schemas.radiology import (
    RadiologyRequestCreate, RadiologyRequestResponse, RadiologyRequestUpdate,
    RadiologyResultCreate, RadiologyResultResponse
)
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/radiology", tags=["Radiology"])

@router.post("/", response_model=RadiologyRequestResponse, dependencies=[Depends(RequirePermission("clinical:write"))])
def create_radiology_request(req_in: RadiologyRequestCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Verify patient exists
    patient = db.query(Patient).filter(Patient.patient_id == req_in.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    new_request = RadiologyRequest(
        patient_id=req_in.patient_id,
        exam_type=req_in.exam_type,
        clinical_notes=req_in.clinical_notes,
        requested_by=current_user["user_id"],
        status="Pending"
    )
    db.add(new_request)
    db.flush()
    
    # Audit log
    log_audit(db, current_user["user_id"], "CREATE", "RadiologyRequest", new_request.request_id, None, req_in.model_dump(), request.client.host)

    db.commit()
    db.refresh(new_request)
    return new_request

@router.get("/", response_model=List[RadiologyRequestResponse], dependencies=[Depends(RequirePermission("clinical:read"))])
def get_radiology_requests(status: str = None, patient_id: int = None, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(RadiologyRequest)
    if status:
        query = query.filter(RadiologyRequest.status == status)
    if patient_id:
        query = query.filter(RadiologyRequest.patient_id == patient_id)
        
    # Order by newest first
    return query.order_by(RadiologyRequest.created_at.desc()).offset(skip).limit(limit).all()

@router.get("/{request_id}", response_model=RadiologyRequestResponse, dependencies=[Depends(RequirePermission("clinical:read"))])
def get_radiology_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found")
    return req

@router.put("/{request_id}/status", response_model=RadiologyRequestResponse, dependencies=[Depends(RequirePermission("clinical:write"))])
def update_radiology_status(request_id: int, status_update: RadiologyRequestUpdate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found")
        
    old_status = req.status
    req.status = status_update.status
    
    # Audit log
    log_audit(db, current_user["user_id"], "UPDATE", "RadiologyRequest", req.request_id, {"status": old_status}, {"status": req.status}, request.client.host)
    
    db.commit()
    db.refresh(req)
    return req

@router.post("/{request_id}/result", response_model=RadiologyResultResponse, dependencies=[Depends(RequirePermission("clinical:write"))])
def add_radiology_result(request_id: int, result_in: RadiologyResultCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found")
    
    if req.result:
        raise HTTPException(status_code=400, detail="Result already exists for this request")
        
    new_result = RadiologyResult(
        request_id=request_id,
        performed_by=current_user["user_id"],
        findings=result_in.findings,
        conclusion=result_in.conclusion,
        image_url=result_in.image_url
    )
    
    req.status = "Completed" # Automatically update status
    
    db.add(new_result)
    db.flush()
    
    # Audit log
    log_audit(db, current_user["user_id"], "CREATE", "RadiologyResult", new_result.result_id, None, result_in.model_dump(), request.client.host)
    
    db.commit()
    db.refresh(new_result)
    return new_result

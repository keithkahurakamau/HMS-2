from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.config.database import get_db
from app.models.radiology import RadiologyRequest, RadiologyResult, RadiologyExamCatalog
from app.models.patient import Patient
from app.schemas.radiology import (
    RadiologyRequestCreate, RadiologyRequestResponse, RadiologyRequestUpdate,
    RadiologyResultCreate, RadiologyResultResponse,
    RadiologyCatalogCreate, RadiologyCatalogPatch, RadiologyCatalogResponse,
)
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/radiology", tags=["Radiology"])


# ─────────────────────────────────────────────────────────────────────────────
# Catalog endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/catalog",
    response_model=List[RadiologyCatalogResponse],
    dependencies=[Depends(RequirePermission("clinical:read"))],
)
def list_catalog(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(RadiologyExamCatalog)
    if not include_inactive:
        query = query.filter(RadiologyExamCatalog.is_active == True)
    return query.order_by(RadiologyExamCatalog.exam_name).all()


@router.post(
    "/catalog",
    response_model=RadiologyCatalogResponse,
    dependencies=[Depends(RequirePermission("radiology:manage"))],
)
def create_catalog(payload: RadiologyCatalogCreate, db: Session = Depends(get_db)):
    if db.query(RadiologyExamCatalog).filter(RadiologyExamCatalog.exam_name == payload.exam_name).first():
        raise HTTPException(status_code=409, detail=f"Exam '{payload.exam_name}' already exists.")

    row = RadiologyExamCatalog(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/catalog/{catalog_id}",
    response_model=RadiologyCatalogResponse,
    dependencies=[Depends(RequirePermission("radiology:manage"))],
)
def update_catalog(catalog_id: int, payload: RadiologyCatalogPatch, db: Session = Depends(get_db)):
    row = db.query(RadiologyExamCatalog).filter(RadiologyExamCatalog.catalog_id == catalog_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Catalog entry not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/catalog/{catalog_id}",
    dependencies=[Depends(RequirePermission("radiology:manage"))],
)
def deactivate_catalog(catalog_id: int, db: Session = Depends(get_db)):
    row = db.query(RadiologyExamCatalog).filter(RadiologyExamCatalog.catalog_id == catalog_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Catalog entry not found.")
    row.is_active = False
    db.commit()
    return {"status": "deactivated", "catalog_id": catalog_id}


# ─────────────────────────────────────────────────────────────────────────────
# Request endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=RadiologyRequestResponse,
    dependencies=[Depends(RequirePermission("clinical:write"))],
)
def create_radiology_request(
    req_in: RadiologyRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = db.query(Patient).filter(Patient.patient_id == req_in.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    catalog = None
    if req_in.catalog_id is not None:
        catalog = db.query(RadiologyExamCatalog).filter(
            RadiologyExamCatalog.catalog_id == req_in.catalog_id,
            RadiologyExamCatalog.is_active == True,
        ).first()
        if not catalog:
            raise HTTPException(status_code=400, detail="Catalog entry not found or inactive.")

    priority = req_in.priority if req_in.priority in ("Routine", "Urgent", "STAT") else "Routine"
    new_request = RadiologyRequest(
        patient_id=req_in.patient_id,
        catalog_id=catalog.catalog_id if catalog else None,
        exam_type=catalog.exam_name if catalog else req_in.exam_type,
        clinical_notes=req_in.clinical_notes,
        priority=priority,
        billed_price=catalog.base_price if catalog else None,
        requested_by=current_user["user_id"],
        status="Pending",
    )
    db.add(new_request)
    db.flush()

    log_audit(
        db,
        current_user["user_id"],
        "CREATE",
        "RadiologyRequest",
        new_request.request_id,
        None,
        req_in.model_dump(),
        request.client.host,
    )

    db.commit()
    db.refresh(new_request)
    return new_request


@router.get(
    "/",
    response_model=List[RadiologyRequestResponse],
    dependencies=[Depends(RequirePermission("clinical:read"))],
)
def get_radiology_requests(
    status: Optional[str] = None,
    patient_id: Optional[int] = None,
    priority: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(RadiologyRequest)
    if status:
        query = query.filter(RadiologyRequest.status == status)
    if patient_id:
        query = query.filter(RadiologyRequest.patient_id == patient_id)
    if priority:
        query = query.filter(RadiologyRequest.priority == priority)

    return query.order_by(RadiologyRequest.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{request_id}",
    response_model=RadiologyRequestResponse,
    dependencies=[Depends(RequirePermission("clinical:read"))],
)
def get_radiology_request(request_id: int, db: Session = Depends(get_db)):
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found")
    return req


@router.put(
    "/{request_id}/status",
    response_model=RadiologyRequestResponse,
    dependencies=[Depends(RequirePermission("clinical:write"))],
)
def update_radiology_status(
    request_id: int,
    status_update: RadiologyRequestUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found")

    old_status = req.status
    req.status = status_update.status

    log_audit(
        db,
        current_user["user_id"],
        "UPDATE",
        "RadiologyRequest",
        req.request_id,
        {"status": old_status},
        {"status": req.status},
        request.client.host,
    )

    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/{request_id}/result",
    response_model=RadiologyResultResponse,
    dependencies=[Depends(RequirePermission("clinical:write"))],
)
def add_radiology_result(
    request_id: int,
    result_in: RadiologyResultCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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
        image_url=result_in.image_url,
        contrast_used=result_in.contrast_used,
    )

    req.status = "Completed"

    db.add(new_result)
    db.flush()

    log_audit(
        db,
        current_user["user_id"],
        "CREATE",
        "RadiologyResult",
        new_result.result_id,
        None,
        result_in.model_dump(),
        request.client.host,
    )

    db.commit()
    db.refresh(new_result)
    return new_result

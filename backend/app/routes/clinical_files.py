"""Clinical file attachments — upload/list/download/delete documents or images
against a patient (optionally an encounter). base64-in-DB (branding pattern),
size-capped. RBAC clinical:read / clinical:write; writes audit-logged.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.clinical_files import ClinicalFile
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/clinical-files", tags=["Clinical Files"])

# ~2 MB binary ≈ 2.8 MB base64. Cap the stored string so a runaway upload can't
# bloat the tenant DB (frontend compresses/guards too).
MAX_DATA_CHARS = 2_800_000


def _ip(request: Request):
    return request.client.host if request.client else None


def _meta(f: ClinicalFile) -> dict:
    return {
        "file_id": f.file_id, "patient_id": f.patient_id, "record_id": f.record_id,
        "filename": f.filename, "mime": f.mime, "size_bytes": f.size_bytes,
        "uploaded_by": f.uploaded_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


class FileCreate(BaseModel):
    patient_id: int
    filename: str = Field(min_length=1, max_length=255)
    mime: Optional[str] = Field(default=None, max_length=120)
    data: str  # base64 data URL
    record_id: Optional[int] = None


@router.post("", dependencies=[Depends(RequirePermission("clinical:write"))])
def upload_file(req: FileCreate, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    if not db.query(Patient).filter(Patient.patient_id == req.patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")
    if len(req.data) > MAX_DATA_CHARS:
        raise HTTPException(status_code=413, detail="File too large — max ~2 MB per attachment.")
    f = ClinicalFile(
        patient_id=req.patient_id, record_id=req.record_id, filename=req.filename,
        mime=req.mime, size_bytes=len(req.data), data=req.data,
        uploaded_by=current_user["user_id"],
    )
    db.add(f)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "ClinicalFile", f.file_id,
              None, {"patient_id": req.patient_id, "filename": req.filename}, _ip(request))
    db.commit()
    db.refresh(f)
    return _meta(f)


@router.get("", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_files(patient_id: int, db: Session = Depends(get_db)):
    rows = (db.query(ClinicalFile).filter(ClinicalFile.patient_id == patient_id)
            .order_by(ClinicalFile.created_at.desc()).limit(200).all())
    return [_meta(f) for f in rows]


@router.get("/{file_id}", dependencies=[Depends(RequirePermission("clinical:read"))])
def get_file(file_id: int, db: Session = Depends(get_db)):
    f = db.query(ClinicalFile).filter(ClinicalFile.file_id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return {**_meta(f), "data": f.data}


@router.delete("/{file_id}", dependencies=[Depends(RequirePermission("clinical:write"))])
def delete_file(file_id: int, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    f = db.query(ClinicalFile).filter(ClinicalFile.file_id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    log_audit(db, current_user["user_id"], "DELETE", "ClinicalFile", file_id,
              {"filename": f.filename, "patient_id": f.patient_id}, None, _ip(request))
    db.delete(f)
    db.commit()
    return {"status": "deleted", "file_id": file_id}

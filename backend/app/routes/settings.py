"""Per-tenant hospital settings.

Flat key/value endpoints. The frontend renders categories and types straight
from the response so adding a new setting is a single insert — no code change.
"""
from typing import Optional, Any, Dict, List
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.settings import HospitalSetting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
class SettingUpsert(BaseModel):
    category: str
    key: str
    value: Optional[Any] = None
    label: Optional[str] = None
    description: Optional[str] = None
    data_type: Optional[str] = Field(default=None, pattern="^(string|number|boolean|json|secret)$")
    is_sensitive: Optional[bool] = None
    sort_order: Optional[int] = None


class BulkUpdate(BaseModel):
    updates: List[SettingUpsert]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _coerce(data_type: str, raw: Any) -> str:
    """Serialize an incoming value into the TEXT column according to data_type."""
    if raw is None:
        return ""
    if data_type == "json":
        if isinstance(raw, str):
            try:
                json.loads(raw)
                return raw
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        return json.dumps(raw)
    if data_type == "boolean":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        s = str(raw).strip().lower()
        if s in ("true", "1", "yes", "on"):
            return "true"
        if s in ("false", "0", "no", "off", ""):
            return "false"
        raise HTTPException(status_code=400, detail=f"Cannot parse '{raw}' as boolean.")
    if data_type == "number":
        try:
            float(str(raw))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Cannot parse '{raw}' as number.") from exc
        return str(raw)
    # string | secret
    return str(raw)


def _decode(data_type: str, raw: Optional[str]) -> Any:
    if raw is None or raw == "":
        return None
    if data_type == "json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if data_type == "boolean":
        return raw.lower() == "true"
    if data_type == "number":
        try:
            f = float(raw)
            return int(f) if f.is_integer() else f
        except ValueError:
            return raw
    return raw


def _serialize(s: HospitalSetting, redact: bool = True) -> Dict[str, Any]:
    value: Any
    if redact and s.is_sensitive:
        value = "••••••" if s.value else None
    else:
        value = _decode(s.data_type, s.value)
    return {
        "setting_id": s.setting_id,
        "category": s.category,
        "key": s.key,
        "label": s.label or s.key.replace("_", " ").title(),
        "description": s.description,
        "data_type": s.data_type,
        "value": value,
        "is_sensitive": bool(s.is_sensitive),
        "sort_order": s.sort_order,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/", dependencies=[Depends(RequirePermission("settings:read"))])
def list_settings(category: Optional[str] = None, db: Session = Depends(get_db)):
    """List all settings, grouped by category."""
    query = db.query(HospitalSetting)
    if category:
        query = query.filter(HospitalSetting.category == category)
    rows = query.order_by(HospitalSetting.category, HospitalSetting.sort_order, HospitalSetting.key).all()

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault(r.category, []).append(_serialize(r))
    return {
        "categories": [{"key": c, "items": items} for c, items in grouped.items()],
        "count": len(rows),
    }


@router.get("/{category}/{key}", dependencies=[Depends(RequirePermission("settings:read"))])
def get_setting(category: str, key: str, db: Session = Depends(get_db)):
    row = db.query(HospitalSetting).filter(
        HospitalSetting.category == category, HospitalSetting.key == key
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found.")
    return _serialize(row)


@router.put("/", dependencies=[Depends(RequirePermission("settings:manage"))])
def upsert_setting(
    payload: SettingUpsert,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.query(HospitalSetting).filter(
        HospitalSetting.category == payload.category, HospitalSetting.key == payload.key
    ).first()

    data_type = payload.data_type or (row.data_type if row else "string")
    coerced = _coerce(data_type, payload.value)

    if not row:
        row = HospitalSetting(
            category=payload.category,
            key=payload.key,
            label=payload.label or payload.key.replace("_", " ").title(),
            description=payload.description,
            data_type=data_type,
            value=coerced,
            is_sensitive=bool(payload.is_sensitive) if payload.is_sensitive is not None else False,
            sort_order=payload.sort_order or 0,
            updated_by=current_user["user_id"],
        )
        db.add(row)
    else:
        row.value = coerced
        if payload.label is not None:
            row.label = payload.label
        if payload.description is not None:
            row.description = payload.description
        if payload.data_type is not None:
            row.data_type = payload.data_type
        if payload.is_sensitive is not None:
            row.is_sensitive = payload.is_sensitive
        if payload.sort_order is not None:
            row.sort_order = payload.sort_order
        row.updated_by = current_user["user_id"]

    db.commit()
    db.refresh(row)
    return _serialize(row, redact=False)


@router.put("/bulk", dependencies=[Depends(RequirePermission("settings:manage"))])
def bulk_update(
    payload: BulkUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    updated = []
    for upsert in payload.updates:
        row = db.query(HospitalSetting).filter(
            HospitalSetting.category == upsert.category,
            HospitalSetting.key == upsert.key,
        ).first()
        if not row:
            continue  # bulk update skips unknown keys silently
        data_type = upsert.data_type or row.data_type
        row.value = _coerce(data_type, upsert.value)
        if upsert.data_type:
            row.data_type = upsert.data_type
        row.updated_by = current_user["user_id"]
        updated.append(row.setting_id)

    db.commit()
    return {"updated": updated, "count": len(updated)}


@router.delete("/{category}/{key}", dependencies=[Depends(RequirePermission("settings:manage"))])
def delete_setting(category: str, key: str, db: Session = Depends(get_db)):
    row = db.query(HospitalSetting).filter(
        HospitalSetting.category == category, HospitalSetting.key == key
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Setting not found.")
    db.delete(row)
    db.commit()
    return {"status": "deleted", "category": category, "key": key}

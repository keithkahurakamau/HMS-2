"""Maternity module: pregnancy episodes, ANC/PNC visits, deliveries, newborns.

Labor + partograph endpoints live in maternity_labor.py (same module key).
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import RequirePermission

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])


@router.get("/episodes", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_episodes():
    return []

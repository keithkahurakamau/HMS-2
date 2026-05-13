from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from app.config.database import get_db
from app.models.patient import Patient
from app.models.user import User
from app.models.billing import Invoice
from app.models.clinical import PatientQueue
from app.core.dependencies import RequirePermission
from app.core import cache

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Dashboard"])

# Dashboard metrics are aggregations across every patient/queue/invoice for the
# tenant. The same payload is requested by every Admin user every time the
# Command Center re-renders, so a tight TTL drops the per-tenant DB load
# materially without showing meaningfully stale numbers. Writes that move the
# numbers (new patient, new invoice, queue movement) invalidate this key.
_DASHBOARD_PREFIX = "analytics:dashboard"
_DASHBOARD_TTL = 30


@router.get("/dashboard", dependencies=[Depends(RequirePermission("users:manage"))])
@cache.cached(_DASHBOARD_PREFIX, ttl_seconds=_DASHBOARD_TTL)
def get_dashboard_metrics(request: Request, db: Session = Depends(get_db)):
    """Aggregates system-wide telemetry for the Command Center."""
    today = date.today()
    
    total_patients = db.query(Patient).count()
    active_staff = db.query(User).filter(User.is_active == True).count()
    
    # Today's Revenue
    today_revenue = db.query(func.sum(Invoice.amount_paid)).filter(
        func.date(Invoice.billing_date) == today
    ).scalar() or 0.0

    # Live Queue Load
    waiting_patients = db.query(PatientQueue).filter(PatientQueue.status != "Completed").all()
    total_waiting = len(waiting_patients)
    
    queue_breakdown = {
        "Triage": len([p for p in waiting_patients if p.department == "Triage"]),
        "Consultation": len([p for p in waiting_patients if p.department == "Consultation"]),
        "Laboratory": len([p for p in waiting_patients if p.department == "Laboratory"]),
        "Pharmacy": len([p for p in waiting_patients if p.department == "Pharmacy"]),
        "Billing": len([p for p in waiting_patients if p.department == "Billing"])
    }

    return {
        "total_patients": total_patients,
        "total_staff": active_staff,
        "today_revenue": float(today_revenue),
        "total_waiting": total_waiting,
        "queue_breakdown": queue_breakdown
    }
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from app.config.database import get_db
from app.models.patient import Patient
from app.models.user import User
from app.models.billing import Invoice
from app.models.clinical import PatientQueue
from app.core.dependencies import RequirePermission

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Dashboard"])

@router.get("/dashboard", dependencies=[Depends(RequirePermission("reports:view"))])
def get_dashboard_metrics(db: Session = Depends(get_db)):
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
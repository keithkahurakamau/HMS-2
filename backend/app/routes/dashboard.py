from fastapi import APIRouter, Depends
from typing import List, Dict
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Worker Dashboard"])

@router.get("/worker-agenda")
def get_worker_agenda(current_user: dict = Depends(get_current_user)) -> List[Dict]:
    """
    Protected endpoint returning role-specific mock agenda items.
    """
    role = current_user.get("role", "UNKNOWN").upper()
    
    mock_tasks = {
        "DOCTOR": [
            {"id": 1, "title": "Review Lab Results for John Doe", "priority": "high", "status": "pending", "time": "10:00 AM"},
            {"id": 2, "title": "Patient Consult - Jane Smith", "priority": "medium", "status": "scheduled", "time": "11:00 AM"}
        ],
        "CASHIER": [
            {"id": 1, "title": "Reconcile morning M-Pesa float", "priority": "normal", "status": "completed", "time": "09:00 AM"},
            {"id": 2, "title": "Process Insurance Claims", "priority": "medium", "status": "pending", "time": "11:00 AM"}
        ],
        "RECEPTIONIST": [
            {"id": 1, "title": "Patient Check-ins", "priority": "normal", "status": "pending", "time": "08:00 AM"},
            {"id": 2, "title": "Triage Queue Management", "priority": "high", "status": "pending", "time": "14:00 PM"}
        ],
        "LAB_TECH": [
            {"id": 1, "title": "Process Blood Samples (Batch 45A)", "priority": "high", "status": "pending", "time": "09:00 AM"},
            {"id": 2, "title": "Microbiology Cultures", "priority": "medium", "status": "pending", "time": "13:00 PM"}
        ],
        "PHARMACIST": [
            {"id": 1, "title": "Prescription Verification", "priority": "high", "status": "pending", "time": "10:00 AM"},
            {"id": 2, "title": "Expired Meds Check", "priority": "low", "status": "completed", "time": "12:00 PM"}
        ]
    }
    
    return mock_tasks.get(role, [])
from fastapi import APIRouter
from typing import List

router = APIRouter(prefix="/api/public", tags=["Public Portal"])

# Simulated Master DB / SaaS Registry
# In production, this would query a central database (e.g. hms_master)
MOCK_TENANTS = [
    {
        "id": "tenant_1",
        "name": "Mayo Clinic Nairobi",
        "domain": "mayoclinic.hms.co.ke",
        "db_name": "mayoclinic_db",
        "theme_color": "blue",
        "is_premium": True
    },
    {
        "id": "tenant_2",
        "name": "St. John's Hospital",
        "domain": "stjohns.hms.co.ke",
        "db_name": "stjohns_db",
        "theme_color": "green",
        "is_premium": False
    },
    {
        "id": "tenant_3",
        "name": "Aga Khan Regional",
        "domain": "agakhan.hms.co.ke",
        "db_name": "agakhan_db",
        "theme_color": "red",
        "is_premium": True
    }
]

@router.get("/hospitals")
def get_available_hospitals():
    """Returns a list of all active hospitals on the platform for the gateway portal."""
    return MOCK_TENANTS

from pydantic import BaseModel
import uuid

class TenantCreate(BaseModel):
    name: str
    domain: str
    db_name: str
    theme_color: str
    is_premium: bool

@router.post("/hospitals")
def provision_hospital(tenant: TenantCreate):
    """Simulates provisioning a new isolated hospital database instance."""
    new_tenant = tenant.model_dump()
    new_tenant["id"] = f"tenant_{str(uuid.uuid4())[:8]}"
    
    # In a real system, this would trigger an async task to:
    # 1. Create a new Postgres database `CREATE DATABASE {tenant.db_name}`
    # 2. Run Alembic migrations on that specific database
    # 3. Seed initial admin user
    
    MOCK_TENANTS.append(new_tenant)
    return {"message": "Tenant provisioned successfully", "tenant": new_tenant}

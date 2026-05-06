from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config.settings import settings

from fastapi import Request

# Create the Default Engine (used for alembic and fallbacks)
default_engine = create_engine(settings.DATABASE_URL)
DefaultSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=default_engine)

# Master DB Engine — always points at hms_master for tenant registry & superadmin
_master_db_url = settings.DATABASE_URL.rsplit('/', 1)[0] + "/hms_master"
master_engine = create_engine(_master_db_url)
MasterSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)

Base = declarative_base()

def get_master_db():
    """Yields a session to the central hms_master database."""
    db = MasterSessionLocal()
    try:
        yield db
    finally:
        db.close()
tenant_engines = {}

def get_tenant_engine(tenant_db_name: str):
    if tenant_db_name in tenant_engines:
        return tenant_engines[tenant_db_name]
    
    # Extract base URL and append tenant db name
    # example: postgresql://user:pass@localhost:5432/mayoclinic_db -> postgresql://user:pass@localhost:5432/tenant_db_name
    base_url = settings.DATABASE_URL.rsplit('/', 1)[0]
    db_url = f"{base_url}/{tenant_db_name}"
    
    engine = create_engine(db_url)
    tenant_engines[tenant_db_name] = engine
    return engine

def get_db(request: Request = None):
    # If no request (e.g. background tasks or tests), fallback to default
    if not request:
        db = DefaultSessionLocal()
        try:
            yield db
        finally:
            db.close()
        return

    # Extract Tenant from Header
    tenant_db_name = request.headers.get("X-Tenant-ID")
    
    # Fallback to default DB if no tenant header is provided (for local testing/alembic)
    if not tenant_db_name:
        tenant_db_name = settings.DATABASE_URL.rsplit('/', 1)[1]
        
    engine = get_tenant_engine(tenant_db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()
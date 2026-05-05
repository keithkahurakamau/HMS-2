import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file 

# 1. Add the backend directory to the Python path so Alembic can find the 'app' module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2. Import your database Base
from app.config.database import Base

# 3. 🚨 CRITICAL: You MUST import every single model file here!
# If a model isn't imported, Alembic won't know it exists and won't create the table.
from app.models.user import User, Role, Permission, role_permissions
from app.models.patient import Patient
from app.models.clinical import Appointment, PatientQueue, MedicalRecord
from app.models.laboratory import LabTestCatalog, LabTestRequiredItem, LabTest
from app.models.inventory import Location, InventoryItem, StockBatch, StockTransfer, DispenseLog, InventoryUsageLog
from app.models.wards import Ward, Bed, AdmissionRecord
from app.models.billing import Invoice, InvoiceItem, Payment, IdempotencyKey
from app.models.audit import AuditLog
from app.models.medical_history import MedicalHistoryEntry, DataAccessLog, ConsentRecord
from app.models.mpesa import MpesaConfig, MpesaTransaction

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Point Alembic to your metadata
target_metadata = Base.metadata

def get_url():
    """
    Securely load the database URL from the environment.
    Ensure you have a .env file with DATABASE_URL=postgresql://user:pass@localhost:5432/medicare_db
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set!")
    return url

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override the sqlalchemy.url in alembic.ini with our secure environment variable
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
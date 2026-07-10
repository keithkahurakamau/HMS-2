# Maternity Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the opt-in Maternity module — pregnancy episodes, ANC/PNC visits, labor partograph, deliveries, newborn records — per `docs/superpowers/specs/2026-07-10-maternity-module-design.md`.

**Architecture:** Standalone module following the referrals recipe: new model file + alembic revision + two route files + opt-in module flag + `maternity:read`/`maternity:manage` permissions. Billing reuses the consultation-fee pattern (`Invoice`/`InvoiceItem` + `post_from_event`). Frontend is one guarded page with three tabs and a custom SVG partograph.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + Vite + Vitest/RTL (frontend), pytest + httpx live-server tests.

## Global Constraints

- Branch: `feat/maternity-module` (already created off `development`). PR targets `development` only.
- Every file stays under 500 lines — route surface is pre-split into `maternity.py` + `maternity_labor.py`.
- Backend tests are live-server: `uvicorn` running on `localhost:8000` with `REDIS_URL=""`, tenant `mayoclinic_db`, header `X-Tenant-ID: mayoclinic_db`, CSRF dance per `tests/test_queue.py`.
- The `maternity` feature flag must be enabled for `mayoclinic_db` (Task 2, Step 6) or every endpoint returns 402.
- Alembic head before this work: `c2d3e4f5a6b7`. New revision id: `b7e4a1c9d2f5`.
- Any schema change requires: alembic revision AND `app/models/maternity.py` added to the `scripts/migrate_all_tenants.py` import block AND the seed mirrored as a `migrate_one` hook.
- Partograph rows are append-only: the API exposes no UPDATE or DELETE for `partograph_entries`.
- Run `npx eslint` on touched frontend files before any push (vite build misses no-undef).
- Commit after every green task; messages end with `Co-Authored-By: RuFlo <ruv@ruv.net>`.

---

### Task 1: Data model + alembic migration

**Files:**
- Create: `backend/app/models/maternity.py`
- Create: `backend/alembic/versions/b7e4a1c9d2f5_add_maternity_tables.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (import block, ~line 59)

**Interfaces:**
- Produces: ORM classes `PregnancyEpisode`, `AncVisit`, `LaborAdmission`, `PartographEntry`, `DeliveryRecord`, `NewbornRecord`, `PncVisit` importable from `app.models.maternity`. Table names: `pregnancy_episodes`, `anc_visits`, `labor_admissions`, `partograph_entries`, `delivery_records`, `newborn_records`, `pnc_visits`.

- [ ] **Step 1: Write the model file**

`backend/app/models/maternity.py`:

```python
"""Maternity module: pregnancy episodes, ANC/PNC visits, labor partograph,
deliveries, newborns.

A pregnancy is a first-class *episode* a patient can have at most one Active
of at a time (partial unique index). Labor rides a normal wards admission via
the thin `labor_admissions` link table — bed management and daily ward billing
stay in the wards module. Partograph entries are append-only: corrections are
new rows pointing at the row they supersede via `corrects_entry_id`.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class PregnancyEpisode(Base):
    __tablename__ = "pregnancy_episodes"

    episode_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    gravida = Column(Integer, nullable=False, default=1)
    para = Column(Integer, nullable=False, default=0)
    lmp = Column(Date, nullable=True)
    edd = Column(Date, nullable=True)
    blood_group = Column(String(8), nullable=True)
    rhesus = Column(String(4), nullable=True)
    risk_flags = Column(Text, nullable=True)
    # Active | Delivered | Closed | Transferred
    status = Column(String(20), nullable=False, default="Active", index=True)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient")
    anc_visits = relationship("AncVisit", backref="episode", cascade="all, delete-orphan")
    pnc_visits = relationship("PncVisit", backref="episode", cascade="all, delete-orphan")

    __table_args__ = (
        # One Active pregnancy per patient. Enforced in Postgres via the
        # partial unique index created in the alembic revision; declared here
        # for create_all parity on fresh bootstraps.
        Index(
            "uq_pregnancy_active_per_patient",
            "patient_id",
            unique=True,
            postgresql_where=(status == "Active"),
        ),
    )


class AncVisit(Base):
    __tablename__ = "anc_visits"

    visit_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    visit_number = Column(Integer, nullable=False, default=1)
    visit_date = Column(Date, nullable=False)
    gestation_weeks = Column(Integer, nullable=True)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    weight_kg = Column(Numeric(5, 1), nullable=True)
    fundal_height_cm = Column(Numeric(4, 1), nullable=True)
    fetal_heart_rate = Column(Integer, nullable=True)
    urine_dip = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LaborAdmission(Base):
    __tablename__ = "labor_admissions"

    labor_admission_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    admission_id = Column(Integer, ForeignKey("admission_records.admission_id", ondelete="CASCADE"), nullable=False, unique=True)
    # Partograph time zero: set when the first >= 4 cm entry lands, or manually.
    active_labor_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    episode = relationship("PregnancyEpisode", backref="labor_admissions")
    entries = relationship("PartographEntry", backref="labor_admission", cascade="all, delete-orphan")


class PartographEntry(Base):
    """Append-only. No UPDATE/DELETE endpoints exist; corrections are new
    rows pointing at the superseded row via corrects_entry_id."""
    __tablename__ = "partograph_entries"

    entry_id = Column(Integer, primary_key=True)
    labor_admission_id = Column(Integer, ForeignKey("labor_admissions.labor_admission_id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cervical_dilation_cm = Column(Numeric(3, 1), nullable=True)
    descent_fifths = Column(Integer, nullable=True)
    contractions_per_10min = Column(Integer, nullable=True)
    contraction_duration_sec = Column(Integer, nullable=True)
    fetal_heart_rate = Column(Integer, nullable=True)
    liquor = Column(String(4), nullable=True)     # I / C / M1 / M2 / M3 / B
    moulding = Column(String(4), nullable=True)   # 0 / + / ++ / +++
    maternal_bp_systolic = Column(Integer, nullable=True)
    maternal_bp_diastolic = Column(Integer, nullable=True)
    maternal_pulse = Column(Integer, nullable=True)
    temperature_c = Column(Numeric(3, 1), nullable=True)
    drugs_note = Column(String(255), nullable=True)
    corrects_entry_id = Column(Integer, ForeignKey("partograph_entries.entry_id", ondelete="SET NULL"), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeliveryRecord(Base):
    __tablename__ = "delivery_records"

    delivery_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    labor_admission_id = Column(Integer, ForeignKey("labor_admissions.labor_admission_id", ondelete="SET NULL"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=False)
    # SVD | Assisted | CSection | Breech
    mode = Column(String(20), nullable=False)
    placenta_complete = Column(Boolean, nullable=True)
    blood_loss_ml = Column(Integer, nullable=True)
    perineum = Column(String(40), nullable=True)
    complications = Column(Text, nullable=True)
    # Stable | Referred | Deceased
    mother_status = Column(String(20), nullable=False, default="Stable")
    conducted_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    assistant_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    episode = relationship("PregnancyEpisode", backref="deliveries")
    newborns = relationship("NewbornRecord", backref="delivery", cascade="all, delete-orphan")


class NewbornRecord(Base):
    __tablename__ = "newborn_records"

    newborn_id = Column(Integer, primary_key=True)
    delivery_id = Column(Integer, ForeignKey("delivery_records.delivery_id", ondelete="CASCADE"), nullable=False, index=True)
    birth_order = Column(Integer, nullable=False, default=1)
    sex = Column(String(10), nullable=False)
    weight_g = Column(Integer, nullable=True)
    apgar_1 = Column(Integer, nullable=True)
    apgar_5 = Column(Integer, nullable=True)
    apgar_10 = Column(Integer, nullable=True)
    # Live | FSB | MSB
    outcome = Column(String(10), nullable=False, default="Live")
    resuscitated = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    registered_patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PncVisit(Base):
    __tablename__ = "pnc_visits"

    visit_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    newborn_id = Column(Integer, ForeignKey("newborn_records.newborn_id", ondelete="SET NULL"), nullable=True)
    visit_number = Column(Integer, nullable=False, default=1)
    visit_date = Column(Date, nullable=False)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    weight_kg = Column(Numeric(5, 1), nullable=True)
    involution = Column(String(40), nullable=True)
    lochia = Column(String(40), nullable=True)
    feeding = Column(String(40), nullable=True)
    cord_status = Column(String(40), nullable=True)
    baby_weight_g = Column(Integer, nullable=True)
    urine_dip = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Write the alembic revision**

`backend/alembic/versions/b7e4a1c9d2f5_add_maternity_tables.py`:

```python
"""Add maternity module tables + permissions

Revision ID: b7e4a1c9d2f5
Revises: c2d3e4f5a6b7
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e4a1c9d2f5"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pregnancy_episodes",
        sa.Column("episode_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("gravida", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("para", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lmp", sa.Date(), nullable=True),
        sa.Column("edd", sa.Date(), nullable=True),
        sa.Column("blood_group", sa.String(8), nullable=True),
        sa.Column("rhesus", sa.String(4), nullable=True),
        sa.Column("risk_flags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pregnancy_episodes_patient_id", "pregnancy_episodes", ["patient_id"])
    op.create_index("ix_pregnancy_episodes_status", "pregnancy_episodes", ["status"])
    op.create_index(
        "uq_pregnancy_active_per_patient", "pregnancy_episodes", ["patient_id"],
        unique=True, postgresql_where=sa.text("status = 'Active'"),
    )

    op.create_table(
        "anc_visits",
        sa.Column("visit_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("gestation_weeks", sa.Integer(), nullable=True),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("fundal_height_cm", sa.Numeric(4, 1), nullable=True),
        sa.Column("fetal_heart_rate", sa.Integer(), nullable=True),
        sa.Column("urine_dip", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_anc_visits_episode_id", "anc_visits", ["episode_id"])

    op.create_table(
        "labor_admissions",
        sa.Column("labor_admission_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("admission_id", sa.Integer(), sa.ForeignKey("admission_records.admission_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("active_labor_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_labor_admissions_episode_id", "labor_admissions", ["episode_id"])

    op.create_table(
        "partograph_entries",
        sa.Column("entry_id", sa.Integer(), primary_key=True),
        sa.Column("labor_admission_id", sa.Integer(), sa.ForeignKey("labor_admissions.labor_admission_id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cervical_dilation_cm", sa.Numeric(3, 1), nullable=True),
        sa.Column("descent_fifths", sa.Integer(), nullable=True),
        sa.Column("contractions_per_10min", sa.Integer(), nullable=True),
        sa.Column("contraction_duration_sec", sa.Integer(), nullable=True),
        sa.Column("fetal_heart_rate", sa.Integer(), nullable=True),
        sa.Column("liquor", sa.String(4), nullable=True),
        sa.Column("moulding", sa.String(4), nullable=True),
        sa.Column("maternal_bp_systolic", sa.Integer(), nullable=True),
        sa.Column("maternal_bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("maternal_pulse", sa.Integer(), nullable=True),
        sa.Column("temperature_c", sa.Numeric(3, 1), nullable=True),
        sa.Column("drugs_note", sa.String(255), nullable=True),
        sa.Column("corrects_entry_id", sa.Integer(), sa.ForeignKey("partograph_entries.entry_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_partograph_entries_labor_admission_id", "partograph_entries", ["labor_admission_id"])

    op.create_table(
        "delivery_records",
        sa.Column("delivery_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("labor_admission_id", sa.Integer(), sa.ForeignKey("labor_admissions.labor_admission_id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("placenta_complete", sa.Boolean(), nullable=True),
        sa.Column("blood_loss_ml", sa.Integer(), nullable=True),
        sa.Column("perineum", sa.String(40), nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        sa.Column("mother_status", sa.String(20), nullable=False, server_default=sa.text("'Stable'")),
        sa.Column("conducted_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_delivery_records_episode_id", "delivery_records", ["episode_id"])

    op.create_table(
        "newborn_records",
        sa.Column("newborn_id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("delivery_records.delivery_id", ondelete="CASCADE"), nullable=False),
        sa.Column("birth_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sex", sa.String(10), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("apgar_1", sa.Integer(), nullable=True),
        sa.Column("apgar_5", sa.Integer(), nullable=True),
        sa.Column("apgar_10", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False, server_default=sa.text("'Live'")),
        sa.Column("resuscitated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("registered_patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_newborn_records_delivery_id", "newborn_records", ["delivery_id"])

    op.create_table(
        "pnc_visits",
        sa.Column("visit_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("newborn_id", sa.Integer(), sa.ForeignKey("newborn_records.newborn_id", ondelete="SET NULL"), nullable=True),
        sa.Column("visit_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("involution", sa.String(40), nullable=True),
        sa.Column("lochia", sa.String(40), nullable=True),
        sa.Column("feeding", sa.String(40), nullable=True),
        sa.Column("cord_status", sa.String(40), nullable=True),
        sa.Column("baby_weight_g", sa.Integer(), nullable=True),
        sa.Column("urine_dip", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnc_visits_episode_id", "pnc_visits", ["episode_id"])

    # Permissions + base role grants (mirrors e2c5b9314f78 referrals pattern).
    for codename, description in (
        ("maternity:read", "View maternity episodes, partographs, and deliveries"),
        ("maternity:manage", "Record ANC/PNC visits, partograph entries, and deliveries"),
    ):
        op.execute(
            f"""
            INSERT INTO permissions (codename, description)
            SELECT '{codename}', '{description}'
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = '{codename}');
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.role_id, p.permission_id
            FROM roles r CROSS JOIN permissions p
            WHERE p.codename = '{codename}'
              AND r.name IN ('Admin', 'Doctor', 'Nurse')
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
              );
            """
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename IN ('maternity:read', 'maternity:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('maternity:read', 'maternity:manage');")
    for table in ("pnc_visits", "newborn_records", "delivery_records",
                  "partograph_entries", "labor_admissions", "anc_visits",
                  "pregnancy_episodes"):
        op.drop_table(table)
```

- [ ] **Step 3: Register the model file in migrate_all_tenants**

In `backend/scripts/migrate_all_tenants.py`, find the `from app.models import (` block (~line 59, contains `wards as _wards`) and add one line inside the parentheses, alphabetically:

```python
    maternity as _maternity,  # noqa: F401
```

- [ ] **Step 4: Apply and verify the migration on the test tenant**

Run (from `backend/`, venv active, `.env` loaded):
```bash
DATABASE_URL="${DATABASE_URL%/*}/mayoclinic_db" alembic upgrade head
python3 -c "
from sqlalchemy import create_engine, inspect
from app.config.settings import settings
base = settings.DATABASE_URL.rsplit('/', 1)[0]
insp = inspect(create_engine(f'{base}/mayoclinic_db'))
tables = set(insp.get_table_names())
need = {'pregnancy_episodes','anc_visits','labor_admissions','partograph_entries','delivery_records','newborn_records','pnc_visits'}
missing = need - tables
print('MISSING:', missing) if missing else print('ALL 7 TABLES PRESENT')
"
```
Expected: `ALL 7 TABLES PRESENT`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/maternity.py backend/alembic/versions/b7e4a1c9d2f5_add_maternity_tables.py backend/scripts/migrate_all_tenants.py
git commit -m "feat(maternity): data model + migration for episodes, visits, partograph, deliveries

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 2: Module catalogue, permissions, department routing, router registration

**Files:**
- Modify: `backend/app/core/modules.py` (MODULES tuple ~line 73, URL_PREFIX_MAP ~line 122)
- Modify: `backend/app/services/tenant_provisioning.py` (PERMISSIONS ~line 169, ROLE_GRANTS Doctor ~line 209 and Nurse ~line 216)
- Modify: `backend/app/routes/patients.py` (`_DEPARTMENT_ALIASES` ~line 347, `CANONICAL_DEPARTMENTS` ~line 366)
- Modify: `backend/app/main.py` (import ~line 47, include_router ~line 293)
- Create: `backend/app/routes/maternity.py` (skeleton router so registration compiles)
- Test: `backend/tests/test_maternity_episodes.py` (gate/permission tests only, extended in Task 4)

**Interfaces:**
- Produces: module key `"maternity"`, permissions `maternity:read` / `maternity:manage`, canonical department `"Maternity"`, router at prefix `/api/maternity`.

- [ ] **Step 1: Create the skeleton router**

`backend/app/routes/maternity.py`:

```python
"""Maternity module: pregnancy episodes, ANC/PNC visits, deliveries, newborns.

Labor + partograph endpoints live in maternity_labor.py (same module key).
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import RequirePermission

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])


@router.get("/episodes", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_episodes():
    return []
```

- [ ] **Step 2: Wire the module catalogue**

In `backend/app/core/modules.py` add to the end of `MODULES` (after the `accounting` line):

```python
    ModuleDef("maternity",    "Maternity",          "ANC/PNC clinics, labor partograph, deliveries, newborns.", False),
```

And to the end of `URL_PREFIX_MAP` (after the `accounting` line):

```python
    ("/api/maternity/",                   "maternity"),
```

- [ ] **Step 3: Add permissions and role grants**

In `backend/app/services/tenant_provisioning.py`, after the referrals block (~line 169) add:

```python
    # ── Maternity ────────────────────────────────────────────────────────
    ("maternity:read",         "View maternity episodes, partographs, and deliveries"),
    ("maternity:manage",       "Record ANC/PNC visits, partograph entries, and deliveries"),
```

In the `"Doctor"` grant list add `"maternity:read", "maternity:manage",` and in the `"Nurse"` grant list add `"maternity:read", "maternity:manage",` (Admin gets everything via backfill_admin_permissions).

- [ ] **Step 4: Add the routable department**

In `backend/app/routes/patients.py` `_DEPARTMENT_ALIASES` add:

```python
    "maternity":          "Maternity",
    "anc":                "Maternity",
    "mch":                "Maternity",
```

And add `"Maternity"` to `CANONICAL_DEPARTMENTS`.

- [ ] **Step 5: Register the router**

In `backend/app/main.py` next to the referrals import (~line 47):

```python
import app.routes.maternity as maternity_module
```

And with the other `include_router` calls:

```python
app.include_router(maternity_module.router)
```

- [ ] **Step 6: Enable the maternity flag for the test tenant**

Run (from `backend/`):
```bash
python3 -c "
import json
from sqlalchemy import create_engine, text
from app.config.settings import settings
eng = create_engine(settings.DATABASE_URL)
with eng.begin() as cx:
    row = cx.execute(text(\"SELECT feature_flags FROM tenants WHERE db_name = 'mayoclinic_db'\")).first()
    flags = json.loads(row[0]) if row and row[0] else {}
    flags['maternity'] = True
    cx.execute(text(\"UPDATE tenants SET feature_flags = :f WHERE db_name = 'mayoclinic_db'\"), {'f': json.dumps(flags)})
print('maternity flag ON for mayoclinic_db')
"
```
(If the master table's name/column differs, check `backend/app/models/master.py` — the tenant table is `tenants` with a Text `feature_flags` column.)

- [ ] **Step 7: Write the gate/permission tests**

`backend/tests/test_maternity_episodes.py`:

```python
"""Maternity module: gating, permissions, and episode lifecycle tests."""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/maternity/episodes")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


class TestAccess:
    def test_unauthenticated_401(self, client):
        r = client.get("/api/maternity/episodes")
        assert r.status_code == 401

    def test_nurse_can_list(self, client, nurse_cookies):
        r = client.get("/api/maternity/episodes", cookies=nurse_cookies)
        assert r.status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        r = client.get("/api/maternity/episodes", cookies=receptionist_cookies)
        assert r.status_code == 403
```

- [ ] **Step 8: Restart the dev server and run the tests**

```bash
# in the server terminal: restart uvicorn so new routes + permissions load
REDIS_URL="" uvicorn app.main:app --port 8000
# then:
python3 -m pytest tests/test_maternity_episodes.py -v
```
Expected: 3 passed. (`test_nurse_can_list` passes because the alembic revision granted Nurse the permission in Task 1 Step 4; the skeleton returns `[]`.)

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/modules.py backend/app/services/tenant_provisioning.py backend/app/routes/patients.py backend/app/main.py backend/app/routes/maternity.py backend/tests/test_maternity_episodes.py
git commit -m "feat(maternity): module wiring — catalogue, permissions, Maternity department, router

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 3: Price-list seed service + migrate_one hook

**Files:**
- Create: `backend/app/services/maternity_seed.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (add `_seed_maternity_price_list` next to `_seed_standard_lab_catalog`, ~line 706, and call it in `migrate_one` after `_seed_standard_lab_catalog(tenant_url)`, ~line 779)
- Test: `backend/tests/test_maternity_seed.py`

**Interfaces:**
- Produces: `seed_maternity_price_list(db) -> int` (rows inserted; idempotent). Service codes: `MAT-ANC-VISIT`, `MAT-PNC-VISIT`, `MAT-DEL-SVD`, `MAT-DEL-ASSISTED`, `MAT-DEL-CS`, `MAT-DEL-BREECH` — all category `"Maternity"`, `unit_price=0`, `revenue_account_id` → CoA account with code `4700` when present.
- Consumes: `PriceListItem`, `Account` from `app.models.accounting`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_maternity_seed.py`:

```python
"""Maternity price-list seed: inserts the six MAT-* codes, idempotently."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

CODES = {
    "MAT-ANC-VISIT", "MAT-PNC-VISIT", "MAT-DEL-SVD",
    "MAT-DEL-ASSISTED", "MAT-DEL-CS", "MAT-DEL-BREECH",
}


def _db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return sessionmaker(bind=create_engine(f"{base}/mayoclinic_db"))()


def test_seed_inserts_all_codes_and_is_idempotent():
    from app.models.accounting import PriceListItem
    from app.services.maternity_seed import seed_maternity_price_list

    db = _db()
    try:
        seed_maternity_price_list(db)
        db.commit()
        rows = db.query(PriceListItem).filter(PriceListItem.service_code.in_(CODES)).all()
        assert {r.service_code for r in rows} == CODES
        assert all(r.category == "Maternity" for r in rows)

        # Second run inserts nothing new.
        inserted = seed_maternity_price_list(db)
        db.commit()
        assert inserted == 0
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_maternity_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.maternity_seed'`

- [ ] **Step 3: Write the seed service**

`backend/app/services/maternity_seed.py`:

```python
"""Idempotent maternity price-list seed.

Mirrored into scripts/migrate_all_tenants.migrate_one so legacy tenants get
the codes too (same convention as lab_catalog_seed). All services seed at
unit_price=0 — zero-priced services raise no charge until the hospital sets
real prices in Admin → Pricing.
"""
from sqlalchemy.orm import Session

from app.models.accounting import Account, PriceListItem

MATERNITY_SERVICES = (
    ("MAT-ANC-VISIT",    "Antenatal Clinic Visit"),
    ("MAT-PNC-VISIT",    "Postnatal Clinic Visit"),
    ("MAT-DEL-SVD",      "Normal Delivery (SVD)"),
    ("MAT-DEL-ASSISTED", "Assisted Delivery"),
    ("MAT-DEL-CS",       "Caesarean Section"),
    ("MAT-DEL-BREECH",   "Breech Delivery"),
)


def seed_maternity_price_list(db: Session) -> int:
    """Insert missing MAT-* price-list rows. Returns number inserted."""
    revenue_account = db.query(Account).filter(Account.code == "4700").first()
    existing = {
        code for (code,) in db.query(PriceListItem.service_code)
        .filter(PriceListItem.service_code.in_([c for c, _ in MATERNITY_SERVICES]))
        .all()
    }
    inserted = 0
    for code, name in MATERNITY_SERVICES:
        if code in existing:
            continue
        db.add(PriceListItem(
            service_code=code,
            name=name,
            category="Maternity",
            unit_price=0,
            revenue_account_id=revenue_account.account_id if revenue_account else None,
        ))
        inserted += 1
    return inserted
```

Note: check the actual `Account` code column name with `grep -n 'code' backend/app/models/accounting.py | head` — if the CoA account model uses e.g. `account_code`, use that name in the query instead.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_maternity_seed.py -v`
Expected: PASS

- [ ] **Step 5: Hook into migrate_all_tenants**

In `backend/scripts/migrate_all_tenants.py` add next to `_seed_standard_lab_catalog` (~line 706):

```python
def _seed_maternity_price_list(tenant_url: str) -> None:
    """Maternity MAT-* service codes (idempotent; zero-priced until set)."""
    from app.services.maternity_seed import seed_maternity_price_list
    engine = create_engine(tenant_url)
    try:
        from sqlalchemy.orm import sessionmaker
        db = sessionmaker(bind=engine)()
        try:
            n = seed_maternity_price_list(db)
            db.commit()
            if n:
                LOG.info("    seeded %d maternity price-list rows", n)
        finally:
            db.close()
    finally:
        engine.dispose()
```

And in `migrate_one`, directly after `_seed_standard_lab_catalog(tenant_url)`:

```python
    # Maternity service codes so ANC/PNC/delivery charges can price (idempotent).
    _seed_maternity_price_list(tenant_url)
```

(Match the exact session/engine idioms of `_seed_standard_lab_catalog` in that file — copy its body shape if it differs from the above.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/maternity_seed.py backend/scripts/migrate_all_tenants.py backend/tests/test_maternity_seed.py
git commit -m "feat(maternity): seed MAT-* price-list codes, mirrored into migrate_all_tenants

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 4: Episode endpoints

**Files:**
- Modify: `backend/app/routes/maternity.py` (replace skeleton)
- Test: `backend/tests/test_maternity_episodes.py` (extend)

**Interfaces:**
- Produces:
  - `POST /api/maternity/episodes` body `{patient_id, gravida, para, lmp?, edd?, blood_group?, rhesus?, risk_flags?}` → 200 `{episode_id, ...}`; 409 when an Active episode exists; 404 unknown patient.
  - `GET /api/maternity/episodes?status=&patient_id=` → list of episode dicts `{episode_id, patient_id, patient_name, gravida, para, lmp, edd, status, created_at}`.
  - `GET /api/maternity/episodes/{episode_id}` → episode dict + `anc_visits`, `pnc_visits`, `deliveries` (each a list of dicts), `labor` (list of `{labor_admission_id, admission_id, active_labor_started_at}`).
  - `PATCH /api/maternity/episodes/{episode_id}/close` body `{status: "Closed"|"Transferred", reason?}` → 200.
- Consumes: models from Task 1; permissions from Task 2.

- [ ] **Step 1: Extend the test file with failing lifecycle tests**

Append to `backend/tests/test_maternity_episodes.py`:

```python
def _make_patient(client, admin_cookies) -> int:
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Mat{suffix}",
        "other_names": "Test Mother",
        "gender": "Female",
        "date_of_birth": "1996-04-02",
        "phone_number": f"+2547{suffix[:8]}",
        "id_type": "None",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


class TestEpisodeLifecycle:
    def test_create_list_get_close(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)

        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 2, "para": 1, "lmp": "2026-03-01",
        })
        assert r.status_code == 200, r.text
        ep = r.json()
        assert ep["status"] == "Active"
        # EDD defaults to LMP + 280 days
        assert ep["edd"] == "2026-12-06"

        # Duplicate Active episode → 409
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 2, "para": 1,
        })
        assert r.status_code == 409

        # List filters by patient
        r = client.get(f"/api/maternity/episodes?patient_id={pid}", cookies=nurse_cookies)
        assert r.status_code == 200
        assert any(e["episode_id"] == ep["episode_id"] for e in r.json())

        # Detail view carries the child collections
        r = client.get(f"/api/maternity/episodes/{ep['episode_id']}", cookies=nurse_cookies)
        assert r.status_code == 200
        body = r.json()
        assert body["anc_visits"] == []
        assert body["deliveries"] == []

        # Close
        r = client.patch(
            f"/api/maternity/episodes/{ep['episode_id']}/close",
            cookies=nurse_cookies, json={"status": "Closed", "reason": "test"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "Closed"

        # After closing, a new episode is allowed again
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 3, "para": 1,
        })
        assert r.status_code == 200

    def test_unknown_patient_404(self, client, nurse_cookies):
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": 99999999, "gravida": 1, "para": 0,
        })
        assert r.status_code == 404
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python3 -m pytest tests/test_maternity_episodes.py -v`
Expected: `TestAccess` passes; `TestEpisodeLifecycle` fails (skeleton has no POST route → 405/404).

- [ ] **Step 3: Implement the episode endpoints**

Replace `backend/app/routes/maternity.py` with:

```python
"""Maternity module: pregnancy episodes, ANC/PNC visits, deliveries, newborns.

Labor + partograph endpoints live in maternity_labor.py (same module key).
Every write is audit-logged. Charges ride app.services.maternity_billing.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.maternity import (
    AncVisit, DeliveryRecord, LaborAdmission, NewbornRecord,
    PncVisit, PregnancyEpisode,
)
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])

VALID_CLOSE_STATUS = {"Closed", "Transferred"}


class EpisodeCreate(BaseModel):
    patient_id: int
    gravida: int = Field(1, ge=1, le=30)
    para: int = Field(0, ge=0, le=30)
    lmp: Optional[date] = None
    edd: Optional[date] = None
    blood_group: Optional[str] = Field(default=None, max_length=8)
    rhesus: Optional[str] = Field(default=None, max_length=4)
    risk_flags: Optional[str] = None


class EpisodeClose(BaseModel):
    status: str
    reason: Optional[str] = None


def _episode_dict(db: Session, ep: PregnancyEpisode) -> dict:
    patient = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first()
    return {
        "episode_id": ep.episode_id,
        "patient_id": ep.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "gravida": ep.gravida,
        "para": ep.para,
        "lmp": ep.lmp.isoformat() if ep.lmp else None,
        "edd": ep.edd.isoformat() if ep.edd else None,
        "blood_group": ep.blood_group,
        "rhesus": ep.rhesus,
        "risk_flags": ep.risk_flags,
        "status": ep.status,
        "created_at": ep.created_at.isoformat() if ep.created_at else None,
    }


def _get_episode_or_404(db: Session, episode_id: int) -> PregnancyEpisode:
    ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Pregnancy episode not found")
    return ep


@router.post("/episodes", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_episode(req: EpisodeCreate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    active = (
        db.query(PregnancyEpisode)
        .filter(PregnancyEpisode.patient_id == req.patient_id,
                PregnancyEpisode.status == "Active")
        .first()
    )
    if active:
        raise HTTPException(status_code=409,
                            detail=f"Patient already has an Active pregnancy episode (#{active.episode_id}).")
    edd = req.edd or (req.lmp + timedelta(days=280) if req.lmp else None)
    ep = PregnancyEpisode(
        patient_id=req.patient_id, gravida=req.gravida, para=req.para,
        lmp=req.lmp, edd=edd, blood_group=req.blood_group, rhesus=req.rhesus,
        risk_flags=req.risk_flags, created_by=current_user["user_id"],
    )
    db.add(ep)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "PregnancyEpisode", ep.episode_id,
              None, {"patient_id": req.patient_id, "gravida": req.gravida},
              request.client.host)
    db.commit()
    db.refresh(ep)
    return _episode_dict(db, ep)


@router.get("/episodes", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_episodes(status: Optional[str] = None, patient_id: Optional[int] = None,
                  db: Session = Depends(get_db)):
    q = db.query(PregnancyEpisode)
    if status:
        q = q.filter(PregnancyEpisode.status == status)
    if patient_id:
        q = q.filter(PregnancyEpisode.patient_id == patient_id)
    eps = q.order_by(PregnancyEpisode.created_at.desc()).limit(200).all()
    return [_episode_dict(db, ep) for ep in eps]


@router.get("/episodes/{episode_id}", dependencies=[Depends(RequirePermission("maternity:read"))])
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    ep = _get_episode_or_404(db, episode_id)
    body = _episode_dict(db, ep)
    body["anc_visits"] = [
        {
            "visit_id": v.visit_id, "visit_number": v.visit_number,
            "visit_date": v.visit_date.isoformat(), "gestation_weeks": v.gestation_weeks,
            "bp_systolic": v.bp_systolic, "bp_diastolic": v.bp_diastolic,
            "weight_kg": float(v.weight_kg) if v.weight_kg is not None else None,
            "fundal_height_cm": float(v.fundal_height_cm) if v.fundal_height_cm is not None else None,
            "fetal_heart_rate": v.fetal_heart_rate, "urine_dip": v.urine_dip,
            "notes": v.notes,
        }
        for v in sorted(ep.anc_visits, key=lambda v: (v.visit_date, v.visit_id))
    ]
    body["pnc_visits"] = [
        {
            "visit_id": v.visit_id, "visit_number": v.visit_number,
            "visit_date": v.visit_date.isoformat(),
            "bp_systolic": v.bp_systolic, "bp_diastolic": v.bp_diastolic,
            "involution": v.involution, "lochia": v.lochia, "feeding": v.feeding,
            "cord_status": v.cord_status, "baby_weight_g": v.baby_weight_g,
            "notes": v.notes,
        }
        for v in sorted(ep.pnc_visits, key=lambda v: (v.visit_date, v.visit_id))
    ]
    deliveries = (
        db.query(DeliveryRecord)
        .filter(DeliveryRecord.episode_id == episode_id)
        .order_by(DeliveryRecord.delivered_at)
        .all()
    )
    body["deliveries"] = [
        {
            "delivery_id": d.delivery_id,
            "delivered_at": d.delivered_at.isoformat(),
            "mode": d.mode, "mother_status": d.mother_status,
            "blood_loss_ml": d.blood_loss_ml, "complications": d.complications,
            "newborns": [
                {
                    "newborn_id": n.newborn_id, "birth_order": n.birth_order,
                    "sex": n.sex, "weight_g": n.weight_g, "outcome": n.outcome,
                    "apgar_1": n.apgar_1, "apgar_5": n.apgar_5,
                    "registered_patient_id": n.registered_patient_id,
                }
                for n in sorted(d.newborns, key=lambda n: n.birth_order)
            ],
        }
        for d in deliveries
    ]
    body["labor"] = [
        {
            "labor_admission_id": la.labor_admission_id,
            "admission_id": la.admission_id,
            "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
        }
        for la in db.query(LaborAdmission).filter(LaborAdmission.episode_id == episode_id).all()
    ]
    return body


@router.patch("/episodes/{episode_id}/close", dependencies=[Depends(RequirePermission("maternity:manage"))])
def close_episode(episode_id: int, req: EpisodeClose, request: Request,
                  db: Session = Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    if req.status not in VALID_CLOSE_STATUS:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {sorted(VALID_CLOSE_STATUS)}")
    ep = _get_episode_or_404(db, episode_id)
    old = ep.status
    from sqlalchemy.sql import func as _func
    ep.status = req.status
    ep.closed_at = _func.now()
    log_audit(db, current_user["user_id"], "UPDATE", "PregnancyEpisode", ep.episode_id,
              {"status": old}, {"status": req.status, "reason": req.reason},
              request.client.host)
    db.commit()
    db.refresh(ep)
    return _episode_dict(db, ep)
```

- [ ] **Step 4: Run the tests**

Restart uvicorn, then: `python3 -m pytest tests/test_maternity_episodes.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/maternity.py backend/tests/test_maternity_episodes.py
git commit -m "feat(maternity): pregnancy episode endpoints — create, list, detail, close

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 5: ANC/PNC visits with billing side-effect

**Files:**
- Create: `backend/app/services/maternity_billing.py`
- Modify: `backend/app/routes/maternity.py` (add visit endpoints)
- Test: `backend/tests/test_maternity_visits.py`

**Interfaces:**
- Produces:
  - `raise_maternity_charge(db, *, patient_id, service_code, clinician_name, user_id) -> Optional[InvoiceItem]` — returns None when the code is missing, inactive, or zero-priced; otherwise appends to the patient's Pending invoice and GL-posts. Caller owns the commit.
  - `POST /api/maternity/episodes/{id}/anc-visits` body `{visit_date, bp_systolic?, bp_diastolic?, weight_kg?, fundal_height_cm?, fetal_heart_rate?, urine_dip?, notes?}` → visit dict. `visit_number` and `gestation_weeks` are computed server-side.
  - `POST /api/maternity/episodes/{id}/pnc-visits` body `{visit_date, newborn_id?, bp_systolic?, bp_diastolic?, involution?, lochia?, feeding?, cord_status?, baby_weight_g?, notes?}` → visit dict.
- Consumes: `PriceListItem` (Task 3 codes), `Invoice`/`InvoiceItem` from `app.models.billing`, `post_from_event` from `app.services.accounting_posting`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_maternity_visits.py`:

```python
"""ANC/PNC visit endpoints + billing side-effects."""
from __future__ import annotations

import uuid

import pytest
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


def _db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return sessionmaker(bind=create_engine(f"{base}/{TENANT}"))()


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/maternity/episodes")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


@pytest.fixture()
def episode(client, nurse_cookies, admin_cookies):
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Anc{suffix}", "other_names": "Visit Mother",
        "gender": "Female", "date_of_birth": "1995-01-15",
        "phone_number": f"+2547{suffix[:8]}", "id_type": "None",
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0, "lmp": "2026-02-10",
    })
    assert r.status_code == 200, r.text
    return {"patient_id": pid, "episode_id": r.json()["episode_id"]}


def _set_price(code: str, price: float):
    db = _db()
    try:
        db.execute(text("UPDATE acc_price_list SET unit_price = :p WHERE service_code = :c"),
                   {"p": price, "c": code})
        db.commit()
    finally:
        db.close()


class TestAncVisit:
    def test_visit_computes_number_and_gestation(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 0)
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies,
            json={"visit_date": "2026-07-08", "bp_systolic": 118, "bp_diastolic": 76},
        )
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["visit_number"] == 1
        # LMP 2026-02-10 → 2026-07-08 is 148 days ≈ 21 weeks
        assert v["gestation_weeks"] == 21

        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies, json={"visit_date": "2026-07-09"},
        )
        assert r.json()["visit_number"] == 2

    def test_priced_visit_raises_invoice_and_gl(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 500)
        try:
            r = client.post(
                f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
                cookies=nurse_cookies, json={"visit_date": "2026-07-10"},
            )
            assert r.status_code == 200, r.text
            db = _db()
            try:
                row = db.execute(text(
                    "SELECT ii.amount FROM invoice_items ii "
                    "JOIN invoices i ON i.invoice_id = ii.invoice_id "
                    "WHERE i.patient_id = :pid AND ii.item_type = 'Maternity' "
                    "ORDER BY ii.id DESC LIMIT 1"
                ), {"pid": episode["patient_id"]}).first()
                assert row is not None and float(row[0]) == 500.0
            finally:
                db.close()
        finally:
            _set_price("MAT-ANC-VISIT", 0)

    def test_zero_priced_visit_raises_no_charge(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 0)
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies, json={"visit_date": "2026-07-11"},
        )
        assert r.status_code == 200
        db = _db()
        try:
            n = db.execute(text(
                "SELECT COUNT(*) FROM invoice_items ii "
                "JOIN invoices i ON i.invoice_id = ii.invoice_id "
                "WHERE i.patient_id = :pid AND ii.item_type = 'Maternity'"
            ), {"pid": episode["patient_id"]}).scalar()
            assert n == 0
        finally:
            db.close()


class TestPncVisit:
    def test_pnc_visit_records(self, client, nurse_cookies, episode):
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/pnc-visits",
            cookies=nurse_cookies,
            json={"visit_date": "2026-07-12", "involution": "Well contracted",
                  "lochia": "Normal", "feeding": "Exclusive BF"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["visit_number"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_maternity_visits.py -v`
Expected: FAIL (404/405 — endpoints don't exist).

- [ ] **Step 3: Write the billing service**

`backend/app/services/maternity_billing.py`:

```python
"""Maternity charge helper — the consultation-fee pattern, parameterised.

Finds-or-creates the mother's Pending invoice under FOR UPDATE, appends a
Maternity line item, bumps the total, and GL-posts via post_from_event.
Zero-priced / missing / inactive service codes charge nothing (returns None).
The CALLER owns the commit — the charge lives or dies with the visit row.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.accounting import PriceListItem
from app.models.billing import Invoice, InvoiceItem
from app.services.accounting_posting import post_from_event


def raise_maternity_charge(
    db: Session,
    *,
    patient_id: int,
    service_code: str,
    clinician_name: str,
    user_id: int,
) -> Optional[InvoiceItem]:
    price = (
        db.query(PriceListItem)
        .filter(PriceListItem.service_code == service_code,
                PriceListItem.is_active == True)  # noqa: E712
        .first()
    )
    if not price or Decimal(price.unit_price or 0) <= 0:
        return None
    amt = Decimal(price.unit_price).quantize(Decimal("0.01"))

    invoice = (
        db.query(Invoice)
        .with_for_update()
        .filter(Invoice.patient_id == patient_id, Invoice.status == "Pending")
        .first()
    )
    if not invoice:
        invoice = Invoice(patient_id=patient_id, total_amount=Decimal(0),
                          status="Pending", created_by=user_id)
        db.add(invoice)
        db.flush()

    invoice.total_amount = (invoice.total_amount or Decimal(0)) + amt
    item = InvoiceItem(
        invoice_id=invoice.invoice_id,
        description=f"{price.name} — {clinician_name}"[:255],
        amount=amt,
        item_type="Maternity",
    )
    db.add(item)
    db.flush()

    post_from_event(
        db,
        source_key="billing.invoice.created",
        source_id=item.id,
        amount=amt,
        memo=f"{price.name} · Invoice #{invoice.invoice_id}",
        reference=f"INV-{invoice.invoice_id}",
        user_id=user_id,
    )
    return item
```

- [ ] **Step 4: Add the visit endpoints**

Append to `backend/app/routes/maternity.py` (imports at top: `from app.services.maternity_billing import raise_maternity_charge`):

```python
class AncVisitCreate(BaseModel):
    visit_date: date
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=300)
    fundal_height_cm: Optional[float] = Field(default=None, ge=4, le=60)
    fetal_heart_rate: Optional[int] = Field(default=None, ge=60, le=220)
    urine_dip: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = None


class PncVisitCreate(BaseModel):
    visit_date: date
    newborn_id: Optional[int] = None
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=300)
    involution: Optional[str] = Field(default=None, max_length=40)
    lochia: Optional[str] = Field(default=None, max_length=40)
    feeding: Optional[str] = Field(default=None, max_length=40)
    cord_status: Optional[str] = Field(default=None, max_length=40)
    baby_weight_g: Optional[int] = Field(default=None, ge=200, le=9000)
    urine_dip: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = None


@router.post("/episodes/{episode_id}/anc-visits", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_anc_visit(episode_id: int, req: AncVisitCreate, request: Request,
                     db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    ep = _get_episode_or_404(db, episode_id)
    if ep.status != "Active":
        raise HTTPException(status_code=400, detail=f"Episode is {ep.status}; ANC visits need an Active episode.")
    count = db.query(AncVisit).filter(AncVisit.episode_id == episode_id).count()
    gestation = None
    if ep.lmp:
        gestation = max(0, (req.visit_date - ep.lmp).days // 7)
    visit = AncVisit(
        episode_id=episode_id, visit_number=count + 1, visit_date=req.visit_date,
        gestation_weeks=gestation, bp_systolic=req.bp_systolic,
        bp_diastolic=req.bp_diastolic, weight_kg=req.weight_kg,
        fundal_height_cm=req.fundal_height_cm, fetal_heart_rate=req.fetal_heart_rate,
        urine_dip=req.urine_dip, notes=req.notes,
        recorded_by=current_user["user_id"],
    )
    db.add(visit)
    db.flush()
    raise_maternity_charge(
        db, patient_id=ep.patient_id, service_code="MAT-ANC-VISIT",
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "AncVisit", visit.visit_id,
              None, {"episode_id": episode_id, "visit_date": req.visit_date.isoformat()},
              request.client.host)
    db.commit()
    return {
        "visit_id": visit.visit_id, "visit_number": visit.visit_number,
        "visit_date": visit.visit_date.isoformat(),
        "gestation_weeks": visit.gestation_weeks,
    }


@router.post("/episodes/{episode_id}/pnc-visits", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_pnc_visit(episode_id: int, req: PncVisitCreate, request: Request,
                     db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    ep = _get_episode_or_404(db, episode_id)
    if req.newborn_id is not None:
        nb = db.query(NewbornRecord).filter(NewbornRecord.newborn_id == req.newborn_id).first()
        if not nb:
            raise HTTPException(status_code=404, detail="Newborn record not found")
    count = db.query(PncVisit).filter(PncVisit.episode_id == episode_id).count()
    visit = PncVisit(
        episode_id=episode_id, newborn_id=req.newborn_id,
        visit_number=count + 1, visit_date=req.visit_date,
        bp_systolic=req.bp_systolic, bp_diastolic=req.bp_diastolic,
        weight_kg=req.weight_kg, involution=req.involution, lochia=req.lochia,
        feeding=req.feeding, cord_status=req.cord_status,
        baby_weight_g=req.baby_weight_g, urine_dip=req.urine_dip,
        notes=req.notes, recorded_by=current_user["user_id"],
    )
    db.add(visit)
    db.flush()
    raise_maternity_charge(
        db, patient_id=ep.patient_id, service_code="MAT-PNC-VISIT",
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "PncVisit", visit.visit_id,
              None, {"episode_id": episode_id, "visit_date": req.visit_date.isoformat()},
              request.client.host)
    db.commit()
    return {
        "visit_id": visit.visit_id, "visit_number": visit.visit_number,
        "visit_date": visit.visit_date.isoformat(),
    }
```

- [ ] **Step 5: Run the tests**

Restart uvicorn, then: `python3 -m pytest tests/test_maternity_visits.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/maternity_billing.py backend/app/routes/maternity.py backend/tests/test_maternity_visits.py
git commit -m "feat(maternity): ANC/PNC visit endpoints with invoice + GL side-effects

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 6: Labor link + partograph (append-only) + alert notifications

**Files:**
- Create: `backend/app/routes/maternity_labor.py`
- Modify: `backend/app/main.py` (import + include_router, next to the Task 2 lines)
- Test: `backend/tests/test_maternity_partograph.py`

**Interfaces:**
- Produces:
  - `POST /api/maternity/episodes/{id}/labor` body `{admission_id, active_labor_started_at?}` → `{labor_admission_id, ...}`. 400 if the admission isn't Active or belongs to a different patient; 409 if already linked.
  - `POST /api/maternity/labor/{labor_admission_id}/partograph` body `{recorded_at?, cervical_dilation_cm?, descent_fifths?, contractions_per_10min?, contraction_duration_sec?, fetal_heart_rate?, liquor?, moulding?, maternal_bp_systolic?, maternal_bp_diastolic?, maternal_pulse?, temperature_c?, drugs_note?, corrects_entry_id?}` → entry dict incl. `alert_status` (`"ok" | "alert" | "action"`).
  - `GET /api/maternity/labor/{labor_admission_id}/partograph` → `{active_labor_started_at, entries: [entry dicts, superseded: bool]}`.
  - Pure helper `alert_status(dilation_cm, hours_since_active) -> str` exported for direct unit-testing.
- Consumes: `LaborAdmission`, `PartographEntry`, `PregnancyEpisode` (Task 1), `AdmissionRecord` from `app.models.wards`, `notify` + `users_with_permission` from `app.utils.notify`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_maternity_partograph.py`:

```python
"""Labor link + partograph: append-only entries, corrections, alert lines."""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/maternity/episodes")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def test_alert_status_math():
    from app.routes.maternity_labor import alert_status
    # On/left of the alert line (4cm + 1cm/hr) is ok.
    assert alert_status(6.0, 2.0) == "ok"      # expected >= 6 at 2h
    assert alert_status(5.0, 2.0) == "alert"   # below 6 at 2h → alert zone
    assert alert_status(4.0, 8.5) == "action"  # below 4 + (8.5-4) = 8.5 → past action line
    assert alert_status(None, 3.0) == "ok"     # nothing to judge


@pytest.fixture()
def labor(client, nurse_cookies, admin_cookies, doctor_cookies):
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Lab{suffix}", "other_names": "Partograph Mother",
        "gender": "Female", "date_of_birth": "1994-06-20",
        "phone_number": f"+2547{suffix[:8]}", "id_type": "None",
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0,
    })
    assert r.status_code == 200, r.text
    eid = r.json()["episode_id"]

    # Ward admission via the normal wards flow (needs a free bed; the seeded
    # tenant has wards + beds. Find one from the board.)
    board = client.get("/api/wards/board", cookies=nurse_cookies).json()
    bed_id = None
    for ward in board if isinstance(board, list) else board.get("wards", []):
        for bed in ward.get("beds", []):
            if bed.get("status") == "Available":
                bed_id = bed.get("bed_id")
                break
        if bed_id:
            break
    assert bed_id, "no free bed on the board — seed a bed first"
    r = client.post("/api/wards/admit", cookies=doctor_cookies, json={
        "patient_id": pid, "bed_id": bed_id, "primary_diagnosis": "Labor",
    })
    assert r.status_code in (200, 201), r.text
    admission_id = r.json().get("admission_id") or r.json().get("id")

    r = client.post(f"/api/maternity/episodes/{eid}/labor", cookies=nurse_cookies,
                    json={"admission_id": admission_id})
    assert r.status_code == 200, r.text
    return {"labor_admission_id": r.json()["labor_admission_id"],
            "episode_id": eid, "patient_id": pid, "admission_id": admission_id}


class TestPartograph:
    def test_append_list_and_correction_chain(self, client, nurse_cookies, labor):
        lid = labor["labor_admission_id"]
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 4.0, "fetal_heart_rate": 140})
        assert r.status_code == 200, r.text
        first = r.json()

        # First >=4cm entry sets time zero.
        r = client.get(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies)
        body = r.json()
        assert body["active_labor_started_at"] is not None
        assert len(body["entries"]) == 1

        # Correction supersedes the first entry.
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 5.0, "fetal_heart_rate": 138,
                              "corrects_entry_id": first["entry_id"]})
        assert r.status_code == 200
        body = client.get(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies).json()
        by_id = {e["entry_id"]: e for e in body["entries"]}
        assert by_id[first["entry_id"]]["superseded"] is True

    def test_no_update_or_delete_routes(self, client, nurse_cookies, labor):
        lid = labor["labor_admission_id"]
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 6.0})
        entry_id = r.json()["entry_id"]
        assert client.patch(f"/api/maternity/labor/{lid}/partograph/{entry_id}",
                            cookies=nurse_cookies, json={}).status_code in (404, 405)
        assert client.delete(f"/api/maternity/labor/{lid}/partograph/{entry_id}",
                             cookies=nurse_cookies).status_code in (404, 405)

    def test_double_link_409(self, client, nurse_cookies, labor):
        r = client.post(f"/api/maternity/episodes/{labor['episode_id']}/labor",
                        cookies=nurse_cookies,
                        json={"admission_id": labor["admission_id"]})
        assert r.status_code == 409
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_maternity_partograph.py -v`
Expected: FAIL (`ModuleNotFoundError` on the import test; 404s elsewhere).

- [ ] **Step 3: Implement**

`backend/app/routes/maternity_labor.py`:

```python
"""Labor admissions + append-only partograph.

Time zero (`active_labor_started_at`) anchors the WHO alert line: expected
dilation = 4 cm + 1 cm/hour. The action line runs 4 hours right of the alert
line. Entries plotting past a line notify ward staff (wards:manage holders).

Partograph rows are APPEND-ONLY by design: there are no update or delete
endpoints, and corrections are new rows pointing at the superseded row.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.maternity import LaborAdmission, PartographEntry, PregnancyEpisode
from app.models.patient import Patient
from app.models.wards import AdmissionRecord
from app.utils.audit import log_audit
from app.utils.notify import notify, users_with_permission

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])


def alert_status(dilation_cm: Optional[float], hours_since_active: Optional[float]) -> str:
    """WHO partograph zones. 'ok' left of the alert line, 'alert' between the
    lines, 'action' right of the action line (alert + 4h)."""
    if dilation_cm is None or hours_since_active is None or hours_since_active < 0:
        return "ok"
    expected_alert = 4.0 + hours_since_active
    expected_action = 4.0 + max(0.0, hours_since_active - 4.0)
    if dilation_cm >= expected_alert:
        return "ok"
    if dilation_cm >= expected_action:
        return "alert"
    return "action"


class LaborLink(BaseModel):
    admission_id: int
    active_labor_started_at: Optional[datetime] = None


class PartographCreate(BaseModel):
    recorded_at: Optional[datetime] = None
    cervical_dilation_cm: Optional[float] = Field(default=None, ge=0, le=10)
    descent_fifths: Optional[int] = Field(default=None, ge=0, le=5)
    contractions_per_10min: Optional[int] = Field(default=None, ge=0, le=10)
    contraction_duration_sec: Optional[int] = Field(default=None, ge=0, le=600)
    fetal_heart_rate: Optional[int] = Field(default=None, ge=40, le=240)
    liquor: Optional[str] = Field(default=None, max_length=4)
    moulding: Optional[str] = Field(default=None, max_length=4)
    maternal_bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    maternal_bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    maternal_pulse: Optional[int] = Field(default=None, ge=20, le=250)
    temperature_c: Optional[float] = Field(default=None, ge=30, le=45)
    drugs_note: Optional[str] = Field(default=None, max_length=255)
    corrects_entry_id: Optional[int] = None


def _entry_dict(e: PartographEntry, active_start: Optional[datetime]) -> dict:
    hours = None
    if active_start and e.recorded_at:
        hours = (e.recorded_at - active_start).total_seconds() / 3600.0
    return {
        "entry_id": e.entry_id,
        "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None,
        "hours_since_active": round(hours, 2) if hours is not None else None,
        "cervical_dilation_cm": float(e.cervical_dilation_cm) if e.cervical_dilation_cm is not None else None,
        "descent_fifths": e.descent_fifths,
        "contractions_per_10min": e.contractions_per_10min,
        "contraction_duration_sec": e.contraction_duration_sec,
        "fetal_heart_rate": e.fetal_heart_rate,
        "liquor": e.liquor,
        "moulding": e.moulding,
        "maternal_bp_systolic": e.maternal_bp_systolic,
        "maternal_bp_diastolic": e.maternal_bp_diastolic,
        "maternal_pulse": e.maternal_pulse,
        "temperature_c": float(e.temperature_c) if e.temperature_c is not None else None,
        "drugs_note": e.drugs_note,
        "corrects_entry_id": e.corrects_entry_id,
        "alert_status": alert_status(
            float(e.cervical_dilation_cm) if e.cervical_dilation_cm is not None else None,
            hours,
        ),
    }


@router.post("/episodes/{episode_id}/labor", dependencies=[Depends(RequirePermission("maternity:manage"))])
def link_labor(episode_id: int, req: LaborLink, request: Request,
               db: Session = Depends(get_db),
               current_user: dict = Depends(get_current_user)):
    ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Pregnancy episode not found")
    adm = db.query(AdmissionRecord).filter(AdmissionRecord.admission_id == req.admission_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="Admission not found")
    if adm.patient_id != ep.patient_id:
        raise HTTPException(status_code=400, detail="Admission belongs to a different patient")
    if adm.status != "Active":
        raise HTTPException(status_code=400, detail="Admission is not Active")
    if db.query(LaborAdmission).filter(LaborAdmission.admission_id == req.admission_id).first():
        raise HTTPException(status_code=409, detail="Admission is already linked to a labor record")

    la = LaborAdmission(episode_id=episode_id, admission_id=req.admission_id,
                        active_labor_started_at=req.active_labor_started_at)
    db.add(la)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "LaborAdmission", la.labor_admission_id,
              None, {"episode_id": episode_id, "admission_id": req.admission_id},
              request.client.host)
    db.commit()
    return {
        "labor_admission_id": la.labor_admission_id,
        "episode_id": episode_id,
        "admission_id": req.admission_id,
        "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
    }


def _get_labor_or_404(db: Session, labor_admission_id: int) -> LaborAdmission:
    la = db.query(LaborAdmission).filter(LaborAdmission.labor_admission_id == labor_admission_id).first()
    if not la:
        raise HTTPException(status_code=404, detail="Labor record not found")
    return la


@router.post("/labor/{labor_admission_id}/partograph", dependencies=[Depends(RequirePermission("maternity:manage"))])
def append_partograph_entry(labor_admission_id: int, req: PartographCreate, request: Request,
                            db: Session = Depends(get_db),
                            current_user: dict = Depends(get_current_user)):
    la = _get_labor_or_404(db, labor_admission_id)
    if req.corrects_entry_id is not None:
        target = (
            db.query(PartographEntry)
            .filter(PartographEntry.entry_id == req.corrects_entry_id,
                    PartographEntry.labor_admission_id == labor_admission_id)
            .first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="Entry to correct not found on this labor record")

    recorded_at = req.recorded_at or datetime.now(timezone.utc)
    entry = PartographEntry(
        labor_admission_id=labor_admission_id,
        recorded_at=recorded_at,
        cervical_dilation_cm=req.cervical_dilation_cm,
        descent_fifths=req.descent_fifths,
        contractions_per_10min=req.contractions_per_10min,
        contraction_duration_sec=req.contraction_duration_sec,
        fetal_heart_rate=req.fetal_heart_rate,
        liquor=req.liquor,
        moulding=req.moulding,
        maternal_bp_systolic=req.maternal_bp_systolic,
        maternal_bp_diastolic=req.maternal_bp_diastolic,
        maternal_pulse=req.maternal_pulse,
        temperature_c=req.temperature_c,
        drugs_note=req.drugs_note,
        corrects_entry_id=req.corrects_entry_id,
        recorded_by=current_user["user_id"],
    )
    db.add(entry)

    # First >= 4 cm observation anchors time zero.
    if (la.active_labor_started_at is None
            and req.cervical_dilation_cm is not None
            and req.cervical_dilation_cm >= 4.0):
        la.active_labor_started_at = recorded_at

    db.flush()

    hours = None
    if la.active_labor_started_at:
        hours = (recorded_at - la.active_labor_started_at).total_seconds() / 3600.0
    status = alert_status(req.cervical_dilation_cm, hours)
    if status in ("alert", "action"):
        ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == la.episode_id).first()
        patient = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first() if ep else None
        pname = f"{patient.surname}, {patient.other_names}" if patient else f"episode #{la.episode_id}"
        for uid in users_with_permission(db, "wards:manage", exclude_roles=("Admin",)):
            notify(
                db, user_id=uid, category="warning",
                title=f"Partograph {status}-line crossing — {pname}",
                body=f"Dilation {req.cervical_dilation_cm} cm at {round(hours or 0, 1)} h of active labor.",
                link="/app/maternity",
            )

    log_audit(db, current_user["user_id"], "CREATE", "PartographEntry", entry.entry_id,
              None, {"labor_admission_id": labor_admission_id, "alert_status": status},
              request.client.host)
    db.commit()
    return _entry_dict(entry, la.active_labor_started_at)


@router.get("/labor/{labor_admission_id}/partograph", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_partograph(labor_admission_id: int, db: Session = Depends(get_db)):
    la = _get_labor_or_404(db, labor_admission_id)
    entries = (
        db.query(PartographEntry)
        .filter(PartographEntry.labor_admission_id == labor_admission_id)
        .order_by(PartographEntry.recorded_at, PartographEntry.entry_id)
        .all()
    )
    superseded_ids = {e.corrects_entry_id for e in entries if e.corrects_entry_id}
    out = []
    for e in entries:
        d = _entry_dict(e, la.active_labor_started_at)
        d["superseded"] = e.entry_id in superseded_ids
        out.append(d)
    return {
        "labor_admission_id": labor_admission_id,
        "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
        "entries": out,
    }
```

Register in `backend/app/main.py`:

```python
import app.routes.maternity_labor as maternity_labor_module
...
app.include_router(maternity_labor_module.router)
```

- [ ] **Step 4: Run the tests**

Restart uvicorn, then: `python3 -m pytest tests/test_maternity_partograph.py -v`
Expected: all PASS. (If `/api/wards/board` shape differs from the fixture's assumption, adapt the fixture — read the actual response with `client.get("/api/wards/board").json()` and pick a free bed accordingly.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/maternity_labor.py backend/app/main.py backend/tests/test_maternity_partograph.py
git commit -m "feat(maternity): labor link + append-only partograph with alert-line notifications

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 7: Delivery, newborns, register-newborn-as-patient

**Files:**
- Modify: `backend/app/routes/maternity.py`
- Test: `backend/tests/test_maternity_delivery.py`

**Interfaces:**
- Produces:
  - `POST /api/maternity/episodes/{id}/delivery` body `{delivered_at, mode, labor_admission_id?, placenta_complete?, blood_loss_ml?, perineum?, complications?, mother_status?, newborns: [{birth_order?, sex, weight_g?, apgar_1?, apgar_5?, apgar_10?, outcome?, resuscitated?, notes?}]}` → delivery dict. Flips episode → Delivered; charges `MAT-DEL-{SVD|ASSISTED|CS|BREECH}`; 409 on a second delivery; 400 on invalid mode or empty newborns.
  - `POST /api/maternity/newborns/{newborn_id}/register-patient` → `{patient_id}`; creates a Patient linked via `registered_patient_id`; 409 if already registered; requires `maternity:manage` AND `patients:write`.
- Consumes: `raise_maternity_charge` (Task 5), episode helpers (Task 4).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_maternity_delivery.py`:

```python
"""Delivery + newborn endpoints."""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}

MODE_TO_CODE = {"SVD": "MAT-DEL-SVD", "Assisted": "MAT-DEL-ASSISTED",
                "CSection": "MAT-DEL-CS", "Breech": "MAT-DEL-BREECH"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/maternity/episodes")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


@pytest.fixture()
def episode(client, nurse_cookies, admin_cookies):
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Del{suffix}", "other_names": "Delivery Mother",
        "gender": "Female", "date_of_birth": "1993-09-09",
        "phone_number": f"+2547{suffix[:8]}", "id_type": "None",
    })
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0,
    })
    return {"patient_id": pid, "episode_id": r.json()["episode_id"]}


class TestDelivery:
    def test_delivery_flips_episode_and_stores_newborns(self, client, nurse_cookies, episode):
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T08:30:00Z",
                            "mode": "SVD",
                            "blood_loss_ml": 250,
                            "newborns": [
                                {"sex": "Female", "weight_g": 3200,
                                 "apgar_1": 8, "apgar_5": 9, "outcome": "Live"},
                            ],
                        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["newborns"]) == 1

        ep = client.get(f"/api/maternity/episodes/{episode['episode_id']}",
                        cookies=nurse_cookies).json()
        assert ep["status"] == "Delivered"

        # Second delivery on the same episode → 409
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T09:00:00Z",
                            "mode": "SVD", "newborns": [{"sex": "Male"}],
                        })
        assert r.status_code == 409

    def test_invalid_mode_400(self, client, nurse_cookies, episode):
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T08:30:00Z",
                            "mode": "Teleport", "newborns": [{"sex": "Male"}],
                        })
        assert r.status_code == 400

    def test_empty_newborns_400(self, client, nurse_cookies, episode):
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T08:30:00Z",
                            "mode": "SVD", "newborns": [],
                        })
        assert r.status_code == 400


class TestNewbornRegistration:
    def test_register_then_conflict(self, client, nurse_cookies, episode):
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T10:00:00Z",
                            "mode": "CSection",
                            "newborns": [{"sex": "Male", "weight_g": 2900}],
                        })
        newborn_id = r.json()["newborns"][0]["newborn_id"]

        r = client.post(f"/api/maternity/newborns/{newborn_id}/register-patient",
                        cookies=nurse_cookies)
        assert r.status_code == 200, r.text
        assert r.json()["patient_id"] > 0

        r = client.post(f"/api/maternity/newborns/{newborn_id}/register-patient",
                        cookies=nurse_cookies)
        assert r.status_code == 409
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_maternity_delivery.py -v`
Expected: FAIL (405/404).

- [ ] **Step 3: Implement**

Append to `backend/app/routes/maternity.py` (add `from datetime import datetime` to the existing date import line):

```python
VALID_DELIVERY_MODES = {"SVD": "MAT-DEL-SVD", "Assisted": "MAT-DEL-ASSISTED",
                        "CSection": "MAT-DEL-CS", "Breech": "MAT-DEL-BREECH"}
VALID_MOTHER_STATUS = {"Stable", "Referred", "Deceased"}
VALID_OUTCOME = {"Live", "FSB", "MSB"}


class NewbornCreate(BaseModel):
    birth_order: int = Field(1, ge=1, le=8)
    sex: str = Field(..., max_length=10)
    weight_g: Optional[int] = Field(default=None, ge=200, le=9000)
    apgar_1: Optional[int] = Field(default=None, ge=0, le=10)
    apgar_5: Optional[int] = Field(default=None, ge=0, le=10)
    apgar_10: Optional[int] = Field(default=None, ge=0, le=10)
    outcome: str = "Live"
    resuscitated: bool = False
    notes: Optional[str] = None


class DeliveryCreate(BaseModel):
    delivered_at: datetime
    mode: str
    labor_admission_id: Optional[int] = None
    placenta_complete: Optional[bool] = None
    blood_loss_ml: Optional[int] = Field(default=None, ge=0, le=10000)
    perineum: Optional[str] = Field(default=None, max_length=40)
    complications: Optional[str] = None
    mother_status: str = "Stable"
    newborns: List[NewbornCreate]


@router.post("/episodes/{episode_id}/delivery", dependencies=[Depends(RequirePermission("maternity:manage"))])
def record_delivery(episode_id: int, req: DeliveryCreate, request: Request,
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    if req.mode not in VALID_DELIVERY_MODES:
        raise HTTPException(status_code=400,
                            detail=f"mode must be one of {sorted(VALID_DELIVERY_MODES)}")
    if req.mother_status not in VALID_MOTHER_STATUS:
        raise HTTPException(status_code=400,
                            detail=f"mother_status must be one of {sorted(VALID_MOTHER_STATUS)}")
    if not req.newborns:
        raise HTTPException(status_code=400, detail="At least one newborn record is required")
    for nb in req.newborns:
        if nb.outcome not in VALID_OUTCOME:
            raise HTTPException(status_code=400,
                                detail=f"newborn outcome must be one of {sorted(VALID_OUTCOME)}")
    ep = _get_episode_or_404(db, episode_id)
    existing = db.query(DeliveryRecord).filter(DeliveryRecord.episode_id == episode_id).first()
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"Episode already has delivery #{existing.delivery_id}")
    if req.labor_admission_id is not None:
        la = (
            db.query(LaborAdmission)
            .filter(LaborAdmission.labor_admission_id == req.labor_admission_id,
                    LaborAdmission.episode_id == episode_id)
            .first()
        )
        if not la:
            raise HTTPException(status_code=404, detail="Labor record not found on this episode")

    delivery = DeliveryRecord(
        episode_id=episode_id, labor_admission_id=req.labor_admission_id,
        delivered_at=req.delivered_at, mode=req.mode,
        placenta_complete=req.placenta_complete, blood_loss_ml=req.blood_loss_ml,
        perineum=req.perineum, complications=req.complications,
        mother_status=req.mother_status, conducted_by=current_user["user_id"],
    )
    db.add(delivery)
    db.flush()
    newborn_rows = []
    for i, nb in enumerate(req.newborns, start=1):
        row = NewbornRecord(
            delivery_id=delivery.delivery_id,
            birth_order=nb.birth_order if nb.birth_order else i,
            sex=nb.sex, weight_g=nb.weight_g,
            apgar_1=nb.apgar_1, apgar_5=nb.apgar_5, apgar_10=nb.apgar_10,
            outcome=nb.outcome, resuscitated=nb.resuscitated, notes=nb.notes,
        )
        db.add(row)
        newborn_rows.append(row)
    ep.status = "Delivered"
    db.flush()

    raise_maternity_charge(
        db, patient_id=ep.patient_id,
        service_code=VALID_DELIVERY_MODES[req.mode],
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "DeliveryRecord", delivery.delivery_id,
              None, {"episode_id": episode_id, "mode": req.mode,
                     "newborns": len(newborn_rows)},
              request.client.host)
    db.commit()
    return {
        "delivery_id": delivery.delivery_id,
        "episode_id": episode_id,
        "mode": delivery.mode,
        "delivered_at": delivery.delivered_at.isoformat(),
        "newborns": [
            {"newborn_id": n.newborn_id, "birth_order": n.birth_order,
             "sex": n.sex, "outcome": n.outcome}
            for n in newborn_rows
        ],
    }


@router.post("/newborns/{newborn_id}/register-patient",
             dependencies=[Depends(RequirePermission("maternity:manage")),
                           Depends(RequirePermission("patients:write"))])
def register_newborn_as_patient(newborn_id: int, request: Request,
                                db: Session = Depends(get_db),
                                current_user: dict = Depends(get_current_user)):
    nb = db.query(NewbornRecord).filter(NewbornRecord.newborn_id == newborn_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Newborn record not found")
    if nb.registered_patient_id:
        raise HTTPException(status_code=409,
                            detail=f"Newborn is already registered as patient #{nb.registered_patient_id}")
    if nb.outcome != "Live":
        raise HTTPException(status_code=400, detail="Only live newborns can be registered as patients")

    delivery = db.query(DeliveryRecord).filter(DeliveryRecord.delivery_id == nb.delivery_id).first()
    ep = _get_episode_or_404(db, delivery.episode_id)
    mother = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first()
    if not mother:
        raise HTTPException(status_code=404, detail="Mother's patient record not found")

    # Reuse the canonical registration path so OP-number generation, blind
    # index, and audit behave exactly like front-desk registration.
    from app.routes.patients import create_patient_record  # see note below
    baby = create_patient_record(
        db,
        surname=mother.surname,
        other_names=f"Baby of {mother.other_names}".strip()[:100],
        gender=nb.sex,
        date_of_birth=delivery.delivered_at.date(),
        phone_number=mother.phone_number,
        id_type="None",
        next_of_kin_name=f"{mother.surname}, {mother.other_names}"[:100],
        next_of_kin_phone=mother.phone_number,
        created_by=current_user["user_id"],
    )
    nb.registered_patient_id = baby.patient_id
    log_audit(db, current_user["user_id"], "CREATE", "Patient", baby.patient_id,
              None, {"source": "newborn_registration", "newborn_id": newborn_id},
              request.client.host)
    db.commit()
    return {"patient_id": baby.patient_id}
```

**Implementation note (resolve during coding, not by skipping):** `create_patient_record` as a reusable function may not exist — patient creation logic likely lives inline in the `POST /api/patients/` handler with OP-number advisory locking and blind-index writes. If so, extract the core row-creation into a helper `create_patient_record(db, **fields) -> Patient` inside `app/routes/patients.py` and have both the existing handler and this endpoint call it. Do NOT duplicate OP-number/blind-index logic here.

- [ ] **Step 4: Run the tests**

Restart uvicorn, then: `python3 -m pytest tests/test_maternity_delivery.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the whole maternity backend suite**

Run: `python3 -m pytest tests/test_maternity_episodes.py tests/test_maternity_visits.py tests/test_maternity_partograph.py tests/test_maternity_delivery.py tests/test_maternity_seed.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/maternity.py backend/app/routes/patients.py backend/tests/test_maternity_delivery.py
git commit -m "feat(maternity): delivery + newborn records, one-click newborn patient registration

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 8: Labor board endpoint

**Files:**
- Modify: `backend/app/routes/maternity_labor.py`
- Test: `backend/tests/test_maternity_partograph.py` (extend)

**Interfaces:**
- Produces: `GET /api/maternity/board` → list of `{labor_admission_id, episode_id, patient_id, patient_name, admission_id, active_labor_started_at, latest: {recorded_at, cervical_dilation_cm, fetal_heart_rate, alert_status} | null}` for labors on Active admissions without a delivery yet. Batched lookups (no N+1).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_maternity_partograph.py`:

```python
class TestLaborBoard:
    def test_board_lists_active_labor_with_latest_entry(self, client, nurse_cookies, labor):
        lid = labor["labor_admission_id"]
        client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                    json={"cervical_dilation_cm": 7.0, "fetal_heart_rate": 142})
        r = client.get("/api/maternity/board", cookies=nurse_cookies)
        assert r.status_code == 200
        rows = [x for x in r.json() if x["labor_admission_id"] == lid]
        assert rows, "labor not on the board"
        assert rows[0]["latest"]["cervical_dilation_cm"] == 7.0
        assert rows[0]["patient_name"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_maternity_partograph.py::TestLaborBoard -v`
Expected: FAIL 404.

- [ ] **Step 3: Implement**

Append to `backend/app/routes/maternity_labor.py`:

```python
@router.get("/board", dependencies=[Depends(RequirePermission("maternity:read"))])
def labor_board(db: Session = Depends(get_db)):
    from app.models.maternity import DeliveryRecord

    rows = (
        db.query(LaborAdmission, PregnancyEpisode, AdmissionRecord)
        .join(PregnancyEpisode, PregnancyEpisode.episode_id == LaborAdmission.episode_id)
        .join(AdmissionRecord, AdmissionRecord.admission_id == LaborAdmission.admission_id)
        .filter(AdmissionRecord.status == "Active")
        .all()
    )
    if not rows:
        return []

    episode_ids = [ep.episode_id for _, ep, _ in rows]
    delivered = {
        eid for (eid,) in db.query(DeliveryRecord.episode_id)
        .filter(DeliveryRecord.episode_id.in_(episode_ids)).all()
    }
    patient_ids = [ep.patient_id for _, ep, _ in rows]
    patients = {
        p.patient_id: p for p in
        db.query(Patient).filter(Patient.patient_id.in_(patient_ids)).all()
    }
    labor_ids = [la.labor_admission_id for la, _, _ in rows]
    latest_by_labor = {}
    for e in (
        db.query(PartographEntry)
        .filter(PartographEntry.labor_admission_id.in_(labor_ids))
        .order_by(PartographEntry.labor_admission_id,
                  PartographEntry.recorded_at.desc(),
                  PartographEntry.entry_id.desc())
        .all()
    ):
        latest_by_labor.setdefault(e.labor_admission_id, e)

    out = []
    for la, ep, adm in rows:
        if ep.episode_id in delivered:
            continue
        p = patients.get(ep.patient_id)
        latest = latest_by_labor.get(la.labor_admission_id)
        latest_dict = None
        if latest:
            d = _entry_dict(latest, la.active_labor_started_at)
            latest_dict = {
                "recorded_at": d["recorded_at"],
                "cervical_dilation_cm": d["cervical_dilation_cm"],
                "fetal_heart_rate": d["fetal_heart_rate"],
                "alert_status": d["alert_status"],
            }
        out.append({
            "labor_admission_id": la.labor_admission_id,
            "episode_id": ep.episode_id,
            "patient_id": ep.patient_id,
            "patient_name": f"{p.surname}, {p.other_names}" if p else None,
            "admission_id": adm.admission_id,
            "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
            "latest": latest_dict,
        })
    return out
```

- [ ] **Step 4: Run the tests**

Restart uvicorn, then: `python3 -m pytest tests/test_maternity_partograph.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/maternity_labor.py backend/tests/test_maternity_partograph.py
git commit -m "feat(maternity): labor board endpoint with latest partograph vitals

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 9: Frontend scaffold — route, nav, page shell, API helpers

**Files:**
- Create: `frontend/src/pages/Maternity.jsx`
- Create: `frontend/src/pages/maternity/api.js`
- Modify: `frontend/src/App.jsx` (lazy import + route, next to the accounting route ~line 226)
- Modify: `frontend/src/components/layouts/MainLayout.jsx` (nav entry after Wards, ~line 63)

**Interfaces:**
- Produces: route `/app/maternity` guarded by `ModuleGuard moduleKey="maternity"`; `api.js` exporting `listEpisodes`, `createEpisode`, `getEpisode`, `closeEpisode`, `createAncVisit`, `createPncVisit`, `linkLabor`, `appendPartograph`, `getPartograph`, `recordDelivery`, `registerNewborn`, `getLaborBoard` — all returning parsed JSON via the shared `client` from `src/api/client.js`.
- Consumes: backend endpoints from Tasks 4–8.

- [ ] **Step 1: Write the API helper**

`frontend/src/pages/maternity/api.js`:

```javascript
import client from '../../api/client';

export const listEpisodes = (params = {}) =>
  client.get('/api/maternity/episodes', { params }).then((r) => r.data);
export const createEpisode = (payload) =>
  client.post('/api/maternity/episodes', payload).then((r) => r.data);
export const getEpisode = (episodeId) =>
  client.get(`/api/maternity/episodes/${episodeId}`).then((r) => r.data);
export const closeEpisode = (episodeId, payload) =>
  client.patch(`/api/maternity/episodes/${episodeId}/close`, payload).then((r) => r.data);
export const createAncVisit = (episodeId, payload) =>
  client.post(`/api/maternity/episodes/${episodeId}/anc-visits`, payload).then((r) => r.data);
export const createPncVisit = (episodeId, payload) =>
  client.post(`/api/maternity/episodes/${episodeId}/pnc-visits`, payload).then((r) => r.data);
export const linkLabor = (episodeId, payload) =>
  client.post(`/api/maternity/episodes/${episodeId}/labor`, payload).then((r) => r.data);
export const appendPartograph = (laborId, payload) =>
  client.post(`/api/maternity/labor/${laborId}/partograph`, payload).then((r) => r.data);
export const getPartograph = (laborId) =>
  client.get(`/api/maternity/labor/${laborId}/partograph`).then((r) => r.data);
export const recordDelivery = (episodeId, payload) =>
  client.post(`/api/maternity/episodes/${episodeId}/delivery`, payload).then((r) => r.data);
export const registerNewborn = (newbornId) =>
  client.post(`/api/maternity/newborns/${newbornId}/register-patient`).then((r) => r.data);
export const getLaborBoard = () =>
  client.get('/api/maternity/board').then((r) => r.data);
export const getMaternityQueue = () =>
  client.get('/api/queue/', { params: { department: 'Maternity' } }).then((r) => r.data);
```

(Confirm `src/api/client.js`'s export shape first — if it exports a named axios instance or wrapper functions, match its idiom; every existing page imports from it.)

- [ ] **Step 2: Write the page shell**

`frontend/src/pages/Maternity.jsx`:

```jsx
import { useState } from 'react';
import AncClinicTab from './maternity/AncClinicTab';
import LaborBoardTab from './maternity/LaborBoardTab';
import DeliveriesTab from './maternity/DeliveriesTab';

const TABS = [
  { key: 'anc', label: 'ANC Clinic' },
  { key: 'labor', label: 'Labor Board' },
  { key: 'deliveries', label: 'Deliveries & PNC' },
];

export default function Maternity() {
  const [tab, setTab] = useState('anc');
  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Maternity</h1>
      <div className="mt-4 flex gap-2 border-b border-gray-200 dark:border-gray-700" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-md ${
              tab === t.key
                ? 'bg-white dark:bg-gray-800 border border-b-0 border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === 'anc' && <AncClinicTab />}
        {tab === 'labor' && <LaborBoardTab />}
        {tab === 'deliveries' && <DeliveriesTab />}
      </div>
    </div>
  );
}
```

Create placeholder tab components so the build passes (each replaced in Tasks 10–12). Example `frontend/src/pages/maternity/AncClinicTab.jsx` (same shape for `LaborBoardTab.jsx`, `DeliveriesTab.jsx` with their names):

```jsx
export default function AncClinicTab() {
  return <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>;
}
```

- [ ] **Step 3: Wire route and nav**

In `frontend/src/App.jsx`, add with the other lazy page imports:

```jsx
const Maternity = lazy(() => import('./pages/Maternity'));
```

(match the file's existing import style — if pages are imported eagerly, import eagerly) and after the accounting route:

```jsx
<Route path="maternity" element={<ModuleGuard moduleKey="maternity"><Maternity /></ModuleGuard>} />
```

In `frontend/src/components/layouts/MainLayout.jsx`, after the Wards entry add (import `Baby` from `lucide-react` in the existing icon import):

```jsx
    { name: 'Maternity',         path: '/app/maternity',       icon: <Baby size={18} />,            allowedRoles: ['Admin', 'Nurse', 'Doctor'],                       requiredPermission: 'maternity:read',   moduleKey: 'maternity' },
```

- [ ] **Step 4: Verify build + lint**

```bash
cd frontend && npx eslint src/pages/Maternity.jsx src/pages/maternity/ src/App.jsx src/components/layouts/MainLayout.jsx && npm run build
```
Expected: no lint errors, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Maternity.jsx frontend/src/pages/maternity/ frontend/src/App.jsx frontend/src/components/layouts/MainLayout.jsx
git commit -m "feat(maternity): page scaffold, module-guarded route, nav entry, API client

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 10: ANC Clinic tab

**Files:**
- Replace: `frontend/src/pages/maternity/AncClinicTab.jsx`
- Create: `frontend/src/pages/maternity/EpisodeForm.jsx`
- Create: `frontend/src/pages/maternity/AncVisitForm.jsx`
- Test: `frontend/src/pages/maternity/AncClinicTab.test.jsx`

**Interfaces:**
- Consumes: `listEpisodes`, `createEpisode`, `getEpisode`, `createAncVisit` from `./api`.
- Produces: `<AncClinicTab />` — episode list with status filter, enroll form (patient_id + gravida/para/LMP), episode detail with ANC visit history + "New visit" form.

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/maternity/AncClinicTab.test.jsx`:

```jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AncClinicTab from './AncClinicTab';
import * as api from './api';

vi.mock('./api');

describe('AncClinicTab', () => {
  beforeEach(() => {
    api.listEpisodes.mockResolvedValue([
      { episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1,
        edd: '2026-12-06', status: 'Active' },
    ]);
  });

  it('lists active episodes', async () => {
    render(<AncClinicTab />);
    expect(await screen.findByText(/Wanjiku, Grace/)).toBeInTheDocument();
    expect(screen.getByText(/G2 P1/)).toBeInTheDocument();
  });

  it('submits an ANC visit for the selected episode', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1,
      status: 'Active', anc_visits: [], pnc_visits: [], deliveries: [], labor: [],
    });
    api.createAncVisit.mockResolvedValue({ visit_id: 9, visit_number: 1 });
    const user = userEvent.setup();
    render(<AncClinicTab />);
    await user.click(await screen.findByText(/Wanjiku, Grace/));
    await user.click(await screen.findByRole('button', { name: /new anc visit/i }));
    await user.type(screen.getByLabelText(/visit date/i), '2026-07-10');
    await user.click(screen.getByRole('button', { name: /save visit/i }));
    await waitFor(() => expect(api.createAncVisit).toHaveBeenCalledWith(1,
      expect.objectContaining({ visit_date: '2026-07-10' })));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/maternity/AncClinicTab.test.jsx`
Expected: FAIL (placeholder renders "Loading…" only).

- [ ] **Step 3: Implement the tab**

`frontend/src/pages/maternity/AncClinicTab.jsx` — episode list + detail panel. Keep under 250 lines by delegating forms:

```jsx
import { useCallback, useEffect, useState } from 'react';
import { listEpisodes, getEpisode } from './api';
import EpisodeForm from './EpisodeForm';
import AncVisitForm from './AncVisitForm';

export default function AncClinicTab() {
  const [episodes, setEpisodes] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showEnroll, setShowEnroll] = useState(false);
  const [showVisit, setShowVisit] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    listEpisodes({ status: 'Active' }).then(setEpisodes).catch(() => setError('Failed to load episodes'));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const openEpisode = (id) =>
    getEpisode(id).then(setSelected).catch(() => setError('Failed to load episode'));

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section aria-label="Active pregnancies" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium text-gray-900 dark:text-gray-100">Active pregnancies</h2>
          <button onClick={() => setShowEnroll(true)}
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700">
            Enroll patient
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
        <ul className="mt-3 divide-y divide-gray-100 dark:divide-gray-700">
          {episodes.map((ep) => (
            <li key={ep.episode_id}>
              <button onClick={() => openEpisode(ep.episode_id)}
                      className="w-full py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded px-2">
                <span className="font-medium text-gray-900 dark:text-gray-100">{ep.patient_name}</span>
                <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">
                  G{ep.gravida} P{ep.para}{ep.edd ? ` · EDD ${ep.edd}` : ''}
                </span>
              </button>
            </li>
          ))}
          {episodes.length === 0 && (
            <li className="py-2 text-sm text-gray-500 dark:text-gray-400">No active pregnancies.</li>
          )}
        </ul>
      </section>

      <section aria-label="Episode detail" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        {!selected ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Select an episode to view visits.</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-gray-900 dark:text-gray-100">{selected.patient_name}</h2>
              <button onClick={() => setShowVisit(true)}
                      className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700">
                New ANC visit
              </button>
            </div>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="py-1 pr-2">#</th><th className="py-1 pr-2">Date</th>
                  <th className="py-1 pr-2">GA (wk)</th><th className="py-1 pr-2">BP</th>
                  <th className="py-1">FHR</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-gray-100">
                {selected.anc_visits.map((v) => (
                  <tr key={v.visit_id} className="border-t border-gray-100 dark:border-gray-700">
                    <td className="py-1 pr-2">{v.visit_number}</td>
                    <td className="py-1 pr-2">{v.visit_date}</td>
                    <td className="py-1 pr-2">{v.gestation_weeks ?? '—'}</td>
                    <td className="py-1 pr-2">{v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic}` : '—'}</td>
                    <td className="py-1">{v.fetal_heart_rate ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {showEnroll && (
        <EpisodeForm onClose={() => setShowEnroll(false)}
                     onSaved={() => { setShowEnroll(false); refresh(); }} />
      )}
      {showVisit && selected && (
        <AncVisitForm episodeId={selected.episode_id}
                      onClose={() => setShowVisit(false)}
                      onSaved={() => { setShowVisit(false); openEpisode(selected.episode_id); }} />
      )}
    </div>
  );
}
```

`frontend/src/pages/maternity/AncVisitForm.jsx`:

```jsx
import { useState } from 'react';
import { createAncVisit } from './api';

export default function AncVisitForm({ episodeId, onClose, onSaved }) {
  const [form, setForm] = useState({ visit_date: '', bp_systolic: '', bp_diastolic: '',
    weight_kg: '', fundal_height_cm: '', fetal_heart_rate: '', urine_dip: '', notes: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.visit_date) { setError('Visit date is required'); return; }
    setSaving(true);
    setError('');
    const payload = { visit_date: form.visit_date };
    for (const k of ['bp_systolic', 'bp_diastolic', 'fetal_heart_rate']) {
      if (form[k] !== '') payload[k] = Number(form[k]);
    }
    for (const k of ['weight_kg', 'fundal_height_cm']) {
      if (form[k] !== '') payload[k] = Number(form[k]);
    }
    for (const k of ['urine_dip', 'notes']) {
      if (form[k]) payload[k] = form[k];
    }
    try {
      await createAncVisit(episodeId, payload);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save visit');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="New ANC visit">
      <form onSubmit={submit} className="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 p-5 shadow-xl">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">New ANC visit</h3>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
        <label className="mt-3 block text-sm text-gray-700 dark:text-gray-300">
          Visit date
          <input type="date" value={form.visit_date} onChange={set('visit_date')} required
                 className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
        </label>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            BP systolic
            <input type="number" value={form.bp_systolic} onChange={set('bp_systolic')}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            BP diastolic
            <input type="number" value={form.bp_diastolic} onChange={set('bp_diastolic')}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            Weight (kg)
            <input type="number" step="0.1" value={form.weight_kg} onChange={set('weight_kg')}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            Fundal height (cm)
            <input type="number" step="0.1" value={form.fundal_height_cm} onChange={set('fundal_height_cm')}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            Fetal heart rate
            <input type="number" value={form.fetal_heart_rate} onChange={set('fetal_heart_rate')}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
          <label className="block text-sm text-gray-700 dark:text-gray-300">
            Urine dip
            <input type="text" value={form.urine_dip} onChange={set('urine_dip')} maxLength={40}
                   className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
          </label>
        </div>
        <label className="mt-3 block text-sm text-gray-700 dark:text-gray-300">
          Notes
          <textarea value={form.notes} onChange={set('notes')} rows={2}
                    className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-2 py-1.5 text-gray-900 dark:text-gray-100" />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose}
                  className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300">
            Cancel
          </button>
          <button type="submit" disabled={saving}
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save visit'}
          </button>
        </div>
      </form>
    </div>
  );
}
```

`frontend/src/pages/maternity/EpisodeForm.jsx` — same modal pattern with fields `patient_id` (number input; the worklist usually supplies it), `gravida`, `para`, `lmp` (date), `blood_group`, `rhesus`, `risk_flags`; submits via `createEpisode` and surfaces `err?.response?.data?.detail` (the 409 duplicate-episode message) in the error slot. Follow the AncVisitForm structure exactly.

Also add the routed-patient worklist above the episode list in `AncClinicTab.jsx` (spec: "routed-patient worklist (unified queue pattern)") — import `getMaternityQueue` from `./api`, load it in the same `refresh` callback, and render:

```jsx
{queue.length > 0 && (
  <div className="mb-3 rounded-md bg-blue-50 dark:bg-blue-900/20 p-3">
    <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300">Routed to Maternity</h3>
    <ul className="mt-1 space-y-1">
      {queue.map((q) => (
        <li key={q.queue_id} className="flex items-center justify-between text-sm text-gray-900 dark:text-gray-100">
          <span>{q.patient_name}</span>
          <button onClick={() => setShowEnroll({ patientId: q.patient_id })}
                  className="text-blue-600 dark:text-blue-400 hover:underline">
            Enroll / open
          </button>
        </li>
      ))}
    </ul>
  </div>
)}
```

(`setShowEnroll` carries the patient_id so `EpisodeForm` prefills it; adjust the existing boolean state to hold `false | {patientId?}`.)

- [ ] **Step 4: Run tests + lint**

```bash
cd frontend && npx vitest run src/pages/maternity/AncClinicTab.test.jsx && npx eslint src/pages/maternity/
```
Expected: tests PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/maternity/
git commit -m "feat(maternity): ANC clinic tab — episode list, enrollment, visit capture

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 11: Labor board + partograph SVG chart

**Files:**
- Replace: `frontend/src/pages/maternity/LaborBoardTab.jsx`
- Create: `frontend/src/pages/maternity/PartographChart.jsx`
- Create: `frontend/src/pages/maternity/PartographEntryForm.jsx`
- Test: `frontend/src/pages/maternity/PartographChart.test.jsx`

**Interfaces:**
- Produces:
  - `PartographChart.jsx` default export `<PartographChart entries={...} activeStart={...} />` plus **named pure exports** `xForHours(hours)`, `yForDilation(cm)`, `alertLinePoints()`, `actionLinePoints()` for unit tests. Chart geometry: viewBox `0 0 720 420`; plot area x∈[60,700], y∈[40,300]; X spans 0–12 h (60 px/h ⇒ `xForHours(h) = 60 + h * (640/12)`); Y spans dilation 0–10 cm inverted (`yForDilation(cm) = 300 - cm * 26`).
  - `<LaborBoardTab />` — board list from `getLaborBoard()`, per-labor detail with chart + `PartographEntryForm` appending via `appendPartograph`.
- Consumes: `getLaborBoard`, `getPartograph`, `appendPartograph` from `./api`.

- [ ] **Step 1: Write the failing chart-math test**

`frontend/src/pages/maternity/PartographChart.test.jsx`:

```jsx
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import PartographChart, { xForHours, yForDilation, alertLinePoints, actionLinePoints } from './PartographChart';

describe('partograph geometry', () => {
  it('maps hours to x linearly across the 12h plot', () => {
    expect(xForHours(0)).toBe(60);
    expect(xForHours(12)).toBe(700);
    expect(xForHours(6)).toBeCloseTo(380);
  });

  it('maps dilation to inverted y', () => {
    expect(yForDilation(0)).toBe(300);
    expect(yForDilation(10)).toBe(40);
  });

  it('alert line runs from 4cm@0h to 10cm@6h; action line is +4h parallel', () => {
    const alert = alertLinePoints();
    expect(alert.x1).toBe(xForHours(0));
    expect(alert.y1).toBe(yForDilation(4));
    expect(alert.x2).toBe(xForHours(6));
    expect(alert.y2).toBe(yForDilation(10));
    const action = actionLinePoints();
    expect(action.x1).toBe(xForHours(4));
    expect(action.y1).toBe(yForDilation(4));
    expect(action.x2).toBe(xForHours(10));
    expect(action.y2).toBe(yForDilation(10));
  });

  it('renders superseded points hollow', () => {
    const activeStart = '2026-07-10T06:00:00Z';
    const entries = [
      { entry_id: 1, recorded_at: '2026-07-10T07:00:00Z', cervical_dilation_cm: 5, superseded: true },
      { entry_id: 2, recorded_at: '2026-07-10T07:00:00Z', cervical_dilation_cm: 6, superseded: false },
    ];
    const { container } = render(<PartographChart entries={entries} activeStart={activeStart} />);
    const points = container.querySelectorAll('circle[data-kind="dilation"]');
    expect(points).toHaveLength(2);
    expect(points[0].getAttribute('fill')).toBe('none');
    expect(points[1].getAttribute('fill')).not.toBe('none');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/maternity/PartographChart.test.jsx`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement the chart**

`frontend/src/pages/maternity/PartographChart.jsx`:

```jsx
// Custom SVG partograph — no chart library, consistent with the bundle-size
// budget. Geometry is exported pure so tests can pin the WHO line positions.
const PLOT = { x0: 60, x1: 700, y0: 40, y1: 300, hours: 12, maxCm: 10 };

export const xForHours = (h) => PLOT.x0 + h * ((PLOT.x1 - PLOT.x0) / PLOT.hours);
export const yForDilation = (cm) => PLOT.y1 - cm * ((PLOT.y1 - PLOT.y0) / PLOT.maxCm);
export const alertLinePoints = () => ({
  x1: xForHours(0), y1: yForDilation(4), x2: xForHours(6), y2: yForDilation(10),
});
export const actionLinePoints = () => ({
  x1: xForHours(4), y1: yForDilation(4), x2: xForHours(10), y2: yForDilation(10),
});

const hoursSince = (iso, startIso) =>
  (new Date(iso).getTime() - new Date(startIso).getTime()) / 3600000;

export default function PartographChart({ entries = [], activeStart = null }) {
  const alert = alertLinePoints();
  const action = actionLinePoints();
  const plotted = activeStart
    ? entries
        .filter((e) => e.cervical_dilation_cm != null)
        .map((e) => ({ ...e, h: hoursSince(e.recorded_at, activeStart) }))
        .filter((e) => e.h >= 0 && e.h <= PLOT.hours)
    : [];
  const current = plotted.filter((e) => !e.superseded);
  const fhr = activeStart
    ? entries
        .filter((e) => e.fetal_heart_rate != null && !e.superseded)
        .map((e) => ({ ...e, h: hoursSince(e.recorded_at, activeStart) }))
        .filter((e) => e.h >= 0 && e.h <= PLOT.hours)
    : [];

  return (
    <svg viewBox="0 0 720 420" role="img" aria-label="Partograph chart"
         className="w-full rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      {/* grid */}
      {Array.from({ length: PLOT.hours + 1 }, (_, h) => (
        <g key={`gx${h}`}>
          <line x1={xForHours(h)} y1={PLOT.y0} x2={xForHours(h)} y2={PLOT.y1}
                stroke="currentColor" className="text-gray-200 dark:text-gray-700" strokeWidth="0.5" />
          <text x={xForHours(h)} y={PLOT.y1 + 16} textAnchor="middle"
                className="fill-gray-500 dark:fill-gray-400" fontSize="10">{h}h</text>
        </g>
      ))}
      {Array.from({ length: PLOT.maxCm + 1 }, (_, cm) => (
        <g key={`gy${cm}`}>
          <line x1={PLOT.x0} y1={yForDilation(cm)} x2={PLOT.x1} y2={yForDilation(cm)}
                stroke="currentColor" className="text-gray-200 dark:text-gray-700" strokeWidth="0.5" />
          <text x={PLOT.x0 - 8} y={yForDilation(cm) + 3} textAnchor="end"
                className="fill-gray-500 dark:fill-gray-400" fontSize="10">{cm}</text>
        </g>
      ))}

      {/* WHO alert + action lines */}
      <line {...alert} stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="6 3" />
      <text x={alert.x2 + 4} y={alert.y2 + 4} fontSize="10" fill="#f59e0b">Alert</text>
      <line {...action} stroke="#dc2626" strokeWidth="1.5" strokeDasharray="6 3" />
      <text x={action.x2 + 4} y={action.y2 + 4} fontSize="10" fill="#dc2626">Action</text>

      {/* dilation curve (current entries only) */}
      {current.length > 1 && (
        <polyline
          points={current
            .sort((a, b) => a.h - b.h)
            .map((e) => `${xForHours(e.h)},${yForDilation(e.cervical_dilation_cm)}`)
            .join(' ')}
          fill="none" stroke="#2563eb" strokeWidth="2"
        />
      )}
      {plotted.map((e) => (
        <circle key={e.entry_id} data-kind="dilation"
                cx={xForHours(e.h)} cy={yForDilation(e.cervical_dilation_cm)} r="4"
                fill={e.superseded ? 'none' : '#2563eb'}
                stroke="#2563eb" strokeWidth="1.5" />
      ))}

      {/* FHR strip (320–400 y-band, 60–200 bpm) */}
      <text x={PLOT.x0} y={334} fontSize="10" className="fill-gray-500 dark:fill-gray-400">FHR</text>
      {fhr.map((e) => {
        const y = 400 - ((e.fetal_heart_rate - 60) / 140) * 60;
        return <circle key={`fhr${e.entry_id}`} data-kind="fhr"
                       cx={xForHours(e.h)} cy={y} r="3" fill="#16a34a" />;
      })}
      {!activeStart && (
        <text x="380" y="180" textAnchor="middle" fontSize="12"
              className="fill-gray-500 dark:fill-gray-400">
          Active labor not started — chart begins at the first ≥4 cm entry.
        </text>
      )}
    </svg>
  );
}
```

- [ ] **Step 4: Implement the board tab + entry form**

`frontend/src/pages/maternity/LaborBoardTab.jsx`:

```jsx
import { useCallback, useEffect, useState } from 'react';
import { getLaborBoard, getPartograph } from './api';
import PartographChart from './PartographChart';
import PartographEntryForm from './PartographEntryForm';

const ALERT_BADGE = {
  ok: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  alert: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  action: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
};

export default function LaborBoardTab() {
  const [board, setBoard] = useState([]);
  const [selected, setSelected] = useState(null);
  const [chart, setChart] = useState(null);
  const [showEntry, setShowEntry] = useState(false);
  const [error, setError] = useState('');

  const refreshBoard = useCallback(() => {
    getLaborBoard().then(setBoard).catch(() => setError('Failed to load labor board'));
  }, []);
  useEffect(() => { refreshBoard(); }, [refreshBoard]);

  const open = useCallback((row) => {
    setSelected(row);
    getPartograph(row.labor_admission_id).then(setChart).catch(() => setError('Failed to load partograph'));
  }, []);

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <section aria-label="Labor board" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <h2 className="font-medium text-gray-900 dark:text-gray-100">In labor</h2>
        <ul className="mt-3 divide-y divide-gray-100 dark:divide-gray-700">
          {board.map((row) => (
            <li key={row.labor_admission_id}>
              <button onClick={() => open(row)}
                      className="flex w-full items-center justify-between py-2 px-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded">
                <span className="font-medium text-gray-900 dark:text-gray-100">{row.patient_name}</span>
                {row.latest && (
                  <span className={`rounded-full px-2 py-0.5 text-xs ${ALERT_BADGE[row.latest.alert_status] || ALERT_BADGE.ok}`}>
                    {row.latest.cervical_dilation_cm ?? '—'} cm · FHR {row.latest.fetal_heart_rate ?? '—'}
                  </span>
                )}
              </button>
            </li>
          ))}
          {board.length === 0 && (
            <li className="py-2 text-sm text-gray-500 dark:text-gray-400">No patients in labor.</li>
          )}
        </ul>
      </section>

      {selected && chart && (
        <section aria-label="Partograph" className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-medium text-gray-900 dark:text-gray-100">
              Partograph — {selected.patient_name}
            </h2>
            <button onClick={() => setShowEntry(true)}
                    className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700">
              New entry
            </button>
          </div>
          <div className="mt-3 overflow-x-auto">
            <PartographChart entries={chart.entries} activeStart={chart.active_labor_started_at} />
          </div>
        </section>
      )}

      {showEntry && selected && (
        <PartographEntryForm
          laborId={selected.labor_admission_id}
          onClose={() => setShowEntry(false)}
          onSaved={() => { setShowEntry(false); open(selected); refreshBoard(); }}
        />
      )}
    </div>
  );
}
```

Add a print action next to "New entry" in `LaborBoardTab.jsx` (spec: print view reuses the referral-letter print pattern — check how the referral letter triggers printing in `ClinicalDesk`'s referral modal and use the same idiom; the minimal version is a `Print` button calling `window.print()` with a `print:`-scoped stylesheet that hides everything but the chart section):

```jsx
<button onClick={() => window.print()}
        className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 print:hidden">
  Print
</button>
```

and add `print:block` / `print:hidden` Tailwind classes so only the partograph `<section>` renders when printing (match the referral-letter print CSS if it uses a dedicated print container instead).

`frontend/src/pages/maternity/PartographEntryForm.jsx` — modal form mirroring `AncVisitForm.jsx` exactly (same overlay/labels/buttons) with numeric fields `cervical_dilation_cm`, `descent_fifths`, `contractions_per_10min`, `contraction_duration_sec`, `fetal_heart_rate`, `maternal_bp_systolic`, `maternal_bp_diastolic`, `maternal_pulse`, `temperature_c`, text fields `liquor`, `moulding`, `drugs_note`; empty strings omitted from the payload, numbers coerced with `Number(...)`; submits `appendPartograph(laborId, payload)`; surfaces `err?.response?.data?.detail` on failure.

- [ ] **Step 5: Run tests + lint**

```bash
cd frontend && npx vitest run src/pages/maternity/ && npx eslint src/pages/maternity/
```
Expected: PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/maternity/
git commit -m "feat(maternity): labor board with WHO partograph SVG chart and entry capture

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 12: Deliveries & PNC tab

**Files:**
- Replace: `frontend/src/pages/maternity/DeliveriesTab.jsx`
- Create: `frontend/src/pages/maternity/DeliveryForm.jsx`
- Test: `frontend/src/pages/maternity/DeliveriesTab.test.jsx`

**Interfaces:**
- Consumes: `listEpisodes`, `getEpisode`, `recordDelivery`, `registerNewborn`, `createPncVisit` from `./api`.
- Produces: `<DeliveriesTab />` — Active episodes get a "Record delivery" action (DeliveryForm modal with dynamic newborn rows); Delivered episodes list their deliveries + newborns with a "Register as patient" button (disabled once `registered_patient_id` is set) and a "New PNC visit" form reusing the AncVisitForm modal pattern.

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/maternity/DeliveriesTab.test.jsx`:

```jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DeliveriesTab from './DeliveriesTab';
import * as api from './api';

vi.mock('./api');

describe('DeliveriesTab', () => {
  beforeEach(() => {
    api.listEpisodes.mockImplementation(({ status }) =>
      Promise.resolve(
        status === 'Delivered'
          ? [{ episode_id: 2, patient_name: 'Atieno, Mary', gravida: 1, para: 1, status: 'Delivered' }]
          : [{ episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1, status: 'Active' }],
      ));
  });

  it('shows delivered episodes with newborn registration', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 2, patient_name: 'Atieno, Mary', status: 'Delivered',
      anc_visits: [], pnc_visits: [], labor: [],
      deliveries: [{
        delivery_id: 5, mode: 'SVD', delivered_at: '2026-07-10T08:30:00Z',
        mother_status: 'Stable', blood_loss_ml: 250,
        newborns: [{ newborn_id: 7, birth_order: 1, sex: 'Female', weight_g: 3200,
                     outcome: 'Live', registered_patient_id: null }],
      }],
    });
    api.registerNewborn.mockResolvedValue({ patient_id: 321 });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByText(/Atieno, Mary/));
    const btn = await screen.findByRole('button', { name: /register as patient/i });
    await user.click(btn);
    await waitFor(() => expect(api.registerNewborn).toHaveBeenCalledWith(7));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/pages/maternity/DeliveriesTab.test.jsx`
Expected: FAIL (placeholder).

- [ ] **Step 3: Implement**

`frontend/src/pages/maternity/DeliveriesTab.jsx` — two lists (Active → "Record delivery", Delivered → detail with newborns + PNC). Follow the AncClinicTab layout idiom; on "Register as patient" call `registerNewborn(newborn_id)`, then re-`getEpisode` to refresh the button state; PNC form is a modal identical in structure to `AncVisitForm` with the PNC fields (`visit_date` required; `involution`, `lochia`, `feeding`, `cord_status` text; `baby_weight_g`, `bp_systolic`, `bp_diastolic` numeric) submitting `createPncVisit(episodeId, payload)`.

`frontend/src/pages/maternity/DeliveryForm.jsx` — modal like `AncVisitForm` with: `delivered_at` (datetime-local, required, convert with `new Date(value).toISOString()`), `mode` select (SVD / Assisted / CSection / Breech), `blood_loss_ml` number, `placenta_complete` checkbox, `complications` textarea, `mother_status` select (Stable / Referred / Deceased), and a dynamic newborn rows array (start with one row: `sex` select Male/Female, `weight_g` number, `apgar_1`/`apgar_5` numbers, `outcome` select Live/FSB/MSB; "Add twin" appends a row with `birth_order` = index+1). Validate ≥1 newborn client-side; submit `recordDelivery(episodeId, payload)`; surface `err?.response?.data?.detail`.

- [ ] **Step 4: Run tests + lint + build**

```bash
cd frontend && npx vitest run src/pages/maternity/ && npx eslint src/pages/maternity/ && npm run build
```
Expected: all PASS, no lint errors, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/maternity/
git commit -m "feat(maternity): deliveries & PNC tab — delivery capture, newborn registration, PNC visits

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 13: Full verification + PR

**Files:** none new.

- [ ] **Step 1: Full backend suite**

```bash
cd backend && python3 -m pytest tests/ -x -q 2>&1 | tail -20
```
Expected: maternity tests all pass; pre-existing failures limited to the known ~34 in `test_api.py` (compare against a `git stash` baseline run if unsure — no NEW failures).

- [ ] **Step 2: Full frontend suite + lint + build**

```bash
cd frontend && npx vitest run && npx eslint src/ --max-warnings=0 2>&1 | tail -5 && npm run build
```
Expected: vitest green; eslint reports nothing new on maternity files; build succeeds.

- [ ] **Step 3: Migration gate dry-run**

```bash
cd backend && python3 scripts/migrate_all_tenants.py 2>&1 | tail -15
```
Expected: completes without error; maternity tables + seeds applied idempotently on every tenant.

- [ ] **Step 4: Drive the real flow (verify skill)**

Invoke the `verify` skill: with uvicorn + `npm run dev` running, walk enroll → ANC visit → admit → labor link → partograph entries (cross the alert line, check the bell) → delivery with twin rows → newborn registration → PNC visit, as Nurse.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/maternity-module
gh pr create --base development --title "feat(maternity): full maternity module — ANC/PNC, partograph, deliveries, newborns" --body "Implements docs/superpowers/specs/2026-07-10-maternity-module-design.md per docs/superpowers/plans/2026-07-10-maternity-module.md. Schema-additive migration (7 tables) registered in migrate_all_tenants with mirrored MAT-* price-list seed. Opt-in module flag; maternity:read/manage granted to Nurse+Doctor.

🤖 Generated with [RuFlo](https://github.com/ruvnet/ruflo)"
```

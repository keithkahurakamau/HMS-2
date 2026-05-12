"""
End-to-end demo seed for the HMS platform.

This is the *opinionated* seed used for development, integration tests, and
sales demos. It will:

  1. Ensure the master DB exists and contains a superadmin.
  2. Provision (or reuse) a demo tenant: "Mayo Clinic" (db = mayoclinic_db).
  3. Seed the tenant with:
       • staff user accounts for every baked-in role
       • a realistic patient roster
       • a lab test catalog with discrete result parameters
       • a radiology exam catalog
       • inventory items — reagents (consumable) AND microscope slides /
         beakers / probes (reusable) — across all four locations
       • hospital_settings rows for branding, billing, lab, radiology, etc.

The script is idempotent. Re-runs detect existing rows and skip them; only
new objects are inserted. Pass ``--reset`` to drop the demo tenant DB first.

Usage:
    python seed_demo.py
    python seed_demo.py --reset
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Repo path bootstrap ─────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.config.database import DATABASE_URL, get_tenant_engine, MasterSessionLocal
from app.core.security import get_password_hash
from app.models.master import Tenant, SuperAdmin
from app.models.user import User, Role, Permission
from app.models.patient import Patient
from app.models.inventory import Location, InventoryItem, StockBatch
from app.models.laboratory import LabTestCatalog, LabCatalogParameter
from app.models.radiology import RadiologyExamCatalog
from app.models.settings import HospitalSetting
from app.services.tenant_provisioning import provision_tenant, DEFAULT_SETTINGS

# ── Demo tenant constants ───────────────────────────────────────────────────
TENANT_NAME = "Mayo Clinic"
TENANT_DB = "mayoclinic_db"
TENANT_DOMAIN = "mayoclinic.com"
BOOT_ADMIN_EMAIL = f"admin@{TENANT_DOMAIN}"
BOOT_ADMIN_NAME = "Mayo Clinic Admin"
SHARED_PASSWORD = "Password@123"   # demo only — never use in production

DEMO_USERS = [
    # (email, full_name, role)
    (f"admin@{TENANT_DOMAIN}",         "Mayo Clinic Admin",   "Admin"),
    (f"dr.kahura@{TENANT_DOMAIN}",     "Dr. Keith Kahura",    "Doctor"),
    (f"nurse.joy@{TENANT_DOMAIN}",     "Nurse Joy Wanjiku",   "Nurse"),
    (f"pharm.keith@{TENANT_DOMAIN}",   "Keith the Pharmacist","Pharmacist"),
    (f"lab.alice@{TENANT_DOMAIN}",     "Alice Otieno",        "Lab Technician"),
    (f"rad.mwangi@{TENANT_DOMAIN}",    "Dr. Peter Mwangi",    "Radiologist"),
    (f"rec.brian@{TENANT_DOMAIN}",     "Brian Mutua",         "Receptionist"),
]

DEMO_PATIENTS = [
    # surname, other_names, sex, dob, blood, phone, town
    ("Kamau",   "John Mwangi",      "Male",   date(1985, 4, 12), "O+",  "+254700111001", "Nairobi"),
    ("Wanjiru", "Mary Njeri",       "Female", date(1992, 9,  3), "A+",  "+254700111002", "Kiambu"),
    ("Otieno",  "Brian Onyango",    "Male",   date(1978, 1, 25), "B+",  "+254700111003", "Kisumu"),
    ("Mutiso",  "Grace Mwende",     "Female", date(2001, 6, 14), "O-",  "+254700111004", "Machakos"),
    ("Hassan",  "Ahmed Yusuf",      "Male",   date(1965,12,  2), "AB+", "+254700111005", "Mombasa"),
    ("Kiprop",  "Caroline Jeptoo",  "Female", date(1989, 3, 19), "A-",  "+254700111006", "Eldoret"),
    ("Karanja", "Peter Maina",      "Male",   date(1972, 7, 30), "O+",  "+254700111007", "Nakuru"),
    ("Achieng", "Linda Akinyi",     "Female", date(1995, 2, 11), "B-",  "+254700111008", "Kisumu"),
    ("Mwangi",  "Daniel Kamotho",   "Male",   date(1968, 8,  4), "AB-", "+254700111009", "Nyeri"),
    ("Wairimu", "Faith Wangari",    "Female", date(2008,11, 22), "O+",  "+254700111010", "Thika"),
]

# Lab catalog — each test ships with its discrete parameter set so the lab UI
# renders the right inputs straight from the DB.
LAB_CATALOG = [
    {
        "test_name": "Complete Blood Count (CBC)",
        "category": "Hematology",
        "default_specimen_type": "Blood",
        "base_price": 600,
        "requires_barcode": True,
        "parameters": [
            ("wbc",  "White Blood Cells (WBC)", "x10⁹/L", "number",  4.0, 11.0, 1),
            ("rbc",  "Red Blood Cells (RBC)",   "x10¹²/L","number",  4.5,  5.9, 2),
            ("hgb",  "Hemoglobin (HGB)",        "g/dL",   "number", 12.0, 16.0, 3),
            ("hct",  "Hematocrit (HCT)",        "%",      "number", 36.0, 50.0, 4),
            ("plt",  "Platelets",               "x10⁹/L", "number",150.0,400.0, 5),
        ],
    },
    {
        "test_name": "Urinalysis (Dipstick + Microscopy)",
        "category": "Microbiology",
        "default_specimen_type": "Urine",
        "base_price": 350,
        "requires_barcode": False,
        "parameters": [
            ("ph",         "pH",          "",      "number",  4.5,  8.0, 1),
            ("appearance", "Appearance",  "",      "choice",   None, None, 2, "Clear,Cloudy,Turbid"),
            ("glucose",    "Glucose",     "",      "choice",   None, None, 3, "Negative,Trace,1+,2+,3+,4+"),
            ("protein",    "Protein",     "",      "choice",   None, None, 4, "Negative,Trace,1+,2+,3+,4+"),
            ("ketones",    "Ketones",     "",      "choice",   None, None, 5, "Negative,Trace,Small,Moderate,Large"),
        ],
    },
    {
        "test_name": "Malaria Smear",
        "category": "Microbiology",
        "default_specimen_type": "Blood",
        "base_price": 250,
        "requires_barcode": False,
        "parameters": [
            ("result",  "Result",   "", "choice", None, None, 1, "Negative,Positive (P. falciparum),Positive (P. vivax),Positive (mixed)"),
            ("density", "Density",  "/μL", "number", None, None, 2),
        ],
    },
    {
        "test_name": "Random Blood Sugar",
        "category": "Biochemistry",
        "default_specimen_type": "Blood",
        "base_price": 180,
        "requires_barcode": False,
        "parameters": [
            ("rbs", "Random Blood Sugar", "mmol/L", "number", 3.9, 7.8, 1),
        ],
    },
    {
        "test_name": "Liver Function Test (LFT)",
        "category": "Biochemistry",
        "default_specimen_type": "Blood",
        "base_price": 1200,
        "requires_barcode": True,
        "parameters": [
            ("alt",       "ALT",            "U/L",  "number",  7.0, 56.0, 1),
            ("ast",       "AST",            "U/L",  "number", 10.0, 40.0, 2),
            ("alp",       "ALP",            "U/L",  "number", 44.0,147.0, 3),
            ("bilirubin", "Total bilirubin","µmol/L","number", 1.7, 20.5, 4),
        ],
    },
    {
        "test_name": "HIV Rapid Test",
        "category": "Serology",
        "default_specimen_type": "Blood",
        "base_price": 200,
        "requires_barcode": False,
        "parameters": [
            ("result", "Result", "", "choice", None, None, 1, "Negative,Positive,Indeterminate"),
        ],
    },
]

RADIOLOGY_CATALOG = [
    ("Chest X-Ray (PA)",        "X-Ray",      "Chest",        800,  False, False),
    ("Chest X-Ray (Lateral)",   "X-Ray",      "Chest",        800,  False, False),
    ("Abdominal Ultrasound",    "Ultrasound", "Abdomen",     2500,  True,  False),
    ("Pelvic Ultrasound",       "Ultrasound", "Pelvis",      2500,  True,  False),
    ("Obstetric Ultrasound",    "Ultrasound", "Uterus",      3000,  False, False),
    ("Head CT (non-contrast)",  "CT",         "Head",        7500,  False, False),
    ("Head CT (contrast)",      "CT",         "Head",        9500,  True,  True),
    ("MRI Knee",                "MRI",        "Right Knee", 15000,  False, False),
    ("Mammography Bilateral",   "Mammography","Breasts",     4500,  True,  False),
]

INVENTORY_ITEMS = [
    # name, category, generic_name, dosage_form, unit_cost, unit_price, reorder_threshold, is_reusable
    ("Sodium Chloride 0.9% 500mL", "Drug",       "Sodium chloride",      "bottle",  120,  180,  20, False),
    ("Paracetamol 500mg",          "Drug",       "Paracetamol",          "tablet",   2,    5,  300, False),
    ("Amoxicillin 500mg",          "Drug",       "Amoxicillin",          "capsule",  4,    8,  200, False),
    ("Disposable Syringe 5mL",     "Consumable", None,                   "piece",    8,   15,  500, False),
    ("Cotton Wool 500g",           "Consumable", None,                   "roll",    250,  350,  20, False),
    ("CBC Reagent Pack",           "Reagent",    None,                   "kit",    3500, 4500,   5, False),
    ("Urinalysis Strips",          "Reagent",    None,                   "strip",    18,   30, 200, False),
    ("Malaria RDT Cassette",       "Reagent",    None,                   "kit",     120,  200, 100, False),
    # Reusable items — logged on use but never decremented.
    ("Microscope Slide",           "Reusable",   None,                   "piece",    20,    0,  10, True),
    ("Reusable Beaker 250mL",      "Reusable",   None,                   "piece",   180,    0,   5, True),
    ("Ultrasound Probe (linear)",  "Reusable",   None,                   "unit",  85000,    0,   1, True),
]


# ── Helpers ────────────────────────────────────────────────────────────────
def _tenant_session(db_name: str):
    eng = get_tenant_engine(db_name)
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)()


def _drop_tenant_db(db_name: str) -> None:
    base_url = DATABASE_URL.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"
            ), {"n": db_name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        admin.dispose()


def _ensure_tenant() -> Tenant:
    """Provision the demo tenant (or return the existing row)."""
    master = MasterSessionLocal()
    try:
        existing = master.query(Tenant).filter(Tenant.db_name == TENANT_DB).first()
        if existing:
            print(f"   tenant '{TENANT_DB}' already exists — reusing.")
            return existing
        print(f"   provisioning new tenant '{TENANT_DB}'…")
        tenant, temp = provision_tenant(
            master,
            name=TENANT_NAME,
            domain=TENANT_DOMAIN,
            db_name=TENANT_DB,
            admin_email=BOOT_ADMIN_EMAIL,
            admin_full_name=BOOT_ADMIN_NAME,
            theme_color="emerald",
            is_premium=True,
        )
        # Bootstrap admin password gets a known value so the demo tests can
        # log in without the temp-password dance.
        admin_session = _tenant_session(TENANT_DB)
        try:
            u = admin_session.query(User).filter(User.email == BOOT_ADMIN_EMAIL).first()
            if u:
                u.hashed_password = get_password_hash(SHARED_PASSWORD)
                u.must_change_password = False
                admin_session.commit()
        finally:
            admin_session.close()
        return tenant
    finally:
        master.close()


def _ensure_users() -> None:
    session = _tenant_session(TENANT_DB)
    try:
        roles = {r.name: r for r in session.query(Role).all()}
        for email, full_name, role_name in DEMO_USERS:
            if session.query(User).filter(User.email == email).first():
                continue
            role = roles.get(role_name)
            if not role:
                print(f"   ⚠ role '{role_name}' missing — skipping {email}")
                continue
            session.add(User(
                email=email,
                full_name=full_name,
                hashed_password=get_password_hash(SHARED_PASSWORD),
                role_id=role.role_id,
                is_active=True,
                must_change_password=False,
            ))
            print(f"   + user {email} ({role_name})")
        session.commit()
    finally:
        session.close()


def _ensure_patients() -> None:
    session = _tenant_session(TENANT_DB)
    try:
        admin = session.query(User).filter(User.email == BOOT_ADMIN_EMAIL).first()
        existing_count = session.query(Patient).count()
        target = max(existing_count + 1, 1)
        for i, (surname, other_names, sex, dob, blood, phone, town) in enumerate(DEMO_PATIENTS):
            op_no = f"OP-2026-{target + i:04d}"
            if session.query(Patient).filter(Patient.outpatient_no == op_no).first():
                continue
            if session.query(Patient).filter(
                Patient.surname == surname, Patient.other_names == other_names
            ).first():
                continue
            session.add(Patient(
                outpatient_no=op_no,
                surname=surname, other_names=other_names,
                sex=sex, date_of_birth=dob,
                blood_group=blood,
                telephone_1=phone,
                town=town,
                marital_status="Single" if i % 2 else "Married",
                nationality="Kenyan",
                id_type="National ID",
                id_number=f"{30000000 + i}",
                registered_by=admin.user_id if admin else None,
                is_active=True,
            ))
            print(f"   + patient {op_no} {surname}, {other_names}")
        session.commit()
    finally:
        session.close()


def _ensure_lab_catalog() -> None:
    session = _tenant_session(TENANT_DB)
    try:
        for entry in LAB_CATALOG:
            cat = session.query(LabTestCatalog).filter(
                LabTestCatalog.test_name == entry["test_name"]
            ).first()
            if cat:
                continue
            cat = LabTestCatalog(
                test_name=entry["test_name"],
                category=entry["category"],
                default_specimen_type=entry["default_specimen_type"],
                base_price=Decimal(str(entry["base_price"])),
                turnaround_hours=entry.get("turnaround_hours", 24),
                requires_barcode=entry.get("requires_barcode", False),
                is_active=True,
            )
            session.add(cat)
            session.flush()
            for row in entry["parameters"]:
                # row may be (key, name, unit, value_type, ref_low, ref_high, sort_order[, choices])
                key, name, unit, value_type, ref_low, ref_high, sort_order, *rest = row
                choices = rest[0] if rest else None
                session.add(LabCatalogParameter(
                    catalog_id=cat.catalog_id,
                    key=key, name=name, unit=unit,
                    value_type=value_type, choices=choices,
                    ref_low=ref_low, ref_high=ref_high,
                    sort_order=sort_order, is_active=True,
                ))
            print(f"   + lab test {entry['test_name']} ({len(entry['parameters'])} params)")
        session.commit()
    finally:
        session.close()


def _ensure_radiology_catalog() -> None:
    session = _tenant_session(TENANT_DB)
    try:
        for (name, modality, body_part, price, prep, contrast) in RADIOLOGY_CATALOG:
            if session.query(RadiologyExamCatalog).filter(
                RadiologyExamCatalog.exam_name == name
            ).first():
                continue
            session.add(RadiologyExamCatalog(
                exam_name=name, modality=modality, body_part=body_part,
                base_price=Decimal(str(price)),
                requires_prep=prep,
                requires_contrast=contrast,
                default_findings_template=f"Technique: {modality} of {body_part}.\nFindings: ",
                default_impression_template="No acute abnormality. ",
                is_active=True,
            ))
            print(f"   + radiology {name} ({modality})")
        session.commit()
    finally:
        session.close()


def _ensure_inventory() -> None:
    session = _tenant_session(TENANT_DB)
    try:
        loc_by_name = {l.name: l for l in session.query(Location).all()}
        main_store = loc_by_name.get("Main Store")
        if not main_store:
            print("   ⚠ Main Store location missing — skipping inventory seed.")
            return
        for i, (name, category, generic, dosage, unit_cost, unit_price, threshold, reusable) in enumerate(INVENTORY_ITEMS):
            item = session.query(InventoryItem).filter(InventoryItem.name == name).first()
            if not item:
                item = InventoryItem(
                    item_code=f"ITM-{i+1:04d}",
                    name=name, category=category,
                    generic_name=generic, dosage_form=dosage,
                    unit_cost=Decimal(str(unit_cost)),
                    unit_price=Decimal(str(unit_price)),
                    reorder_threshold=threshold,
                    is_reusable=reusable,
                    is_active=True,
                )
                session.add(item)
                session.flush()
                print(f"   + inventory {name}{' (reusable)' if reusable else ''}")
            # One starting batch in main store
            if not session.query(StockBatch).filter(StockBatch.item_id == item.item_id).first():
                qty = 1 if reusable else 100
                session.add(StockBatch(
                    item_id=item.item_id,
                    location_id=main_store.location_id,
                    batch_number=f"BAT-{item.item_code}-001",
                    quantity=qty,
                    expiry_date=date.today() + timedelta(days=365),
                    supplier_name="DemoMed Suppliers",
                ))
        # Transfer the reagents + reusable items to Laboratory.
        lab = loc_by_name.get("Laboratory")
        if lab:
            lab_items = ["CBC Reagent Pack", "Urinalysis Strips", "Malaria RDT Cassette",
                         "Microscope Slide", "Reusable Beaker 250mL"]
            for nm in lab_items:
                it = session.query(InventoryItem).filter(InventoryItem.name == nm).first()
                if not it:
                    continue
                if session.query(StockBatch).filter(
                    StockBatch.item_id == it.item_id,
                    StockBatch.location_id == lab.location_id,
                ).first():
                    continue
                qty = 1 if it.is_reusable else 50
                session.add(StockBatch(
                    item_id=it.item_id,
                    location_id=lab.location_id,
                    batch_number=f"LAB-{it.item_code}-001",
                    quantity=qty,
                    expiry_date=date.today() + timedelta(days=180),
                    supplier_name="DemoMed Suppliers",
                ))
                print(f"   ↳ stocked Laboratory with {nm}")
        session.commit()
    finally:
        session.close()


def _ensure_settings() -> None:
    """Settings rows are inserted by provision_tenant on a fresh tenant. On
    re-seeds, top-up missing rows so newer defaults land without a migration."""
    session = _tenant_session(TENANT_DB)
    try:
        for (category, key, label, description, data_type, value, is_sensitive, sort_order) in DEFAULT_SETTINGS:
            if session.query(HospitalSetting).filter(
                HospitalSetting.category == category,
                HospitalSetting.key == key,
            ).first():
                continue
            session.add(HospitalSetting(
                category=category, key=key, label=label, description=description,
                data_type=data_type, value=value, is_sensitive=is_sensitive,
                sort_order=sort_order,
            ))
            print(f"   + setting {category}.{key}")
        # Personalize a few demo values.
        for cat, key, val in [
            ("branding", "hospital_name", "Mayo Clinic Kenya"),
            ("branding", "tagline", "Excellence in Care"),
            ("billing", "currency", "KES"),
            ("notifications", "email_from", "no-reply@mayoclinic.com"),
            ("privacy", "kdpa_dpo_email", "dpo@mayoclinic.com"),
        ]:
            row = session.query(HospitalSetting).filter(
                HospitalSetting.category == cat, HospitalSetting.key == key,
            ).first()
            if row:
                row.value = val
        session.commit()
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the HMS demo tenant end-to-end.")
    parser.add_argument("--reset", action="store_true",
                        help=f"Drop {TENANT_DB} (if it exists) and reseed from scratch.")
    args = parser.parse_args()

    print("=" * 64)
    print("  HMS DEMO SEED")
    print("=" * 64)

    if args.reset:
        # Also clear the master row so provision_tenant can recreate it.
        print(f"-> dropping demo tenant DB '{TENANT_DB}'…")
        _drop_tenant_db(TENANT_DB)
        master = MasterSessionLocal()
        try:
            master.query(Tenant).filter(Tenant.db_name == TENANT_DB).delete()
            master.commit()
        finally:
            master.close()

    print("[1/7] tenant…")
    _ensure_tenant()

    print("[2/7] users…")
    _ensure_users()

    print("[3/7] patients…")
    _ensure_patients()

    print("[4/7] lab catalog + parameters…")
    _ensure_lab_catalog()

    print("[5/7] radiology catalog…")
    _ensure_radiology_catalog()

    print("[6/7] inventory (with reusable items)…")
    _ensure_inventory()

    print("[7/7] hospital settings…")
    _ensure_settings()

    print()
    print("Demo accounts (all use the same password):")
    print(f"  password: {SHARED_PASSWORD}")
    for email, name, role in DEMO_USERS:
        print(f"  {role:<15} {email}  ({name})")
    print()
    print(f"Hospital domain: {TENANT_DOMAIN}")
    print(f"X-Tenant-ID:     {TENANT_DB}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())

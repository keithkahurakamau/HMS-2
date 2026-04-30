import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

# Ensure the app module can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.database import SessionLocal, Base, engine
from app.core.security import get_password_hash

# Import ALL your models
from app.models.user import User, Role, Permission
from app.models.patient import Patient
from app.models.inventory import Location, InventoryItem, StockBatch, StockTransfer, DispenseLog, InventoryUsageLog
from app.models.wards import Ward, Bed, AdmissionRecord
from app.models.laboratory import LabTestCatalog, LabTestRequiredItem, LabTest
from app.models.clinical import Appointment, PatientQueue, MedicalRecord
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.audit import AuditLog
from app.models.medical_history import ConsentRecord, MedicalHistoryEntry

def reset_database():
    """
    DANGER ZONE: Wipes the entire database schema using raw PostgreSQL CASCADE.
    This bypasses all foreign key deadlocks and guarantees a clean slate.
    """
    print("🧨 Wiping existing database schema with CASCADE...")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE;"))
        connection.execute(text("CREATE SCHEMA public;"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        connection.commit()
        
    print("🏗️ Rebuilding database schema...")
    Base.metadata.create_all(bind=engine)

def seed_database():
    print("🌱 Initiating Full Enterprise Hospital Seed Protocol...")
    db = SessionLocal()
    
    try:
        # ==========================================
        # 1. LOCATIONS (Hub and Spoke)
        # ==========================================
        print("   -> Seeding Locations...")
        locs = ["Main Store", "Pharmacy", "Laboratory", "Wards", "Front Desk"]
        locations = {}
        for l_name in locs:
            loc = Location(name=l_name, description=f"{l_name} Department")
            db.add(loc)
            locations[l_name] = loc
        db.flush()

        # ==========================================
        # 2. ROLES, PERMISSIONS & USERS
        # ==========================================
        print("   -> Seeding Permissions, Roles & Users...")
        
        # 2a. Create Core System Permissions
        permissions_data = [
            "users:manage", "clinical:write", "clinical:read", 
            "patients:read", "patients:write", "history:read", "history:manage",
            "pharmacy:manage", "pharmacy:read", "laboratory:manage", "laboratory:read", 
            "wards:manage", "billing:read", "billing:manage"
        ]
        
        perms = {}
        for p_code in permissions_data:
            perm = Permission(codename=p_code, description=f"Allows {p_code}")
            db.add(perm)
            perms[p_code] = perm
        db.flush()

        # 2b. Create Roles and Map Permissions to them
        roles_config = {
            "Admin": ["users:manage", "clinical:read", "patients:read", "pharmacy:read", "laboratory:read", "wards:manage", "billing:manage", "history:read", "history:manage"],
            "Doctor": ["clinical:write", "clinical:read", "patients:read", "patients:write", "pharmacy:read", "laboratory:read", "history:read", "history:manage"],
            "Nurse": ["clinical:read", "patients:read", "wards:manage", "pharmacy:read", "history:read"],
            "Pharmacist": ["pharmacy:manage", "pharmacy:read", "patients:read"],
            "Lab Technician": ["laboratory:manage", "laboratory:read", "patients:read"],
            "Receptionist": ["patients:read", "patients:write", "billing:read"]
        }

        roles = {}
        for r_name, p_list in roles_config.items():
            role = Role(name=r_name, description=f"{r_name} Access Level")
            for p_code in p_list:
                role.permissions.append(perms[p_code])
            db.add(role)
            roles[r_name] = role
        db.flush()

        # 2c. Create Staff Users
        users_data = [
            {"email": "admin@hospital.com", "full_name": "System Admin", "role": "Admin", "spec": None, "lic": None},
            {"email": "dr.kahura@hospital.com", "full_name": "Dr. James Kahura", "role": "Doctor", "spec": "Internal Medicine", "lic": "MPDB-1001"},
            {"email": "dr.omondi@hospital.com", "full_name": "Dr. Sarah Omondi", "role": "Doctor", "spec": "Pediatrics", "lic": "MPDB-2002"},
            {"email": "nurse.joy@hospital.com", "full_name": "Nurse Joy Wanjiku", "role": "Nurse", "spec": "Ward Matron", "lic": "NCK-8822"},
            {"email": "pharm.keith@hospital.com", "full_name": "Pharm. Keith Kamau", "role": "Pharmacist", "spec": "Clinical Pharmacist", "lic": "PPB-5533"},
            {"email": "lab.alice@hospital.com", "full_name": "Alice Mutua", "role": "Lab Technician", "spec": "Pathology", "lic": "KMLTTB-9911"},
            {"email": "rec.brian@hospital.com", "full_name": "Brian Koech", "role": "Receptionist", "spec": None, "lic": None}
        ]
        
        staff = {}
        for u in users_data:
            user = User(
                email=u["email"], 
                full_name=u["full_name"],
                hashed_password=get_password_hash("password123"),
                role_id=roles[u["role"]].role_id,
                specialization=u["spec"],
                license_number=u["lic"],
                is_active=True
            )
            db.add(user)
            staff[u["email"]] = user
        db.flush()

        # ==========================================
        # 3. PATIENT REGISTRY (Expanded & Localized)
        # ==========================================
        print("   -> Seeding Patient Registry (10 Patients)...")
        
        receptionist_id = staff["rec.brian@hospital.com"].user_id
        
        patients_data = [
            {
                "outpatient_no": "OP-2026-0001", "inpatient_no": "IP-2026-0001",
                "surname": "Kamau", "other_names": "David Njoroge", "sex": "Male",
                "date_of_birth": datetime(1985, 4, 12).date(), "marital_status": "Married",
                "religion": "Christian", "primary_language": "Swahili", "blood_group": "O+",
                "allergies": "Penicillin", "chronic_conditions": "Hypertension",
                "id_type": "National ID", "id_number": "29384756", "nationality": "Kenyan",
                "telephone_1": "0712345678", "telephone_2": "0722000111", "email": "david.kamau@example.com",
                "residence": "Roysambu", "town": "Nairobi", "occupation": "Civil Engineer",
                "nok_name": "Jane Kamau", "nok_relationship": "Wife", "nok_contact": "0799123456",
                "reference_number": "NHIF-998877"
            },
            {
                "outpatient_no": "OP-2026-0002", "inpatient_no": None,
                "surname": "Achieng", "other_names": "Sarah", "sex": "Female",
                "date_of_birth": datetime(1992, 11, 23).date(), "marital_status": "Single",
                "religion": "Christian", "primary_language": "English", "blood_group": "A+",
                "allergies": "None", "chronic_conditions": "Asthma",
                "id_type": "National ID", "id_number": "33445566", "nationality": "Kenyan",
                "telephone_1": "0723456789", "email": "sarah.achieng@example.com",
                "residence": "Kilimani", "town": "Nairobi", "occupation": "Financial Analyst",
                "nok_name": "Peter Omondi", "nok_relationship": "Brother", "nok_contact": "0744123456"
            },
            {
                "outpatient_no": "OP-2026-0003", "inpatient_no": None,
                "surname": "Mohammed", "other_names": "Ali Tariq", "sex": "Male",
                "date_of_birth": datetime(1978, 2, 15).date(), "marital_status": "Married",
                "religion": "Muslim", "primary_language": "Somali", "blood_group": "B+",
                "allergies": "Dust, Pollen", "chronic_conditions": "Type 2 Diabetes",
                "id_type": "Passport", "id_number": "A1234567", "nationality": "Somalian",
                "telephone_1": "0733445566", "residence": "Eastleigh", "town": "Nairobi", 
                "occupation": "Businessman", "nok_name": "Fatuma Ali", "nok_relationship": "Wife", 
                "nok_contact": "0733998877"
            },
            {
                "outpatient_no": "OP-2026-0004", "inpatient_no": "IP-2026-0002",
                "surname": "Wanjiru", "other_names": "Grace", "sex": "Female",
                "date_of_birth": datetime(1955, 6, 30).date(), "marital_status": "Widowed",
                "religion": "Christian", "primary_language": "Kikuyu", "blood_group": "O-",
                "allergies": "Sulfa Drugs", "chronic_conditions": "Arthritis, Hypertension",
                "id_type": "National ID", "id_number": "11223344", "nationality": "Kenyan",
                "telephone_1": "0700112233", "residence": "Kasarani", "town": "Nairobi", 
                "occupation": "Retired", "nok_name": "John Ndungu", "nok_relationship": "Son", 
                "nok_contact": "0722334455"
            },
            {
                "outpatient_no": "OP-2026-0005", "inpatient_no": None,
                "surname": "Smith", "other_names": "Robert", "sex": "Male",
                "date_of_birth": datetime(1989, 8, 10).date(), "marital_status": "Single",
                "religion": "Other", "primary_language": "English", "blood_group": "AB+",
                "allergies": "Peanuts", "chronic_conditions": "None",
                "id_type": "Alien ID", "id_number": "F9988776", "nationality": "British",
                "telephone_1": "0755667788", "email": "rob.smith@ukmail.com",
                "residence": "Westlands", "town": "Nairobi", "occupation": "Diplomat",
                "nok_name": "Emma Smith", "nok_relationship": "Sister", "nok_contact": "+447911123456"
            },
            {
                "outpatient_no": "OP-2026-0006", "inpatient_no": None,
                "surname": "Mutua", "other_names": "Faith Syombua", "sex": "Female",
                "date_of_birth": datetime(2015, 1, 5).date(), "marital_status": "Single",
                "religion": "Christian", "primary_language": "Swahili", "blood_group": "A-",
                "allergies": "None", "chronic_conditions": "None",
                "id_type": "Birth Certificate", "id_number": "BC-2015-8899", "nationality": "Kenyan",
                "telephone_1": "0799887766", "residence": "Langata", "town": "Nairobi", 
                "occupation": "Student", "nok_name": "Daniel Mutua", "nok_relationship": "Father", 
                "nok_contact": "0799887766"
            },
            {
                "outpatient_no": "OP-2026-0007", "inpatient_no": None,
                "surname": "Kipchoge", "other_names": "Eliud", "sex": "Male",
                "date_of_birth": datetime(1984, 11, 5).date(), "marital_status": "Married",
                "religion": "Christian", "primary_language": "Kalenjin", "blood_group": "O+",
                "allergies": "None", "chronic_conditions": "None",
                "id_type": "National ID", "id_number": "22334455", "nationality": "Kenyan",
                "telephone_1": "0722111222", "residence": "Eldoret", "town": "Eldoret", 
                "occupation": "Athlete", "nok_name": "Grace Sugut", "nok_relationship": "Wife", 
                "nok_contact": "0722999888"
            },
            {
                "outpatient_no": "OP-2026-0008", "inpatient_no": None,
                "surname": "Onyango", "other_names": "Kevin", "sex": "Male",
                "date_of_birth": datetime(2000, 3, 18).date(), "marital_status": "Single",
                "religion": "Christian", "primary_language": "English", "blood_group": "B-",
                "allergies": "Latex", "chronic_conditions": "None",
                "id_type": "National ID", "id_number": "39998877", "nationality": "Kenyan",
                "telephone_1": "0711223344", "email": "kevin.onyango@usiu.ac.ke",
                "residence": "Thika Road", "town": "Nairobi", "occupation": "University Student",
                "nok_name": "Rose Onyango", "nok_relationship": "Mother", "nok_contact": "0733112233"
            },
            {
                "outpatient_no": "OP-2026-0009", "inpatient_no": "IP-2026-0003",
                "surname": "Naidoo", "other_names": "Priya", "sex": "Female",
                "date_of_birth": datetime(1990, 7, 22).date(), "marital_status": "Married",
                "religion": "Hindu", "primary_language": "English", "blood_group": "AB-",
                "allergies": "Shellfish", "chronic_conditions": "PCOS",
                "id_type": "Passport", "id_number": "Z99887766", "nationality": "South African",
                "telephone_1": "0744556677", "residence": "Parklands", "town": "Nairobi", 
                "occupation": "Architect", "nok_name": "Rajesh Naidoo", "nok_relationship": "Husband", 
                "nok_contact": "0744998877"
            },
            {
                "outpatient_no": "OP-2026-0010", "inpatient_no": None,
                "surname": "Odhiambo", "other_names": "Brian", "sex": "Male",
                "date_of_birth": datetime(1995, 12, 10).date(), "marital_status": "Single",
                "religion": "Christian", "primary_language": "Luo", "blood_group": "O+",
                "allergies": "None", "chronic_conditions": "None",
                "id_type": "National ID", "id_number": "35556677", "nationality": "Kenyan",
                "telephone_1": "0799112233", "residence": "South B", "town": "Nairobi", 
                "occupation": "Graphic Designer", "nok_name": "Mercy Odhiambo", "nok_relationship": "Sister", 
                "nok_contact": "0700998877"
            }
        ]

        db_patients = []
        for p_data in patients_data:
            patient = Patient(**p_data, registered_by=receptionist_id)
            db.add(patient)
            db_patients.append(patient)
            
        db.flush()
        
        # Reference the first patient for clinical workflow data below
        primary_patient = db_patients[0] 

        # ==========================================
        # 4. INVENTORY & PROCUREMENT
        # ==========================================
        print("   -> Seeding Master Inventory & Batches...")
        items_data = [
            {"code": "DRG-001", "name": "Amoxicillin 625mg", "cat": "Medication", "cost": 100, "price": 150},
            {"code": "DRG-002", "name": "Paracetamol 500mg IV", "cat": "Medication", "cost": 300, "price": 450},
            {"code": "RGT-001", "name": "CBC Reagent Pack", "cat": "Reagents", "cost": 4000, "price": 5000},
            {"code": "CNS-001", "name": "Surgical Gloves (Box)", "cat": "Consumables", "cost": 500, "price": 800}
        ]
        
        catalog = {}
        for i in items_data:
            item = InventoryItem(item_code=i["code"], name=i["name"], category=i["cat"], unit_cost=i["cost"], unit_price=i["price"])
            db.add(item)
            catalog[i["name"]] = item
        db.flush()

        batches = [
            {"item": "Amoxicillin 625mg", "loc": "Pharmacy", "batch": "AMOX-01", "qty": 1000, "supplier": "MedKEM Logistics"},
            {"item": "Paracetamol 500mg IV", "loc": "Wards", "batch": "PARA-IV-99", "qty": 150, "supplier": "Global Pharma"},
            {"item": "Surgical Gloves (Box)", "loc": "Wards", "batch": "GLV-22", "qty": 20, "supplier": "Surgical Supplies Ltd"},
            {"item": "CBC Reagent Pack", "loc": "Laboratory", "batch": "RGT-CBC-01", "qty": 15, "supplier": "LabTech Diagnostics"},
            {"item": "Amoxicillin 625mg", "loc": "Main Store", "batch": "AMOX-02", "qty": 5000, "supplier": "MedKEM Logistics"}
        ]

        for b in batches:
            batch = StockBatch(
                item_id=catalog[b["item"]].item_id, location_id=locations[b["loc"]].location_id,
                batch_number=b["batch"], quantity=b["qty"], expiry_date=datetime.now() + timedelta(days=365),
                supplier_name=b["supplier"]
            )
            db.add(batch)
        db.flush()

        # ==========================================
        # 5. LAB CATALOG & BILL OF MATERIALS (BOM)
        # ==========================================
        print("   -> Seeding Lab Catalog & BOMs...")
        lab_cat = LabTestCatalog(test_name="Complete Blood Count (CBC)", category="Hematology", default_specimen_type="Whole Blood", base_price=1500.0)
        db.add(lab_cat)
        db.flush()

        # Link the Reagent to the Test (When a CBC is done, it deducts 1 CBC Reagent Pack)
        bom = LabTestRequiredItem(
            catalog_id=lab_cat.catalog_id,
            inventory_item_id=catalog["CBC Reagent Pack"].item_id,
            item_name="CBC Reagent Pack",
            quantity_required=1
        )
        db.add(bom)
        db.flush()

        # ==========================================
        # 6. CLINICAL WORKFLOW (Appts, Queue, Records)
        # ==========================================
        print("   -> Seeding Clinical Encounters...")
        # 1. Create an Appointment for the primary patient
        appt = Appointment(patient_id=primary_patient.patient_id, doctor_id=staff["dr.kahura@hospital.com"].user_id, appointment_date=datetime.now(timezone.utc), status="Completed")
        db.add(appt)
        
        # 2. Put patient in Queue
        queue = PatientQueue(patient_id=primary_patient.patient_id, department="Consultation", acuity_level=2, status="In Progress", assigned_to=staff["dr.kahura@hospital.com"].user_id)
        db.add(queue)
        
        # 3. Create the Medical Record (SOAP Note)
        record = MedicalRecord(
            patient_id=primary_patient.patient_id, doctor_id=staff["dr.kahura@hospital.com"].user_id,
            record_status="Billed", blood_pressure="130/85", heart_rate=92, temperature=39.1,
            chief_complaint="Severe fever and chills for 3 days.",
            diagnosis="Severe Malaria", treatment_plan="Admit to GMW for IV therapy. Run CBC.",
            icd10_code="B50.9"
        )
        db.add(record)
        db.flush()

        # 4. Generate Lab Order from the Medical Record
        test = LabTest(patient_id=primary_patient.patient_id, record_id=record.record_id, ordered_by=staff["dr.kahura@hospital.com"].user_id, catalog_id=lab_cat.catalog_id, test_name="Complete Blood Count (CBC)", billed_price=1500.0, status="Pending Collection", priority="STAT")
        db.add(test)
        db.flush()

        # ==========================================
        # 7. WARDS & ADMISSIONS
        # ==========================================
        print("   -> Seeding Wards & Bed Allocations...")
        w1 = Ward(name="General Medical Ward", capacity=12)
        w2 = Ward(name="Intensive Care Unit (ICU)", capacity=4)
        db.add_all([w1, w2])
        db.flush()

        b1 = Bed(ward_id=w1.ward_id, bed_number="GMW-01", status="Occupied")
        b2 = Bed(ward_id=w1.ward_id, bed_number="GMW-02", status="Available")
        db.add_all([b1, b2])
        db.flush()

        adm = AdmissionRecord(
            patient_id=primary_patient.patient_id, bed_id=b1.bed_id, admitting_doctor_id=staff["dr.kahura@hospital.com"].user_id,
            primary_diagnosis="Severe Malaria", status="Active"
        )
        db.add(adm)
        db.flush()

        # ==========================================
        # 8. BILLING & INVOICING
        # ==========================================
        print("   -> Seeding Billing Data...")
        inv = Invoice(patient_id=primary_patient.patient_id, appointment_id=appt.appointment_id, total_amount=4000.0, status="Pending", created_by=staff["rec.brian@hospital.com"].user_id)
        db.add(inv)
        db.flush()

        inv_item1 = InvoiceItem(invoice_id=inv.invoice_id, description="Consultation Fee", amount=2500.0, item_type="Consultation")
        inv_item2 = InvoiceItem(invoice_id=inv.invoice_id, description="Complete Blood Count (CBC)", amount=1500.0, item_type="Laboratory", reference_id=test.test_id)
        db.add_all([inv_item1, inv_item2])
        
        # Add a quick Audit Log just to populate the table
        audit = AuditLog(user_id=staff["dr.kahura@hospital.com"].user_id, action="CREATE", entity_type="MedicalRecord", entity_id=str(record.record_id), new_value={"diagnosis": "Severe Malaria"})
        db.add(audit)

        # ==========================================
        # 9. MEDICAL HISTORY (KDPA Compliant)
        # ==========================================
        print("   -> Seeding Medical History & Consents...")
        # Add Consent
        consent = ConsentRecord(
            patient_id=primary_patient.patient_id,
            recorded_by=receptionist_id,
            consent_type="Treatment",
            consent_given=True,
            consent_method="Written",
            notes="Standard outpatient treatment consent signed."
        )
        db.add(consent)
        
        # Add a couple of Medical History Entries
        hist1 = MedicalHistoryEntry(
            patient_id=primary_patient.patient_id,
            recorded_by=staff["dr.kahura@hospital.com"].user_id,
            entry_type="SURGICAL_HISTORY",
            title="Appendectomy",
            description="Laparoscopic appendectomy without complications.",
            event_date="2015",
            severity="N/A",
            status="Resolved",
            is_sensitive=False
        )
        
        hist2 = MedicalHistoryEntry(
            patient_id=primary_patient.patient_id,
            recorded_by=staff["dr.kahura@hospital.com"].user_id,
            entry_type="ALLERGY",
            title="Penicillin Allergy",
            description="Patient develops severe hives and shortness of breath.",
            event_date="Childhood",
            severity="Severe",
            status="Active",
            is_sensitive=False
        )
        
        hist3 = MedicalHistoryEntry(
            patient_id=primary_patient.patient_id,
            recorded_by=staff["dr.kahura@hospital.com"].user_id,
            entry_type="MENTAL_HEALTH",
            title="Anxiety Disorder",
            description="Generalized anxiety disorder, managed with therapy.",
            event_date="2020",
            severity="Moderate",
            status="Managed",
            is_sensitive=True # Sensitive data to test KDPA redaction
        )
        
        db.add_all([hist1, hist2, hist3])
        db.flush()

        db.commit()
        print("✅ SUCCESS: Enterprise Database perfectly seeded and ready for Production Testing!")

    except Exception as e:
        db.rollback()
        print(f"❌ SEEDING FAILED: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_database()
    seed_database()
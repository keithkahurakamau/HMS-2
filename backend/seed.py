import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker

# Ensure the app module can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.database import DefaultSessionLocal as SessionLocal, Base, default_engine as engine
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
from app.models.radiology import RadiologyRequest, RadiologyResult

def reset_database(target_engine):
    """
    DANGER ZONE: Wipes the entire database schema using raw PostgreSQL CASCADE.
    """
    print("🧨 Wiping existing database schema with CASCADE...")
    with target_engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE;"))
        connection.execute(text("CREATE SCHEMA public;"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        connection.commit()
        
    print("🏗️ Rebuilding database schema...")
    Base.metadata.create_all(bind=target_engine)

def seed_database(target_engine, hospital_name="General Hospital", staff_domain="hospital.com"):
    """Seeds a single tenant database with full E2E data."""
    print(f"🌱 Seeding [{hospital_name}] @ {staff_domain}...")
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
    db = TenantSession()
    
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
            "wards:manage", "billing:read", "billing:manage", "radiology:manage"
        ]
        
        perms = {}
        for p_code in permissions_data:
            perm = Permission(codename=p_code, description=f"Allows {p_code}")
            db.add(perm)
            perms[p_code] = perm
        db.flush()

        # 2b. Create Roles and Map Permissions to them
        roles_config = {
            "Admin": [
                "users:manage", "clinical:write", "clinical:read",
                "patients:read", "patients:write", "history:read", "history:manage",
                "pharmacy:manage", "pharmacy:read", "laboratory:manage", "laboratory:read",
                "wards:manage", "billing:read", "billing:manage", "radiology:manage"
            ],
            "Doctor": ["clinical:write", "clinical:read", "patients:read", "patients:write", "pharmacy:read", "laboratory:read", "history:read", "history:manage"],
            "Nurse": ["clinical:read", "patients:read", "wards:manage", "pharmacy:read", "history:read"],
            "Pharmacist": ["pharmacy:manage", "pharmacy:read", "patients:read"],
            "Lab Technician": ["laboratory:manage", "laboratory:read", "patients:read"],
            "Radiologist": ["radiology:manage", "clinical:read", "patients:read"],
            "Receptionist": ["patients:read", "patients:write", "billing:read", "billing:manage"]
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
            {"email": f"admin@{staff_domain}", "full_name": "System Admin", "role": "Admin", "spec": None, "lic": None},
            {"email": f"dr.kahura@{staff_domain}", "full_name": "Dr. James Kahura", "role": "Doctor", "spec": "Internal Medicine", "lic": "MPDB-1001"},
            {"email": f"dr.omondi@{staff_domain}", "full_name": "Dr. Sarah Omondi", "role": "Doctor", "spec": "Pediatrics", "lic": "MPDB-2002"},
            {"email": f"nurse.joy@{staff_domain}", "full_name": "Nurse Joy Wanjiku", "role": "Nurse", "spec": "Ward Matron", "lic": "NCK-8822"},
            {"email": f"pharm.keith@{staff_domain}", "full_name": "Pharm. Keith Kamau", "role": "Pharmacist", "spec": "Clinical Pharmacist", "lic": "PPB-5533"},
            {"email": f"lab.alice@{staff_domain}", "full_name": "Alice Mutua", "role": "Lab Technician", "spec": "Pathology", "lic": "KMLTTB-9911"},
            {"email": f"rad.mwangi@{staff_domain}", "full_name": "Dr. Peter Mwangi", "role": "Radiologist", "spec": "Radiology", "lic": "MPDB-3033"},
            {"email": f"rec.brian@{staff_domain}", "full_name": "Brian Koech", "role": "Receptionist", "spec": None, "lic": None}
        ]
        
        staff = {}
        for u in users_data:
            user = User(
                email=u["email"], 
                full_name=u["full_name"],
                hashed_password=get_password_hash("Password@123"),
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
        
        receptionist_id = staff[f"rec.brian@{staff_domain}"].user_id
        
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
        lab_tests_catalog = [
            LabTestCatalog(test_name="Complete Blood Count (CBC)", category="Hematology", default_specimen_type="Whole Blood", base_price=1500.0),
            LabTestCatalog(test_name="Malaria Rapid Test (RDT)", category="Parasitology", default_specimen_type="Whole Blood", base_price=800.0),
            LabTestCatalog(test_name="Blood Glucose (Fasting)", category="Chemistry", default_specimen_type="Whole Blood", base_price=600.0),
            LabTestCatalog(test_name="Urine Full Analysis", category="Urinalysis", default_specimen_type="Urine", base_price=500.0),
            LabTestCatalog(test_name="HIV 1 & 2 Rapid Test", category="Serology", default_specimen_type="Whole Blood", base_price=1200.0),
        ]
        for ltc in lab_tests_catalog:
            db.add(ltc)
        db.flush()

        bom = LabTestRequiredItem(
            catalog_id=lab_tests_catalog[0].catalog_id,
            inventory_item_id=catalog["CBC Reagent Pack"].item_id,
            item_name="CBC Reagent Pack",
            quantity_required=1
        )
        db.add(bom)
        db.flush()

        # ==========================================
        # 6. WARDS & BEDS (before admissions)
        # ==========================================
        print("   -> Seeding Wards & Bed Allocations...")
        w1 = Ward(name="General Medical Ward", capacity=12)
        w2 = Ward(name="Intensive Care Unit (ICU)", capacity=4)
        w3 = Ward(name="Paediatric Ward", capacity=8)
        db.add_all([w1, w2, w3])
        db.flush()

        beds = [
            Bed(ward_id=w1.ward_id, bed_number="GMW-01", status="Occupied"),
            Bed(ward_id=w1.ward_id, bed_number="GMW-02", status="Available"),
            Bed(ward_id=w1.ward_id, bed_number="GMW-03", status="Available"),
            Bed(ward_id=w2.ward_id, bed_number="ICU-01", status="Occupied"),
            Bed(ward_id=w3.ward_id, bed_number="PAE-01", status="Available"),
        ]
        db.add_all(beds)
        db.flush()
        b_gmw01, b_gmw02, b_gmw03, b_icu01, b_pae01 = beds

        # ==========================================
        # 7. CLINICAL WORKFLOW — MULTI-PATIENT E2E
        # ==========================================
        print("   -> Seeding Clinical Encounters (5 patients)...")

        # --- PATIENT 1: David Kamau — Full E2E: Admission, CBC lab, Paid invoice ---
        p1 = db_patients[0]
        appt1 = Appointment(patient_id=p1.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
                            appointment_date=datetime.now(timezone.utc) - timedelta(days=1), status="Completed")
        db.add(appt1)
        q1 = PatientQueue(patient_id=p1.patient_id, department="Consultation", acuity_level=2,
                          status="Done", assigned_to=staff[f"dr.kahura@{staff_domain}"].user_id)
        db.add(q1)
        rec1 = MedicalRecord(
            patient_id=p1.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
            record_status="Billed", blood_pressure="130/85", heart_rate=92, temperature=39.1,
            chief_complaint="Severe fever and chills for 3 days.",
            diagnosis="Severe Malaria", treatment_plan="Admit to GMW. IV Quinine. CBC STAT.",
            icd10_code="B50.9"
        )
        db.add(rec1)
        db.flush()
        test1 = LabTest(patient_id=p1.patient_id, record_id=rec1.record_id,
                        ordered_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                        catalog_id=lab_tests_catalog[0].catalog_id, test_name="Complete Blood Count (CBC)",
                        billed_price=1500.0, status="Completed", priority="STAT",
                        result_summary="WBC: 12.4, RBC: 3.2, Hb: 9.1g/dL — Anaemia noted.",
                        performed_by_id=staff[f"lab.alice@{staff_domain}"].user_id)
        db.add(test1)
        adm1 = AdmissionRecord(patient_id=p1.patient_id, bed_id=b_gmw01.bed_id,
                               admitting_doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
                               primary_diagnosis="Severe Malaria", status="Active")
        db.add(adm1)
        db.flush()
        inv1 = Invoice(patient_id=p1.patient_id, appointment_id=appt1.appointment_id,
                       total_amount=4000.0, amount_paid=4000.0, status="Paid",
                       created_by=staff[f"rec.brian@{staff_domain}"].user_id)
        db.add(inv1)
        db.flush()
        db.add_all([
            InvoiceItem(invoice_id=inv1.invoice_id, description="Consultation Fee", amount=2500.0, item_type="Consultation"),
            InvoiceItem(invoice_id=inv1.invoice_id, description="Complete Blood Count (CBC)", amount=1500.0, item_type="Laboratory", reference_id=test1.test_id),
            Payment(invoice_id=inv1.invoice_id, amount=4000.0, payment_method="Cash"),
        ])
        db.flush()

        # --- PATIENT 2: Sarah Achieng — Outpatient, Pending lab, Pending billing ---
        p2 = db_patients[1]
        appt2 = Appointment(patient_id=p2.patient_id, doctor_id=staff[f"dr.omondi@{staff_domain}"].user_id,
                            appointment_date=datetime.now(timezone.utc), status="Completed")
        db.add(appt2)
        q2 = PatientQueue(patient_id=p2.patient_id, department="Consultation", acuity_level=3,
                          status="Done", assigned_to=staff[f"dr.omondi@{staff_domain}"].user_id)
        db.add(q2)
        rec2 = MedicalRecord(
            patient_id=p2.patient_id, doctor_id=staff[f"dr.omondi@{staff_domain}"].user_id,
            record_status="Billed", blood_pressure="118/76", heart_rate=88, temperature=37.2,
            chief_complaint="Shortness of breath and wheezing for 2 days.",
            diagnosis="Acute Asthma Exacerbation", treatment_plan="Salbutamol nebulization. Peak flow monitoring.",
            icd10_code="J45.901"
        )
        db.add(rec2)
        db.flush()
        test2 = LabTest(patient_id=p2.patient_id, record_id=rec2.record_id,
                        ordered_by=staff[f"dr.omondi@{staff_domain}"].user_id,
                        catalog_id=lab_tests_catalog[3].catalog_id, test_name="Urine Full Analysis",
                        billed_price=500.0, status="Pending Collection", priority="Routine")
        db.add(test2)
        db.flush()
        inv2 = Invoice(patient_id=p2.patient_id, appointment_id=appt2.appointment_id,
                       total_amount=3000.0, status="Pending",
                       created_by=staff[f"rec.brian@{staff_domain}"].user_id)
        db.add(inv2)
        db.flush()
        db.add_all([
            InvoiceItem(invoice_id=inv2.invoice_id, description="Consultation Fee", amount=2500.0, item_type="Consultation"),
            InvoiceItem(invoice_id=inv2.invoice_id, description="Urine Full Analysis", amount=500.0, item_type="Laboratory", reference_id=test2.test_id),
        ])
        db.flush()

        # --- PATIENT 3: Ali Mohammed — Pending M-Pesa payment (tests M-Pesa ledger) ---
        p3 = db_patients[2]
        appt3 = Appointment(patient_id=p3.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
                            appointment_date=datetime.now(timezone.utc) - timedelta(hours=2), status="Completed")
        db.add(appt3)
        rec3 = MedicalRecord(
            patient_id=p3.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
            record_status="Billed", blood_pressure="145/92", heart_rate=78, temperature=36.8,
            chief_complaint="Elevated blood sugar, dizziness.",
            diagnosis="Type 2 Diabetes — Uncontrolled", treatment_plan="Adjust Metformin dose. Blood glucose monitoring.",
            icd10_code="E11.9"
        )
        db.add(rec3)
        db.flush()
        test3 = LabTest(patient_id=p3.patient_id, record_id=rec3.record_id,
                        ordered_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                        catalog_id=lab_tests_catalog[2].catalog_id, test_name="Blood Glucose (Fasting)",
                        billed_price=600.0, status="Completed", priority="Routine",
                        result_summary="Fasting glucose: 14.2 mmol/L — High",
                        performed_by_id=staff[f"lab.alice@{staff_domain}"].user_id)
        db.add(test3)
        db.flush()
        inv3 = Invoice(patient_id=p3.patient_id, appointment_id=appt3.appointment_id,
                       total_amount=3100.0, status="Pending M-Pesa",
                       created_by=staff[f"rec.brian@{staff_domain}"].user_id)
        db.add(inv3)
        db.flush()
        db.add_all([
            InvoiceItem(invoice_id=inv3.invoice_id, description="Consultation Fee", amount=2500.0, item_type="Consultation"),
            InvoiceItem(invoice_id=inv3.invoice_id, description="Blood Glucose (Fasting)", amount=600.0, item_type="Laboratory", reference_id=test3.test_id),
        ])
        db.flush()

        # --- PATIENT 4: Grace Wanjiru — ICU Admission ---
        p4 = db_patients[3]
        appt4 = Appointment(patient_id=p4.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
                            appointment_date=datetime.now(timezone.utc) - timedelta(days=2), status="Completed")
        db.add(appt4)
        rec4 = MedicalRecord(
            patient_id=p4.patient_id, doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
            record_status="Admitted", blood_pressure="180/110", heart_rate=110, temperature=38.5,
            chief_complaint="Hypertensive crisis, severe headache.",
            diagnosis="Hypertensive Emergency", treatment_plan="ICU admission. IV Labetalol. Continuous monitoring.",
            icd10_code="I16.1"
        )
        db.add(rec4)
        db.flush()
        adm4 = AdmissionRecord(patient_id=p4.patient_id, bed_id=b_icu01.bed_id,
                               admitting_doctor_id=staff[f"dr.kahura@{staff_domain}"].user_id,
                               primary_diagnosis="Hypertensive Emergency", status="Active")
        db.add(adm4)
        db.flush()

        # --- PATIENT 5: Faith Mutua (Paediatric) — Waiting in queue ---
        p5 = db_patients[5]
        appt5 = Appointment(patient_id=p5.patient_id, doctor_id=staff[f"dr.omondi@{staff_domain}"].user_id,
                            appointment_date=datetime.now(timezone.utc) + timedelta(hours=1), status="Confirmed")
        db.add(appt5)
        q5 = PatientQueue(patient_id=p5.patient_id, department="Paediatrics", acuity_level=3,
                          status="Waiting", assigned_to=staff[f"dr.omondi@{staff_domain}"].user_id)
        db.add(q5)
        db.flush()

        # ==========================================
        # 8. MEDICAL HISTORY & CONSENTS (3 patients)
        # ==========================================
        print("   -> Seeding Medical History & Consents...")
        for pid in [p1.patient_id, p2.patient_id, p3.patient_id]:
            db.add(ConsentRecord(
                patient_id=pid, recorded_by=receptionist_id,
                consent_type="Treatment", consent_given=True,
                consent_method="Written", notes="Standard outpatient treatment consent."
            ))
        db.flush()

        db.add_all([
            MedicalHistoryEntry(patient_id=p1.patient_id, recorded_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                                entry_type="SURGICAL_HISTORY", title="Appendectomy",
                                description="Laparoscopic appendectomy 2015, no complications.",
                                event_date="2015", severity="N/A", status="Resolved", is_sensitive=False),
            MedicalHistoryEntry(patient_id=p1.patient_id, recorded_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                                entry_type="ALLERGY", title="Penicillin Allergy",
                                description="Severe hives and anaphylaxis risk.",
                                event_date="Childhood", severity="Severe", status="Active", is_sensitive=False),
            MedicalHistoryEntry(patient_id=p1.patient_id, recorded_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                                entry_type="MENTAL_HEALTH", title="Anxiety Disorder",
                                description="Generalised anxiety, managed with therapy.",
                                event_date="2020", severity="Moderate", status="Managed", is_sensitive=True),
            MedicalHistoryEntry(patient_id=p2.patient_id, recorded_by=staff[f"dr.omondi@{staff_domain}"].user_id,
                                entry_type="CHRONIC_CONDITION", title="Bronchial Asthma",
                                description="Diagnosed 2018. Salbutamol PRN.",
                                event_date="2018", severity="Moderate", status="Managed", is_sensitive=False),
            MedicalHistoryEntry(patient_id=p3.patient_id, recorded_by=staff[f"dr.kahura@{staff_domain}"].user_id,
                                entry_type="CHRONIC_CONDITION", title="Type 2 Diabetes Mellitus",
                                description="Diagnosed 2019. Metformin 500mg BD.",
                                event_date="2019", severity="Moderate", status="Managed", is_sensitive=False),
        ])
        db.flush()

        # ==========================================
        # 9. AUDIT LOGS (Seed a realistic trail)
        # ==========================================
        print("   -> Seeding Audit Trail...")
        db.add_all([
            AuditLog(user_id=staff[f"dr.kahura@{staff_domain}"].user_id, action="CREATE",
                     entity_type="MedicalRecord", entity_id=str(rec1.record_id),
                     new_value={"diagnosis": "Severe Malaria"}),
            AuditLog(user_id=staff[f"rec.brian@{staff_domain}"].user_id, action="CREATE",
                     entity_type="Invoice", entity_id=str(inv1.invoice_id),
                     new_value={"total": 4000.0, "patient_id": p1.patient_id}),
            AuditLog(user_id=staff[f"rec.brian@{staff_domain}"].user_id, action="UPDATE",
                     entity_type="Invoice", entity_id=str(inv1.invoice_id),
                     old_value={"status": "Pending"}, new_value={"status": "Paid"}),
        ])
        db.flush()

        db.commit()
        print("")
        print("✅ SUCCESS: Full E2E database seeded!")
        print("")
        print(f"   📋 Test Credentials (password: Password@123) — domain: {staff_domain}")
        print(f"   ┌─────────────────────────────────────────────────┐")
        print(f"   │  admin@{staff_domain:30s} → Admin              │")
        print(f"   │  dr.kahura@{staff_domain:26s} → Doctor             │")
        print(f"   │  dr.omondi@{staff_domain:26s} → Doctor (Paeds)     │")
        print(f"   │  nurse.joy@{staff_domain:26s} → Nurse              │")
        print(f"   │  pharm.keith@{staff_domain:24s} → Pharmacist         │")
        print(f"   │  lab.alice@{staff_domain:26s} → Lab Technician     │")
        print(f"   │  rec.brian@{staff_domain:26s} → Receptionist       │")
        print(f"   └─────────────────────────────────────────────────┘")
        print("")
        print("   🏥 Test Scenarios Ready:")
        print("   • Patient 1 (Kamau)     — Admitted GMW, CBC Completed, Invoice PAID ✅")
        print("   • Patient 2 (Achieng)   — Outpatient, Lab Pending Collection, Invoice Pending 🟡")
        print("   • Patient 3 (Mohammed)  — Outpatient, Lab Done, Invoice Pending M-Pesa 📱")
        print("   • Patient 4 (Wanjiru)   — ICU Admitted, Hypertensive Emergency 🔴")
        print("   • Patient 5 (Mutua)     — In Paediatric Queue, Appointment booked 🟢")



    except Exception as e:
        db.rollback()
        print(f"❌ SEEDING FAILED: {e}")
    finally:
        db.close()

def create_db_if_not_exists(db_name: str, base_url: str):
    """Creates a PostgreSQL database if it doesn't already exist."""
    admin_engine = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"   ✅ Database '{db_name}' created.")
        else:
            print(f"   ⏩ Database '{db_name}' already exists.")
    admin_engine.dispose()


def seed_master_db(master_engine):
    """Seeds the central hms_master database with the superadmin and tenant registry."""
    from app.models.master import Tenant, SuperAdmin
    
    print("🌱 Seeding Master Registry (hms_master)...")
    Base.metadata.create_all(bind=master_engine)
    
    MasterSession = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)
    db = MasterSession()
    
    try:
        # 1. Create or update Superadmin
        existing_admin = db.query(SuperAdmin).filter(SuperAdmin.email == "superadmin@hms.co.ke").first()
        if not existing_admin:
            sa = SuperAdmin(
                email="superadmin@hms.co.ke",
                full_name="HMS Platform Superadmin",
                hashed_password=get_password_hash("SuperAdmin@2026"),
                is_active=True
            )
            db.add(sa)
            print("   → Superadmin account created.")
        else:
            print("   → Superadmin account already exists.")
        
        # 2. Register Tenants
        tenants_config = [
            {"name": "Mayo Clinic Nairobi", "domain": "mayoclinic.hms.co.ke", "db_name": "mayoclinic_db", "theme_color": "blue", "is_premium": True, "staff_domain": "mayoclinic.com"},
            {"name": "St. John's Hospital", "domain": "stjohns.hms.co.ke", "db_name": "stjohns_db", "theme_color": "emerald", "is_premium": False, "staff_domain": "stjohns.com"},
        ]
        
        registered = []
        for t in tenants_config:
            existing = db.query(Tenant).filter(Tenant.db_name == t["db_name"]).first()
            if not existing:
                tenant = Tenant(
                    name=t["name"], domain=t["domain"], db_name=t["db_name"],
                    theme_color=t["theme_color"], is_premium=t["is_premium"]
                )
                db.add(tenant)
                print(f"   → Registered tenant: {t['name']}")
            else:
                print(f"   → Tenant '{t['name']}' already registered.")
            registered.append(t)
        
        db.commit()
        print("✅ Master registry seeded.\n")
        return registered
        
    except Exception as e:
        db.rollback()
        print(f"❌ MASTER SEED FAILED: {e}")
        return []
    finally:
        db.close()


if __name__ == "__main__":
    from app.config.settings import settings
    base_url = settings.DATABASE_URL.rsplit('/', 1)[0]

    print("\n" + "="*60)
    print("  👑 HMS PLATFORM SEED ORCHESTRATOR")
    print("="*60)
    
    # ========================================
    # PHASE 1: Master Database (hms_master)
    # ========================================
    print("\n── PHASE 1: Master Registry ──")
    create_db_if_not_exists("hms_master", base_url)
    m_engine = create_engine(f"{base_url}/hms_master")
    tenants_to_seed = seed_master_db(m_engine)
    m_engine.dispose()

    print(f"\n   👑 Superadmin Login:")
    print(f"   Email: superadmin@hms.co.ke")
    print(f"   Password: SuperAdmin@2026\n")

    # ========================================
    # PHASE 2: Tenant Databases (auto-loop)
    # ========================================
    print("── PHASE 2: Tenant Provisioning ──\n")
    for i, t in enumerate(tenants_to_seed, 1):
        print("=" * 60)
        print(f"  🏥 TENANT {i}: {t['name']}")
        print("=" * 60)
        create_db_if_not_exists(t["db_name"], base_url)
        t_engine = create_engine(f"{base_url}/{t['db_name']}")
        reset_database(t_engine)
        seed_database(t_engine, hospital_name=t["name"], staff_domain=t["staff_domain"])
        t_engine.dispose()
        print()

    print("=" * 60)
    print("  🎉 ALL DATABASES SEEDED SUCCESSFULLY")
    print("=" * 60)
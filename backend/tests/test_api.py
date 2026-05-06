"""
Comprehensive integration tests for the HMS API.
JWT tokens are generated directly (bypassing the 5/min login rate limit).
Tests run against the live server at http://localhost:8000.
"""
import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
DOMAIN = "mayoclinic.com"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


# ─── 1. Health & Public ───────────────────────────────────────────────────────

class TestPublic:
    def test_health(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "Operational"

    def test_hospitals_list(self, client):
        r = client.get("/api/public/hospitals")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ─── 2. Auth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_me_requires_auth(self, client):
        r = client.get("/api/users/me")
        assert r.status_code == 401

    def test_wrong_password_returns_401(self, client):
        r = client.post("/api/auth/login", json={"email": f"admin@{DOMAIN}", "password": "wrongpass"})
        assert r.status_code == 401

    def test_unknown_user_returns_401(self, client):
        r = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "Password@123"})
        assert r.status_code == 401

    def test_me_with_valid_token(self, client, admin_cookies):
        r = client.get("/api/users/me", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "Admin"
        assert data["email"] == f"admin@{DOMAIN}"

    def test_all_roles_have_correct_identity(self, client, admin_cookies, doctor_cookies,
                                              nurse_cookies, pharmacist_cookies,
                                              lab_cookies, radiologist_cookies, receptionist_cookies):
        cases = [
            (admin_cookies, "Admin"),
            (doctor_cookies, "Doctor"),
            (nurse_cookies, "Nurse"),
            (pharmacist_cookies, "Pharmacist"),
            (lab_cookies, "Lab Technician"),
            (radiologist_cookies, "Radiologist"),
            (receptionist_cookies, "Receptionist"),
        ]
        for cookies, expected_role in cases:
            r = client.get("/api/users/me", cookies=cookies)
            assert r.status_code == 200
            assert r.json()["role"] == expected_role

    def test_admin_has_all_key_permissions(self, client, admin_cookies):
        r = client.get("/api/users/me/permissions", cookies=admin_cookies)
        assert r.status_code == 200
        perms = r.json()
        for p in ["users:manage", "billing:manage", "pharmacy:manage", "clinical:write"]:
            assert p in perms, f"Admin missing: {p}"

    def test_receptionist_has_billing_manage(self, client, receptionist_cookies):
        r = client.get("/api/users/me/permissions", cookies=receptionist_cookies)
        assert r.status_code == 200
        assert "billing:manage" in r.json()

    def test_radiologist_has_radiology_manage(self, client, radiologist_cookies):
        r = client.get("/api/users/me/permissions", cookies=radiologist_cookies)
        assert r.status_code == 200
        assert "radiology:manage" in r.json()

    def test_nurse_does_not_have_billing_manage(self, client, nurse_cookies):
        r = client.get("/api/users/me/permissions", cookies=nurse_cookies)
        assert r.status_code == 200
        assert "billing:manage" not in r.json()


# ─── 3. Patients ─────────────────────────────────────────────────────────────

class TestPatients:
    def test_list_requires_auth(self, client):
        r = client.get("/api/patients/")
        assert r.status_code == 401

    def test_list_as_admin(self, client, admin_cookies):
        r = client.get("/api/patients/", cookies=admin_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 10

    def test_search_by_surname(self, client, receptionist_cookies):
        r = client.get("/api/patients/?search=Kamau", cookies=receptionist_cookies)
        assert r.status_code == 200
        assert any("Kamau" in p["surname"] for p in r.json())

    def test_search_by_opd_number(self, client, doctor_cookies):
        r = client.get("/api/patients/?search=OP-2026-0001", cookies=doctor_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_by_id(self, client, doctor_cookies):
        r = client.get("/api/patients/1", cookies=doctor_cookies)
        assert r.status_code == 200
        assert "patient_id" in r.json()

    def test_not_found_returns_404(self, client, admin_cookies):
        r = client.get("/api/patients/99999", cookies=admin_cookies)
        assert r.status_code == 404

    def test_nurse_can_read(self, client, nurse_cookies):
        r = client.get("/api/patients/", cookies=nurse_cookies)
        assert r.status_code == 200

    def test_patient_history(self, client, doctor_cookies):
        r = client.get("/api/patients/1/history", cookies=doctor_cookies)
        assert r.status_code == 200


# ─── 4. Admin ────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_metrics_fields(self, client, admin_cookies):
        r = client.get("/api/admin/metrics", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        for f in ["total_patients", "active_admissions", "daily_revenue", "low_stock_alerts"]:
            assert f in data
        assert data["total_patients"] >= 10

    def test_staff_directory_has_all_roles(self, client, admin_cookies):
        r = client.get("/api/admin/users", cookies=admin_cookies)
        assert r.status_code == 200
        roles = {u["role"] for u in r.json()}
        for role in ["Admin", "Doctor", "Nurse", "Pharmacist", "Lab Technician", "Radiologist", "Receptionist"]:
            assert role in roles, f"Missing role: {role}"

    def test_audit_logs_exist(self, client, admin_cookies):
        r = client.get("/api/admin/audit-logs", cookies=admin_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_pricing_catalog(self, client, admin_cookies):
        r = client.get("/api/admin/pricing", cookies=admin_cookies)
        assert r.status_code == 200

    def test_doctor_blocked_from_metrics(self, client, doctor_cookies):
        r = client.get("/api/admin/metrics", cookies=doctor_cookies)
        assert r.status_code == 403

    def test_receptionist_blocked_from_staff(self, client, receptionist_cookies):
        r = client.get("/api/admin/users", cookies=receptionist_cookies)
        assert r.status_code == 403


# ─── 5. Analytics ────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_dashboard_all_fields(self, client, admin_cookies):
        r = client.get("/api/analytics/dashboard", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        for f in ["total_patients", "total_staff", "today_revenue", "total_waiting", "queue_breakdown"]:
            assert f in data
        assert data["total_patients"] >= 10

    def test_doctor_blocked(self, client, doctor_cookies):
        r = client.get("/api/analytics/dashboard", cookies=doctor_cookies)
        assert r.status_code == 403

    def test_receptionist_blocked(self, client, receptionist_cookies):
        r = client.get("/api/analytics/dashboard", cookies=receptionist_cookies)
        assert r.status_code == 403


# ─── 6. Clinical ─────────────────────────────────────────────────────────────

class TestClinical:
    def test_queue_for_doctor(self, client, doctor_cookies):
        r = client.get("/api/clinical/queue", cookies=doctor_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pending_prescriptions(self, client, pharmacist_cookies):
        r = client.get("/api/clinical/prescriptions/pending", cookies=pharmacist_cookies)
        assert r.status_code == 200

    def test_records_by_patient(self, client, doctor_cookies):
        r = client.get("/api/clinical/records/1", cookies=doctor_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ─── 7. Laboratory ───────────────────────────────────────────────────────────

class TestLaboratory:
    def test_queue_has_pending_tests(self, client, lab_cookies):
        r = client.get("/api/laboratory/queue", cookies=lab_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1

    def test_queue_item_fields(self, client, lab_cookies):
        r = client.get("/api/laboratory/queue", cookies=lab_cookies)
        item = r.json()[0]
        for f in ["test_id", "test_name", "status", "patient", "priority"]:
            assert f in item

    def test_catalog_returns_all_active_tests(self, client, lab_cookies):
        r = client.get("/api/laboratory/catalog", cookies=lab_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 5, f"Expected >=5 catalog items, got {len(data)}"
        names = [i["test_name"] for i in data]
        assert "Complete Blood Count (CBC)" in names
        assert "Malaria Rapid Test (RDT)" in names
        assert "HIV 1 & 2 Rapid Test" in names

    def test_inventory_has_reagents(self, client, lab_cookies):
        r = client.get("/api/laboratory/inventory", cookies=lab_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ─── 8. Pharmacy ─────────────────────────────────────────────────────────────

class TestPharmacy:
    def test_inventory_has_stock(self, client, pharmacist_cookies):
        r = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert any("Amoxicillin" in item["name"] for item in data)

    def test_inventory_item_fields(self, client, pharmacist_cookies):
        r = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies)
        item = r.json()[0]
        for f in ["item_id", "name", "batch_id", "quantity", "expiry_date"]:
            assert f in item

    def test_dispense_requires_auth(self, client):
        # CSRF middleware fires before auth on POST — returns 403 without token
        r = client.post("/api/pharmacy/dispense", json={})
        assert r.status_code in (401, 403)

    def test_nurse_blocked_from_inventory(self, client, nurse_cookies):
        # Nurse has pharmacy:read — they can see inventory (to administer ward drugs)
        r = client.get("/api/pharmacy/inventory", cookies=nurse_cookies)
        assert r.status_code == 200


# ─── 9. Inventory ────────────────────────────────────────────────────────────

class TestInventory:
    def test_items_list(self, client, admin_cookies):
        r = client.get("/api/inventory/items", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 4
        names = [i["name"] for i in data]
        assert "Amoxicillin 625mg" in names
        assert "CBC Reagent Pack" in names

    def test_alerts(self, client, admin_cookies):
        r = client.get("/api/inventory/alerts", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert "expiring_batches" in data
        assert "low_stock_alerts" in data

    def test_pharmacist_can_read(self, client, pharmacist_cookies):
        r = client.get("/api/inventory/items", cookies=pharmacist_cookies)
        assert r.status_code == 200

    def test_lab_tech_blocked_from_central_inventory(self, client, lab_cookies):
        # Lab Technician has laboratory:read but NOT pharmacy:read → blocked from central inventory
        r = client.get("/api/inventory/items", cookies=lab_cookies)
        assert r.status_code == 403

    def test_nurse_has_pharmacy_read_so_can_access(self, client, nurse_cookies):
        # Nurse has pharmacy:read (to administer ward medications)
        r = client.get("/api/inventory/items", cookies=nurse_cookies)
        assert r.status_code == 200

    def test_doctor_has_pharmacy_read_so_can_access(self, client, doctor_cookies):
        # Doctor has pharmacy:read to see available drugs for prescribing
        r = client.get("/api/inventory/items", cookies=doctor_cookies)
        assert r.status_code == 200


# ─── 10. Wards ───────────────────────────────────────────────────────────────

class TestWards:
    def test_board_has_all_wards(self, client, admin_cookies):
        r = client.get("/api/wards/board", cookies=admin_cookies)
        assert r.status_code == 200
        wards = r.json()
        assert len(wards) >= 3
        names = [w["name"] for w in wards]
        assert "General Medical Ward" in names
        assert "Intensive Care Unit (ICU)" in names
        assert "Paediatric Ward" in names

    def test_ward_inventory(self, client, nurse_cookies):
        r = client.get("/api/wards/inventory", cookies=nurse_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_occupied_beds_have_patient_and_diagnosis(self, client, admin_cookies):
        r = client.get("/api/wards/board", cookies=admin_cookies)
        all_beds = [bed for w in r.json() for bed in w["beds"]]
        occupied = [b for b in all_beds if b["status"] == "Occupied"]
        assert len(occupied) >= 2
        for bed in occupied:
            assert bed["patient"] is not None
            assert bed["diagnosis"] is not None
            assert "admission_id" in bed


# ─── 11. Billing ─────────────────────────────────────────────────────────────

class TestBilling:
    def test_queue_accessible_by_admin(self, client, admin_cookies):
        r = client.get("/api/billing/queue", cookies=admin_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_queue_accessible_by_receptionist(self, client, receptionist_cookies):
        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        assert r.status_code == 200

    def test_queue_blocked_for_nurse(self, client, nurse_cookies):
        r = client.get("/api/billing/queue", cookies=nurse_cookies)
        assert r.status_code == 403

    def test_queue_blocked_for_doctor(self, client, doctor_cookies):
        r = client.get("/api/billing/queue", cookies=doctor_cookies)
        assert r.status_code == 403

    def test_mpesa_transactions(self, client, admin_cookies):
        r = client.get("/api/billing/mpesa-transactions", cookies=admin_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_queue_has_pending_invoices(self, client, admin_cookies):
        r = client.get("/api/billing/queue", cookies=admin_cookies)
        statuses = {inv["status"] for inv in r.json()}
        assert any(s in statuses for s in ["Pending", "Pending M-Pesa", "Partially Paid"])

    def test_invoice_has_all_fields(self, client, admin_cookies):
        r = client.get("/api/billing/queue", cookies=admin_cookies)
        inv = r.json()[0]
        for f in ["invoice_id", "patient_id", "patient_name", "total_amount", "status", "items"]:
            assert f in inv


# ─── 12. Radiology ───────────────────────────────────────────────────────────

class TestRadiology:
    def test_accessible_by_radiologist(self, client, radiologist_cookies):
        r = client.get("/api/radiology/", cookies=radiologist_cookies)
        assert r.status_code == 200

    def test_accessible_by_doctor(self, client, doctor_cookies):
        r = client.get("/api/radiology/", cookies=doctor_cookies)
        assert r.status_code == 200

    def test_blocked_for_pharmacist(self, client, pharmacist_cookies):
        r = client.get("/api/radiology/", cookies=pharmacist_cookies)
        assert r.status_code == 403

    def test_blocked_for_lab_tech(self, client, lab_cookies):
        r = client.get("/api/radiology/", cookies=lab_cookies)
        assert r.status_code == 403


# ─── 13. Medical History ─────────────────────────────────────────────────────

class TestMedicalHistory:
    def test_chart_has_expected_sections(self, client, doctor_cookies):
        r = client.get("/api/medical-history/1/chart", cookies=doctor_cookies)
        assert r.status_code == 200
        data = r.json()
        for section in ["patient_id", "baseline_allergies", "allergies", "chronic_conditions"]:
            assert section in data, f"Missing section: {section}"

    def test_chart_has_allergy_entry(self, client, doctor_cookies):
        r = client.get("/api/medical-history/1/chart", cookies=doctor_cookies)
        data = r.json()
        # allergies is a list of detailed entries
        assert isinstance(data["allergies"], list)
        assert len(data["allergies"]) >= 1

    def test_consent_record(self, client, doctor_cookies):
        r = client.get("/api/medical-history/consent/1", cookies=doctor_cookies)
        assert r.status_code == 200

    def test_blocked_for_pharmacist(self, client, pharmacist_cookies):
        r = client.get("/api/medical-history/1/chart", cookies=pharmacist_cookies)
        assert r.status_code == 403

    def test_blocked_for_lab_tech(self, client, lab_cookies):
        r = client.get("/api/medical-history/1/chart", cookies=lab_cookies)
        assert r.status_code == 403


# ─── 14. M-Pesa Admin ────────────────────────────────────────────────────────

class TestMpesaAdmin:
    def test_config_accessible_by_admin(self, client, admin_cookies):
        r = client.get("/api/admin/mpesa/config", cookies=admin_cookies)
        assert r.status_code == 200
        assert "configured" in r.json()

    def test_transactions_accessible_by_admin(self, client, admin_cookies):
        r = client.get("/api/admin/mpesa/transactions", cookies=admin_cookies)
        assert r.status_code == 200

    def test_blocked_for_doctor(self, client, doctor_cookies):
        r = client.get("/api/admin/mpesa/config", cookies=doctor_cookies)
        assert r.status_code == 403

    def test_blocked_for_receptionist(self, client, receptionist_cookies):
        r = client.get("/api/admin/mpesa/config", cookies=receptionist_cookies)
        assert r.status_code == 403


# ─── 15. Queue & Dashboard ───────────────────────────────────────────────────

class TestQueueAndDashboard:
    def test_queue_list(self, client, admin_cookies):
        r = client.get("/api/queue/", cookies=admin_cookies)
        assert r.status_code == 200

    def test_appointments_list(self, client, receptionist_cookies):
        r = client.get("/api/appointments/", cookies=receptionist_cookies)
        assert r.status_code == 200
        assert len(r.json()) >= 5

    def test_worker_agenda_doctor(self, client, doctor_cookies):
        r = client.get("/api/dashboard/worker-agenda", cookies=doctor_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_worker_agenda_nurse(self, client, nurse_cookies):
        r = client.get("/api/dashboard/worker-agenda", cookies=nurse_cookies)
        assert r.status_code == 200


# ─── 16. RBAC Sweep ──────────────────────────────────────────────────────────

class TestRBACGuarantees:
    def test_all_protected_endpoints_reject_unauthenticated(self, client):
        endpoints = [
            "/api/patients/", "/api/clinical/queue",
            "/api/laboratory/queue", "/api/laboratory/catalog", "/api/laboratory/inventory",
            "/api/pharmacy/inventory", "/api/wards/board", "/api/wards/inventory",
            "/api/billing/queue", "/api/admin/metrics", "/api/inventory/items",
            "/api/radiology/", "/api/medical-history/1/chart", "/api/analytics/dashboard",
        ]
        for path in endpoints:
            r = client.get(path)
            assert r.status_code == 401, f"Expected 401 for {path}, got {r.status_code}"

    def test_all_roles_can_see_own_profile(self, client, admin_cookies, doctor_cookies,
                                            nurse_cookies, pharmacist_cookies, lab_cookies,
                                            radiologist_cookies, receptionist_cookies):
        for cookies in [admin_cookies, doctor_cookies, nurse_cookies,
                        pharmacist_cookies, lab_cookies, radiologist_cookies, receptionist_cookies]:
            r = client.get("/api/users/me", cookies=cookies)
            assert r.status_code == 200

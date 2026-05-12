"""
Radiology module integration tests — exam catalog + request/result flow.
"""
import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


@pytest.fixture(scope="module")
def rad_patient_id(client, doctor_cookies):
    rows = client.get("/api/patients/?search=Otieno", cookies=doctor_cookies).json()
    assert rows, "Demo seed must include at least one Otieno patient"
    return rows[0]["patient_id"]


# ─── Catalog CRUD ───────────────────────────────────────────────────────────

class TestRadiologyCatalog:
    def test_list_catalog(self, client, doctor_cookies):
        r = client.get("/api/radiology/catalog", cookies=doctor_cookies)
        assert r.status_code == 200
        names = {row["exam_name"] for row in r.json()}
        assert "Chest X-Ray (PA)" in names

    def test_admin_creates_and_updates_exam(self, client, admin_cookies):
        payload = {
            "exam_name": "MRI Lumbar Spine (auto)",
            "modality": "MRI",
            "body_part": "Lumbar spine",
            "base_price": 18000,
            "requires_prep": False,
            "requires_contrast": False,
            "default_findings_template": "Vertebral alignment is normal.",
            "is_active": True,
        }
        created = client.post("/api/radiology/catalog", cookies=admin_cookies, json=payload)
        assert created.status_code == 200, created.text
        catalog_id = created.json()["catalog_id"]
        try:
            patched = client.patch(f"/api/radiology/catalog/{catalog_id}",
                                    cookies=admin_cookies,
                                    json={"base_price": 19500, "requires_prep": True})
            assert patched.status_code == 200
            assert float(patched.json()["base_price"]) == 19500
            assert patched.json()["requires_prep"] is True
        finally:
            client.delete(f"/api/radiology/catalog/{catalog_id}", cookies=admin_cookies)

    def test_receptionist_cannot_create_exam(self, client, receptionist_cookies):
        r = client.post("/api/radiology/catalog", cookies=receptionist_cookies, json={
            "exam_name": "Should not exist", "modality": "X-Ray", "base_price": 100,
        })
        assert r.status_code == 403


# ─── Request + result lifecycle ─────────────────────────────────────────────

class TestRadiologyFlow:
    def test_create_request_via_catalog_locks_price(self, client, doctor_cookies, rad_patient_id):
        cat = client.get("/api/radiology/catalog", cookies=doctor_cookies).json()
        chest = next(c for c in cat if c["exam_name"] == "Chest X-Ray (PA)")

        r = client.post("/api/radiology/", cookies=doctor_cookies, json={
            "patient_id": rad_patient_id,
            "catalog_id": chest["catalog_id"],
            "exam_type": chest["exam_name"],
            "clinical_notes": "Persistent cough x 2 weeks.",
            "priority": "Routine",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "Pending"
        assert body["priority"] == "Routine"
        assert body["billed_price"] is not None
        assert float(body["billed_price"]) == float(chest["base_price"])

    def test_create_request_freeform_no_catalog(self, client, doctor_cookies, rad_patient_id):
        r = client.post("/api/radiology/", cookies=doctor_cookies, json={
            "patient_id": rad_patient_id,
            "exam_type": "Pelvic ad-hoc",
            "clinical_notes": "Trauma assessment",
            "priority": "Urgent",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["catalog_id"] is None
        assert body["exam_type"] == "Pelvic ad-hoc"

    def test_status_progression_and_result(self, client, doctor_cookies, radiologist_cookies, rad_patient_id):
        created = client.post("/api/radiology/", cookies=doctor_cookies, json={
            "patient_id": rad_patient_id,
            "exam_type": "Chest X-Ray (PA)",
            "priority": "Routine",
        }).json()
        request_id = created["request_id"]

        ack = client.put(f"/api/radiology/{request_id}/status",
                         cookies=radiologist_cookies, json={"status": "In Progress"})
        assert ack.status_code == 200
        assert ack.json()["status"] == "In Progress"

        result = client.post(f"/api/radiology/{request_id}/result",
                             cookies=radiologist_cookies, json={
                                 "findings": "Clear lung fields. No focal consolidation.",
                                 "conclusion": "Normal chest radiograph.",
                                 "contrast_used": None,
                             })
        assert result.status_code == 200, result.text
        assert result.json()["findings"].startswith("Clear")

        # Second result on same request should be rejected.
        dup = client.post(f"/api/radiology/{request_id}/result",
                          cookies=radiologist_cookies, json={
                              "findings": "duplicate", "conclusion": "duplicate"
                          })
        assert dup.status_code == 400

    def test_filter_by_status(self, client, doctor_cookies):
        r = client.get("/api/radiology/?status=Pending&limit=5", cookies=doctor_cookies)
        assert r.status_code == 200
        for row in r.json():
            assert row["status"] == "Pending"

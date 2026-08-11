"""Clinical file attachments: RBAC clinical:read/write, upload→list→download→
delete, size cap. Live server."""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}

DATA_URL = "data:text/plain;base64,SGVsbG8gRG9jdG9yVjI="  # "Hello DoctorV2"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/clinical-files?patient_id=1")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    s = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"File{s}", "other_names": "Attach Test", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": f"+2547{s[:8]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


class TestAccess:
    def test_unauthenticated_401(self, client):
        assert client.get("/api/clinical-files?patient_id=1").status_code == 401

    def test_nurse_can_read(self, client, nurse_cookies):
        assert client.get("/api/clinical-files?patient_id=1", cookies=nurse_cookies).status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        assert client.get("/api/clinical-files?patient_id=1", cookies=receptionist_cookies).status_code == 403

    def test_nurse_cannot_upload(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-files", cookies=nurse_cookies, json={
            "patient_id": pid, "filename": "x.txt", "data": DATA_URL})
        assert r.status_code == 403


class TestLifecycle:
    def test_upload_list_download_delete(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-files", cookies=doctor_cookies, json={
            "patient_id": pid, "filename": "referral.txt", "mime": "text/plain", "data": DATA_URL})
        assert r.status_code == 200, r.text
        fid = r.json()["file_id"]
        assert r.json()["size_bytes"] == len(DATA_URL)

        # list returns metadata only (no data blob)
        rows = client.get(f"/api/clinical-files?patient_id={pid}", cookies=doctor_cookies).json()
        row = next(f for f in rows if f["file_id"] == fid)
        assert row["filename"] == "referral.txt" and "data" not in row

        # download returns the data
        got = client.get(f"/api/clinical-files/{fid}", cookies=doctor_cookies).json()
        assert got["data"] == DATA_URL

        # delete
        assert client.delete(f"/api/clinical-files/{fid}", cookies=doctor_cookies).status_code == 200
        assert all(f["file_id"] != fid for f in
                   client.get(f"/api/clinical-files?patient_id={pid}", cookies=doctor_cookies).json())

    def test_unknown_patient_404(self, client, doctor_cookies):
        r = client.post("/api/clinical-files", cookies=doctor_cookies, json={
            "patient_id": 99999999, "filename": "x.txt", "data": DATA_URL})
        assert r.status_code == 404

    def test_oversized_413(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        big = "data:text/plain;base64," + ("A" * 2_800_001)
        r = client.post("/api/clinical-files", cookies=doctor_cookies, json={
            "patient_id": pid, "filename": "big.bin", "data": big})
        assert r.status_code == 413

    def test_download_unknown_404(self, client, doctor_cookies):
        assert client.get("/api/clinical-files/99999999", cookies=doctor_cookies).status_code == 404

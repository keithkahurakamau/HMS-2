"""
Self-service profile + password tests.

Covers:
  - PATCH /users/me updates own name/specialization/licence
  - POST /users/me/change-password verifies current password, enforces change
  - Wrong current password rejected; password is restored at the end so the
    shared test user's credentials stay stable for other suites.
"""
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
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


class TestProfileUpdate:
    def test_requires_auth(self, client):
        assert client.patch("/api/users/me", json={"full_name": "X"}).status_code == 401

    def test_doctor_updates_own_profile(self, client, doctor_cookies):
        tag = uuid.uuid4().hex[:5].upper()
        r = client.patch("/api/users/me", cookies=doctor_cookies, json={
            "full_name": f"Dr Test {tag}",
            "specialization": "Cardiology",
        })
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == f"Dr Test {tag}"
        assert r.json()["specialization"] == "Cardiology"
        # Reflected on /me.
        me = client.get("/api/users/me", cookies=doctor_cookies).json()
        assert me["specialization"] == "Cardiology"

    def test_empty_name_rejected(self, client, doctor_cookies):
        r = client.patch("/api/users/me", cookies=doctor_cookies, json={"full_name": "   "})
        assert r.status_code == 422


class TestPasswordChange:
    # The shared demo seed password (seed_demo.py SHARED_PASSWORD).
    SEED_PWD = "Password@123"

    def test_wrong_current_rejected(self, client, nurse_cookies):
        r = client.post("/api/users/me/change-password", cookies=nurse_cookies, json={
            "current_password": "definitely-wrong", "new_password": "BrandNewPass123",  # gitleaks:allow — dummy test value
        })
        assert r.status_code == 400

    def test_too_short_rejected(self, client, nurse_cookies):
        r = client.post("/api/users/me/change-password", cookies=nurse_cookies, json={
            "current_password": self.SEED_PWD, "new_password": "short",
        })
        assert r.status_code == 422

    def test_change_and_restore(self, client, nurse_cookies):
        new_pwd = f"Rotated{uuid.uuid4().hex[:6]}A1"
        r = client.post("/api/users/me/change-password", cookies=nurse_cookies, json={
            "current_password": self.SEED_PWD, "new_password": new_pwd,
        })
        # If the seed password differs in this env, skip rather than fail noisily.
        if r.status_code == 400:
            pytest.skip("seed password differs in this environment")
        assert r.status_code == 200, r.text
        # Restore so other suites relying on the seed password still pass.
        back = client.post("/api/users/me/change-password", cookies=nurse_cookies, json={
            "current_password": new_pwd, "new_password": self.SEED_PWD,
        })
        assert back.status_code == 200, back.text

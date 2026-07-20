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
        "sex": "Female", "date_of_birth": "1993-09-09",
        "telephone_1": f"+2547{suffix[:8]}",
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0,
    })
    assert r.status_code == 200, r.text
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
    def test_register_then_conflict(self, client, nurse_cookies, admin_cookies, episode):
        r = client.post(f"/api/maternity/episodes/{episode['episode_id']}/delivery",
                        cookies=nurse_cookies, json={
                            "delivered_at": "2026-07-10T10:00:00Z",
                            "mode": "CSection",
                            "newborns": [{"sex": "Male", "weight_g": 2900}],
                        })
        newborn_id = r.json()["newborns"][0]["newborn_id"]

        # register-patient requires maternity:manage AND patients:write;
        # Nurse doesn't hold patients:write in this codebase's RBAC, so use
        # admin_cookies (which holds every permission) for this call.
        r = client.post(f"/api/maternity/newborns/{newborn_id}/register-patient",
                        cookies=admin_cookies)
        assert r.status_code == 200, r.text
        assert r.json()["patient_id"] > 0

        r = client.post(f"/api/maternity/newborns/{newborn_id}/register-patient",
                        cookies=admin_cookies)
        assert r.status_code == 409

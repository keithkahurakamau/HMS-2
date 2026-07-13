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

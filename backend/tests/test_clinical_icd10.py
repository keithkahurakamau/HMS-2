"""
ICD-10-CM catalogue search integration tests.

Covers /api/clinical/icd10/search :
  - Auth gating
  - Code-prefix search (dotted and undotted input)
  - Description substring search
  - Short queries return nothing (type-ahead floor)
  - Result cap respected
"""
from __future__ import annotations

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


class TestIcd10Search:
    def test_requires_auth(self, client):
        r = client.get("/api/clinical/icd10/search", params={"q": "E11"})
        assert r.status_code == 401

    def test_code_prefix_undotted(self, client, doctor_cookies):
        r = client.get("/api/clinical/icd10/search", params={"q": "E119"}, cookies=doctor_cookies)
        assert r.status_code == 200, r.text
        codes = [row["code"] for row in r.json()]
        assert "E11.9" in codes

    def test_code_prefix_dotted(self, client, doctor_cookies):
        r = client.get("/api/clinical/icd10/search", params={"q": "E11.9"}, cookies=doctor_cookies)
        assert r.status_code == 200
        codes = [row["code"] for row in r.json()]
        assert "E11.9" in codes

    def test_description_substring(self, client, doctor_cookies):
        r = client.get("/api/clinical/icd10/search", params={"q": "cholera"}, cookies=doctor_cookies)
        assert r.status_code == 200
        descriptions = " ".join(row["description"].lower() for row in r.json())
        assert "cholera" in descriptions

    def test_short_query_returns_empty(self, client, doctor_cookies):
        r = client.get("/api/clinical/icd10/search", params={"q": "e"}, cookies=doctor_cookies)
        assert r.status_code == 200
        assert r.json() == []

    def test_limit_is_respected(self, client, doctor_cookies):
        r = client.get(
            "/api/clinical/icd10/search",
            params={"q": "fever", "limit": 5},
            cookies=doctor_cookies,
        )
        assert r.status_code == 200
        assert len(r.json()) <= 5

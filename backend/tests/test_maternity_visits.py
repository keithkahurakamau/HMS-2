"""ANC/PNC visit endpoints + billing side-effects."""
from __future__ import annotations

import uuid

import pytest
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


def _db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return sessionmaker(bind=create_engine(f"{base}/{TENANT}"))()


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
        "surname": f"Anc{suffix}", "other_names": "Visit Mother",
        "sex": "Female", "date_of_birth": "1995-01-15",
        "telephone_1": f"+2547{suffix[:8]}",
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0, "lmp": "2026-02-10",
    })
    assert r.status_code == 200, r.text
    return {"patient_id": pid, "episode_id": r.json()["episode_id"]}


def _set_price(code: str, price: float):
    db = _db()
    try:
        db.execute(text("UPDATE acc_price_list SET unit_price = :p WHERE service_code = :c"),
                   {"p": price, "c": code})
        db.commit()
    finally:
        db.close()


class TestAncVisit:
    def test_visit_computes_number_and_gestation(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 0)
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies,
            json={"visit_date": "2026-07-08", "bp_systolic": 118, "bp_diastolic": 76},
        )
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["visit_number"] == 1
        # LMP 2026-02-10 → 2026-07-08 is 148 days ≈ 21 weeks
        assert v["gestation_weeks"] == 21

        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies, json={"visit_date": "2026-07-09"},
        )
        assert r.json()["visit_number"] == 2

    def test_priced_visit_raises_invoice_and_gl(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 500)
        try:
            r = client.post(
                f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
                cookies=nurse_cookies, json={"visit_date": "2026-07-10"},
            )
            assert r.status_code == 200, r.text
            db = _db()
            try:
                # Query invoice item with its ID
                row = db.execute(text(
                    "SELECT ii.id, ii.amount FROM invoice_items ii "
                    "JOIN invoices i ON i.invoice_id = ii.invoice_id "
                    "WHERE i.patient_id = :pid AND ii.item_type = 'Maternity' "
                    "ORDER BY ii.id DESC LIMIT 1"
                ), {"pid": episode["patient_id"]}).first()
                assert row is not None
                ii_id = row[0]
                assert float(row[1]) == 500.0

                # Assert GL journal entry exists for this invoice item
                je_row = db.execute(text(
                    "SELECT entry_id FROM acc_journal_entries "
                    "WHERE source_type = 'billing.invoice.created' "
                    "AND source_id = :ii_id AND status = 'posted'"
                ), {"ii_id": ii_id}).first()
                assert je_row is not None, f"No journal entry found for invoice item {ii_id}"
                entry_id = je_row[0]

                # Verify journal lines debit and credit total 500.00 each
                debit_row = db.execute(text(
                    "SELECT COALESCE(SUM(debit_base), 0) FROM acc_journal_lines "
                    "WHERE entry_id = :entry_id"
                ), {"entry_id": entry_id}).scalar()
                credit_row = db.execute(text(
                    "SELECT COALESCE(SUM(credit_base), 0) FROM acc_journal_lines "
                    "WHERE entry_id = :entry_id"
                ), {"entry_id": entry_id}).scalar()
                assert float(debit_row) == 500.0, f"Total debit was {debit_row}, expected 500.0"
                assert float(credit_row) == 500.0, f"Total credit was {credit_row}, expected 500.0"
            finally:
                db.close()
        finally:
            _set_price("MAT-ANC-VISIT", 0)

    def test_zero_priced_visit_raises_no_charge(self, client, nurse_cookies, episode):
        _set_price("MAT-ANC-VISIT", 0)
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/anc-visits",
            cookies=nurse_cookies, json={"visit_date": "2026-07-11"},
        )
        assert r.status_code == 200
        db = _db()
        try:
            n = db.execute(text(
                "SELECT COUNT(*) FROM invoice_items ii "
                "JOIN invoices i ON i.invoice_id = ii.invoice_id "
                "WHERE i.patient_id = :pid AND ii.item_type = 'Maternity'"
            ), {"pid": episode["patient_id"]}).scalar()
            assert n == 0
        finally:
            db.close()


class TestPncVisit:
    def test_pnc_visit_records(self, client, nurse_cookies, episode):
        r = client.post(
            f"/api/maternity/episodes/{episode['episode_id']}/pnc-visits",
            cookies=nurse_cookies,
            json={"visit_date": "2026-07-12", "involution": "Well contracted",
                  "lochia": "Normal", "feeding": "Exclusive BF"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["visit_number"] == 1

"""Labor link + partograph: append-only entries, corrections, alert lines."""
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


def test_alert_status_math():
    from app.routes.maternity_labor import alert_status
    # On/left of the alert line (4cm + 1cm/hr) is ok.
    assert alert_status(6.0, 2.0) == "ok"      # expected >= 6 at 2h
    assert alert_status(5.0, 2.0) == "alert"   # below 6 at 2h → alert zone
    assert alert_status(4.0, 8.5) == "action"  # below 4 + (8.5-4) = 8.5 → past action line
    assert alert_status(None, 3.0) == "ok"     # nothing to judge


def _find_available_bed(board):
    """Board is a flat list of ward dicts (app/routes/wards.py get_bed_board),
    each with a "beds" list; bed dicts key their id as "id" (not "bed_id")
    and their occupancy as "status". Keep the dict-shaped fallback in case
    that ever changes to a {"wards": [...]} envelope."""
    for ward in board if isinstance(board, list) else board.get("wards", []):
        for bed in ward.get("beds", []):
            if bed.get("status") == "Available":
                return bed.get("id")
    return None


@pytest.fixture()
def labor(client, nurse_cookies, admin_cookies, doctor_cookies):
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Lab{suffix}", "other_names": "Partograph Mother",
        "sex": "Female", "date_of_birth": "1994-06-20",
        "telephone_1": f"+2547{suffix[:8]}",
    })
    assert r.status_code in (200, 201), r.text
    pid = r.json()["patient_id"]
    r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
        "patient_id": pid, "gravida": 1, "para": 0,
    })
    assert r.status_code == 200, r.text
    eid = r.json()["episode_id"]

    # Ward admission via the normal wards flow (needs a free bed). Look for
    # one Available on the board; if the seeded tenant has none left (this
    # fixture runs once per test and never discharges), seed a fresh
    # ward+bed as admin (wards:manage) so the fixture is self-sufficient.
    board = client.get("/api/wards/board", cookies=nurse_cookies).json()
    bed_id = _find_available_bed(board)
    if not bed_id:
        wname = f"MatTest{suffix}"
        r = client.post("/api/wards/", cookies=admin_cookies,
                        json={"name": wname, "capacity": 5})
        assert r.status_code == 200, r.text
        ward_id = r.json()["ward_id"]
        r = client.post(f"/api/wards/{ward_id}/beds", cookies=admin_cookies,
                        json={"bed_number": f"{wname}-1"})
        assert r.status_code == 200, r.text
        board = client.get("/api/wards/board", cookies=nurse_cookies).json()
        bed_id = _find_available_bed(board)
    assert bed_id, "no free bed on the board — seed a bed first"

    r = client.post("/api/wards/admit", cookies=doctor_cookies, json={
        "patient_id": pid, "bed_id": bed_id, "diagnosis": "Labor",
    })
    assert r.status_code in (200, 201), r.text
    # admit_patient() only ever returns {"message": ...} — no admission_id in
    # the body — so pull it back off the board, where get_bed_board() attaches
    # admission_id to Occupied beds.
    board = client.get("/api/wards/board", cookies=nurse_cookies).json()
    admission_id = None
    for ward in board:
        for bed in ward.get("beds", []):
            if bed.get("id") == bed_id:
                admission_id = bed.get("admission_id")
                break
        if admission_id:
            break
    assert admission_id, "admission_id not found on the board after admit"

    r = client.post(f"/api/maternity/episodes/{eid}/labor", cookies=nurse_cookies,
                    json={"admission_id": admission_id})
    assert r.status_code == 200, r.text
    return {"labor_admission_id": r.json()["labor_admission_id"],
            "episode_id": eid, "patient_id": pid, "admission_id": admission_id}


class TestPartograph:
    def test_append_list_and_correction_chain(self, client, nurse_cookies, labor):
        lid = labor["labor_admission_id"]
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 4.0, "fetal_heart_rate": 140})
        assert r.status_code == 200, r.text
        first = r.json()

        # First >=4cm entry sets time zero.
        r = client.get(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies)
        body = r.json()
        assert body["active_labor_started_at"] is not None
        assert len(body["entries"]) == 1

        # Correction supersedes the first entry.
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 5.0, "fetal_heart_rate": 138,
                              "corrects_entry_id": first["entry_id"]})
        assert r.status_code == 200
        body = client.get(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies).json()
        by_id = {e["entry_id"]: e for e in body["entries"]}
        assert by_id[first["entry_id"]]["superseded"] is True

    def test_no_update_or_delete_routes(self, client, nurse_cookies, labor):
        lid = labor["labor_admission_id"]
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 6.0})
        entry_id = r.json()["entry_id"]
        assert client.patch(f"/api/maternity/labor/{lid}/partograph/{entry_id}",
                            cookies=nurse_cookies, json={}).status_code in (404, 405)
        assert client.delete(f"/api/maternity/labor/{lid}/partograph/{entry_id}",
                             cookies=nurse_cookies).status_code in (404, 405)

    def test_double_link_409(self, client, nurse_cookies, labor):
        r = client.post(f"/api/maternity/episodes/{labor['episode_id']}/labor",
                        cookies=nurse_cookies,
                        json={"admission_id": labor["admission_id"]})
        assert r.status_code == 409

    def test_naive_recorded_at_after_active_labor_started(self, client, nurse_cookies, labor):
        """A client-supplied naive datetime-local value (no offset) must not
        crash when subtracted against the tz-aware active_labor_started_at
        reloaded from the TIMESTAMPTZ column. Before the fix this 500'd."""
        lid = labor["labor_admission_id"]
        # First >=4cm entry anchors active_labor_started_at (tz-aware, from the DB).
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 4.0, "fetal_heart_rate": 140})
        assert r.status_code == 200, r.text

        # Second entry supplies a naive recorded_at (as an HTML datetime-local
        # input would), timed after active labor started.
        r = client.post(f"/api/maternity/labor/{lid}/partograph", cookies=nurse_cookies,
                        json={"cervical_dilation_cm": 5.0, "fetal_heart_rate": 138,
                              "recorded_at": "2026-07-13T09:00:00"})
        assert r.status_code == 200, r.text
        assert r.json()["hours_since_active"] is not None

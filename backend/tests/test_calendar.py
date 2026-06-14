"""
Personal calendar events integration tests.

Covers /api/calendar/events :
  - Auth gating
  - Create → list → update → delete roundtrip for the owner
  - Date-window filtering
  - end-before-start rejected
  - One user cannot see or mutate another user's events (isolation)
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


class TestCalendarAuth:
    def test_requires_auth(self, client):
        assert client.get("/api/calendar/events").status_code == 401
        assert client.post("/api/calendar/events", json={
            "title": "x", "start_at": "2026-07-01T09:00:00"
        }).status_code == 401


class TestCalendarCrud:
    def test_create_list_update_delete(self, client, doctor_cookies):
        tag = uuid.uuid4().hex[:6].upper()
        r = client.post("/api/calendar/events", cookies=doctor_cookies, json={
            "title": f"Leave {tag}",
            "category": "leave",
            "start_at": "2026-07-10T00:00:00",
            "end_at": "2026-07-12T00:00:00",
            "all_day": True,
            "notes": "Annual leave",
        })
        assert r.status_code == 200, r.text
        event = r.json()
        assert event["title"] == f"Leave {tag}"
        assert event["category"] == "leave"
        eid = event["event_id"]

        # Appears in the owner's list.
        r = client.get("/api/calendar/events", cookies=doctor_cookies)
        assert any(e["event_id"] == eid for e in r.json())

        # Update.
        r = client.patch(f"/api/calendar/events/{eid}", cookies=doctor_cookies,
                         json={"title": f"Updated {tag}", "category": "meeting"})
        assert r.status_code == 200, r.text
        assert r.json()["title"] == f"Updated {tag}"
        assert r.json()["category"] == "meeting"

        # Delete.
        assert client.delete(f"/api/calendar/events/{eid}", cookies=doctor_cookies).status_code == 200
        r = client.get("/api/calendar/events", cookies=doctor_cookies)
        assert all(e["event_id"] != eid for e in r.json())

    def test_unknown_category_falls_back_to_personal(self, client, doctor_cookies):
        r = client.post("/api/calendar/events", cookies=doctor_cookies, json={
            "title": "Misc", "category": "nonsense", "start_at": "2026-07-15T09:00:00",
        })
        assert r.status_code == 200
        assert r.json()["category"] == "personal"
        client.delete(f"/api/calendar/events/{r.json()['event_id']}", cookies=doctor_cookies)

    def test_end_before_start_rejected(self, client, doctor_cookies):
        r = client.post("/api/calendar/events", cookies=doctor_cookies, json={
            "title": "Bad range",
            "start_at": "2026-07-10T10:00:00",
            "end_at": "2026-07-10T09:00:00",
        })
        assert r.status_code == 400

    def test_date_window_filter(self, client, doctor_cookies):
        tag = uuid.uuid4().hex[:6]
        r = client.post("/api/calendar/events", cookies=doctor_cookies, json={
            "title": f"July {tag}", "start_at": "2026-07-20T09:00:00",
        })
        eid = r.json()["event_id"]
        # Window in August should not include the July event.
        r = client.get("/api/calendar/events", cookies=doctor_cookies,
                       params={"date_from": "2026-08-01T00:00:00", "date_to": "2026-08-31T23:59:59"})
        assert all(e["event_id"] != eid for e in r.json())
        client.delete(f"/api/calendar/events/{eid}", cookies=doctor_cookies)


class TestCalendarIsolation:
    def test_one_user_cannot_touch_anothers_event(self, client, doctor_cookies, nurse_cookies):
        r = client.post("/api/calendar/events", cookies=doctor_cookies, json={
            "title": "Doctor private", "start_at": "2026-07-25T09:00:00",
        })
        eid = r.json()["event_id"]

        # Nurse can't see it in their list…
        r = client.get("/api/calendar/events", cookies=nurse_cookies)
        assert all(e["event_id"] != eid for e in r.json())
        # …nor update or delete it (scoped query → 404).
        assert client.patch(f"/api/calendar/events/{eid}", cookies=nurse_cookies,
                            json={"title": "hijack"}).status_code == 404
        assert client.delete(f"/api/calendar/events/{eid}", cookies=nurse_cookies).status_code == 404

        # Owner cleanup.
        client.delete(f"/api/calendar/events/{eid}", cookies=doctor_cookies)

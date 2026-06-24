# Perfect Deletion Across All Queues — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every queue in the system a reliable soft-cancel ("remove") action — Triage, Pharmacy prescriptions, Radiology requests, and Billing invoices — with a reason + audit, no hard deletes.

**Architecture:** FastAPI + SQLAlchemy backend (multi-tenant, DB-per-tenant), React (Vite) frontend. Every action soft-cancels (status string flip) and writes an audit row; entries drop out of their worklist because each list already filters terminal statuses. The Billing void additionally reverses its ledger posting via the existing `accounting.reverse_entry`. **No schema change.**

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pytest (live-server httpx integration tests), React 18, Vite, Vitest + RTL, Tailwind, lucide-react, react-hot-toast.

## Global Constraints

- Branch: `feat/queue-deletion-all-modules` (already created off `development`). One combined PR → `development`.
- **No schema change, no migration.** All status values already exist (`Invoice.status` includes `"Cancelled"`; `RadiologyRequest.status` and `MedicalRecord.record_status` are free strings). Keep the migration gate a no-op — state this in the PR.
- Soft-cancel only — never hard-delete a clinical/financial row. Each action requires a `reason` and writes a `log_audit` row.
- Permissions (per-module manage): `patients:write` (triage — existing endpoints), `pharmacy:manage` (prescription cancel), `radiology:manage` (radiology cancel), `billing:manage` (invoice void).
- Billing void: only fully-unpaid `Pending` invoices; reject `Paid`/`Partially Paid`/`Pending M-Pesa`/already-`Cancelled` with HTTP 400. Must reverse the GL posting via `app.services.accounting.reverse_entry`.
- Backend tests are **live-server integration tests**: server on `http://localhost:8000`, tenant `mayoclinic_db`, CSRF double-submit (GET first, echo `csrf_token` cookie as `x-csrf-token`), `*_cookies` fixtures in `backend/tests/conftest.py`. Run with `REDIS_URL=""`. The `medical_history` and `accounting` feature flags are already enabled for `mayoclinic_db` locally.
- Server is NOT in --reload mode: after editing backend code, restart it (`pkill -f "uvicorn app.main:app"` then relaunch `REDIS_URL="" nohup uvicorn app.main:app --port 8000 --host 127.0.0.1 > <scratch>/uvicorn.log 2>&1 & disown`; wait for `/docs` HTTP 200). Do one restart after edits, not many.
- Frontend: run `npx eslint <files>` (0 errors required; pre-existing exhaustive-deps warnings are not new findings) and `npm run build` before committing. Set httpx/test cookies once on the client (not per-request) to keep output pristine.
- Commit messages end with `Co-Authored-By: RuFlo <ruv@ruv.net>`.

---

## File Structure

**Backend**
- Modify `backend/app/routes/clinical.py` — add `CancelPrescriptionRequest` + `POST /prescriptions/{record_id}/cancel`.
- Modify `backend/app/routes/radiology.py` — add a cancel request schema + `POST /{request_id}/cancel`.
- Modify `backend/app/routes/billing.py` — add `VoidInvoiceRequest` + `POST /invoices/{invoice_id}/void` (uses `accounting.reverse_entry`).
- Tests: `backend/tests/test_prescription_cancel.py`, `backend/tests/test_radiology_cancel.py`, `backend/tests/test_billing_void.py` (all new).

**Frontend**
- Modify `frontend/src/pages/Triage.jsx` — per-row Remove + Cancel on the "Awaiting Triage" cards (reuses shipped `/queue/{id}/checkout` + `/queue/{id}/cancel`).
- Modify `frontend/src/pages/Pharmacy.jsx` — Cancel action on pending-prescription cards.
- Modify `frontend/src/pages/Radiology.jsx` — Cancel action on request rows.
- Modify `frontend/src/pages/Billing.jsx` — Void action on invoice rows.
- Test: `frontend/src/pages/Pharmacy.test.jsx` already exists — extend if it cleanly covers the cancel; otherwise lint+build is the gate for pages without tests.

---

### Task 1: Pharmacy prescription cancel endpoint

**Files:**
- Modify: `backend/app/routes/clinical.py` (after `return_prescription`, ~line 310)
- Test: `backend/tests/test_prescription_cancel.py` (create)

**Interfaces:**
- Produces: `POST /api/clinical/prescriptions/{record_id}/cancel` body `{"reason": str|null}` → `{"message","record_id"}`; sets `MedicalRecord.record_status="Cancelled"`; drops from `/clinical/prescriptions/pending`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prescription_cancel.py`:

```python
"""Pharmacy can cancel a pending prescription (soft, with reason + audit).

Live-server integration test (server on :8000, tenant mayoclinic_db).
"""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_RXCAN_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Rx Cancel", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _forward_to_pharmacy(client, doctor_cookies, patient_id) -> int:
    """Create a clinical record routed to Pharmacy; return record_id."""
    r = client.post("/api/clinical/submit", cookies=doctor_cookies, json={
        "patient_id": patient_id,
        "record_status": "Pharmacy",
        "chief_complaint": "rx cancel test",
        "prescription_notes": "Amoxicillin 500mg",
    })
    assert r.status_code == 200, r.text
    # Find the record via the pending list
    pend = client.get("/api/clinical/prescriptions/pending", cookies=doctor_cookies).json()
    mine = [p for p in pend if p.get("patient_id") == patient_id]
    assert mine, f"expected a pending script for patient {patient_id}: {pend[:2]}"
    return mine[0]["record_id"]


def test_cancel_requires_auth(client):
    r = client.post("/api/clinical/prescriptions/1/cancel", json={"reason": "x"})
    assert r.status_code == 401


def test_cancel_unknown_returns_404(client, pharmacist_cookies):
    r = client.post("/api/clinical/prescriptions/999999999/cancel",
                    cookies=pharmacist_cookies, json={"reason": "x"})
    assert r.status_code == 404


def test_cancel_drops_from_pending(client, doctor_cookies, pharmacist_cookies):
    patient = _new_patient(client, doctor_cookies)
    pid = patient["patient_id"]
    try:
        rid = _forward_to_pharmacy(client, doctor_cookies, pid)
        r = client.post(f"/api/clinical/prescriptions/{rid}/cancel",
                        cookies=pharmacist_cookies, json={"reason": "Duplicate script"})
        assert r.status_code == 200, r.text

        pend = client.get("/api/clinical/prescriptions/pending", cookies=pharmacist_cookies).json()
        assert all(p["record_id"] != rid for p in pend)
    finally:
        client.delete(f"/api/patients/{pid}", cookies=doctor_cookies)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_prescription_cancel.py -v
```

Expected: FAIL — the cancel endpoint 404s (route missing).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routes/clinical.py`, after `return_prescription` (mirror that handler's structure). The `_BM` base, `datetime`, `timezone`, `log_audit`, `MedicalRecord`, `RequirePermission`, `get_current_user` are already imported there. Add:

```python
class CancelPrescriptionRequest(_BM):
    reason: Optional[str] = None


@router.post("/prescriptions/{record_id}/cancel", dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def cancel_prescription(
    record_id: int,
    payload: CancelPrescriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Pharmacist cancels a pending prescription (e.g. duplicate/erroneous).

    Soft: flips the record off the Pharmacy worklist while keeping the
    encounter row. Distinct from 'return to doctor' (which bounces it back)."""
    record = db.query(MedicalRecord).filter(MedicalRecord.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Prescription not found.")
    if record.record_status == "Pharmacy":
        old = {"record_status": "Pharmacy"}
        record.record_status = "Cancelled"
        record.internal_notes = (record.internal_notes or "") + \
            f"\nCANCELLED BY PHARMACY ({datetime.now(timezone.utc).isoformat()}): {payload.reason or ''}"
        log_audit(
            db, current_user["user_id"], "UPDATE", "MedicalRecord", str(record_id),
            old, {"record_status": "Cancelled", "reason": payload.reason},
            request.client.host if request.client else None,
        )
        db.commit()
    return {"message": "Prescription cancelled.", "record_id": record_id}
```

Ensure `Optional` is imported in clinical.py (it is, used elsewhere; confirm with `grep -n "Optional" app/routes/clinical.py`).

- [ ] **Step 4: Restart server, run the test → PASS**

Restart per Global Constraints, then:

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_prescription_cancel.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/clinical.py backend/tests/test_prescription_cancel.py
git commit -m "feat(pharmacy): cancel a pending prescription (soft, reason + audit)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 2: Radiology request cancel endpoint

**Files:**
- Modify: `backend/app/routes/radiology.py` (add a cancel request schema near the other request schemas + the endpoint near `create_radiology_request`)
- Test: `backend/tests/test_radiology_cancel.py` (create)

**Interfaces:**
- Produces: `POST /api/radiology/{request_id}/cancel` body `{"reason": str|null}` → `{"message","request_id"}`; sets `RadiologyRequest.status="Cancelled"`; drops from the requests list.

- [ ] **Step 1: Read the radiology request creation + list to match conventions**

```bash
sed -n '83,175p' backend/app/routes/radiology.py
```

Note the imports already present (`log_audit`?, `RadiologyRequest`, `RequirePermission`, `get_current_user`, `Request`). If `log_audit` is not imported, add `from app.utils.audit import log_audit`.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_radiology_cancel.py`:

```python
"""Radiology can cancel an imaging request (soft, reason + audit)."""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_RADCAN_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Rad Cancel", "sex": "Female",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _create_request(client, doctor_cookies, patient_id) -> int:
    r = client.post("/api/radiology/requests", cookies=doctor_cookies, json={
        "patient_id": patient_id, "exam_type": "Chest X-Ray", "priority": "Routine"})
    assert r.status_code in (200, 201), r.text
    return r.json()["request_id"]


def test_cancel_requires_auth(client):
    r = client.post("/api/radiology/1/cancel", json={"reason": "x"})
    assert r.status_code == 401


def test_cancel_unknown_returns_404(client, radiologist_cookies):
    r = client.post("/api/radiology/999999999/cancel",
                    cookies=radiologist_cookies, json={"reason": "x"})
    assert r.status_code == 404


def test_cancel_sets_status_and_drops(client, doctor_cookies, radiologist_cookies):
    patient = _new_patient(client, doctor_cookies)
    pid = patient["patient_id"]
    try:
        req_id = _create_request(client, doctor_cookies, pid)
        r = client.post(f"/api/radiology/{req_id}/cancel",
                        cookies=radiologist_cookies, json={"reason": "Wrong order"})
        assert r.status_code == 200, r.text

        rows = client.get("/api/radiology/requests", cookies=radiologist_cookies).json()
        match = [x for x in rows if x.get("request_id") == req_id]
        # Either dropped from the list, or present but Cancelled.
        assert not match or match[0].get("status") == "Cancelled", match
    finally:
        client.delete(f"/api/patients/{pid}", cookies=doctor_cookies)
```

> If `POST /api/radiology/requests` or `GET /api/radiology/requests` differ in path/shape from the above (verify in Step 1), adjust the helper calls to the real routes — keep the assertions (cancel → status Cancelled / dropped).

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_radiology_cancel.py -v
```

Expected: FAIL — cancel route missing (404).

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routes/radiology.py`, add a request schema (inline Pydantic, mirroring how other request bodies are declared in that file) and the endpoint:

```python
from pydantic import BaseModel  # if not already imported

class RadiologyCancelRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/{request_id}/cancel", dependencies=[Depends(RequirePermission("radiology:manage"))])
def cancel_radiology_request(
    request_id: int,
    payload: RadiologyCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel an imaging request that should not be performed."""
    req = db.query(RadiologyRequest).filter(RadiologyRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Radiology request not found.")
    if req.status not in ("Completed", "Cancelled"):
        old = {"status": req.status}
        req.status = "Cancelled"
        if payload.reason:
            req.clinical_notes = (req.clinical_notes or "") + f"\nCANCELLED: {payload.reason}"
        log_audit(
            db, current_user["user_id"], "UPDATE", "RadiologyRequest", str(request_id),
            old, {"status": "Cancelled", "reason": payload.reason},
            request.client.host if request.client else None,
        )
        db.commit()
    return {"message": "Radiology request cancelled.", "request_id": request_id}
```

Ensure `Optional`, `RequirePermission`, `get_current_user`, `Request`, `RadiologyRequest`, `log_audit`, `HTTPException` are imported (add any missing — see Step 1).

- [ ] **Step 5: Restart server, run the test → PASS**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_radiology_cancel.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/radiology.py backend/tests/test_radiology_cancel.py
git commit -m "feat(radiology): cancel an imaging request (soft, reason + audit)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 3: Billing invoice void endpoint (with GL reversal)

**Files:**
- Modify: `backend/app/routes/billing.py` (add `VoidInvoiceRequest` + `POST /invoices/{invoice_id}/void`)
- Test: `backend/tests/test_billing_void.py` (create)

**Interfaces:**
- Consumes: `app.services.accounting.reverse_entry(db, entry_id, user_id, reason)` (existing — mirrors a posted `JournalEntry`, swaps Dr/Cr, marks original `reversed`). Invoice items post under `source_type="billing.invoice.created"`, `source_id=<InvoiceItem.id>`.
- Produces: `POST /api/billing/invoices/{invoice_id}/void` body `{"reason": str|null}` → `{"message","invoice_id"}`; sets `Invoice.status="Cancelled"`; 400 if not fully-unpaid `Pending`; reverses each posted GL entry; drops from `/billing/queue`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_billing_void.py`:

```python
"""Billing can void a fully-unpaid Pending invoice (soft + GL reversal)."""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_VOID_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Void Test", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _charge_consult_fee(client, doctor_cookies, patient_id):
    """Charge a consultation fee → creates a Pending invoice (+GL post)."""
    r = client.post("/api/billing/consultation-fee", cookies=doctor_cookies,
                    json={"patient_id": patient_id, "amount": 500})
    assert r.status_code == 200, r.text


def _find_pending_invoice(client, billing_cookies, patient_id):
    q = client.get("/api/billing/queue", cookies=billing_cookies).json()
    mine = [i for i in q if i.get("patient_id") == patient_id]
    assert mine, f"expected a pending invoice for {patient_id}"
    return mine[0]["invoice_id"]


def test_void_requires_auth(client):
    r = client.post("/api/billing/invoices/1/void", json={"reason": "x"})
    assert r.status_code == 401


def test_void_unknown_returns_404(client, admin_cookies):
    r = client.post("/api/billing/invoices/999999999/void",
                    cookies=admin_cookies, json={"reason": "x"})
    assert r.status_code == 404


def test_void_pending_invoice_drops_from_queue(client, doctor_cookies, admin_cookies):
    patient = _new_patient(client, doctor_cookies)
    pid = patient["patient_id"]
    try:
        _charge_consult_fee(client, doctor_cookies, pid)
        inv_id = _find_pending_invoice(client, admin_cookies, pid)

        r = client.post(f"/api/billing/invoices/{inv_id}/void",
                        cookies=admin_cookies, json={"reason": "Duplicate charge"})
        assert r.status_code == 200, r.text

        q = client.get("/api/billing/queue", cookies=admin_cookies).json()
        assert all(i["invoice_id"] != inv_id for i in q)

        # Idempotency / guard: a second void is rejected (already Cancelled).
        again = client.post(f"/api/billing/invoices/{inv_id}/void",
                            cookies=admin_cookies, json={"reason": "again"})
        assert again.status_code == 400, again.text
    finally:
        client.delete(f"/api/patients/{pid}", cookies=doctor_cookies)
```

> `admin_cookies` holds `billing:manage`. If the consultation-fee charge requires a configured fee and fails, set one first via `PUT /api/billing/consultation-fee/me {"amount": 500}` as `doctor_cookies` — add that call inside `_charge_consult_fee` before the charge if the charge 400s.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_billing_void.py -v
```

Expected: FAIL — void route missing (404).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routes/billing.py` (it already imports `post_from_event`; add `from app.services.accounting import reverse_entry` and `from app.models.accounting import JournalEntry`, and `from app.models.billing import InvoiceItem` if not present). Add:

```python
from pydantic import BaseModel  # if not already imported

class VoidInvoiceRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/invoices/{invoice_id}/void", dependencies=[Depends(RequirePermission("billing:manage"))])
def void_invoice(
    invoice_id: int,
    payload: VoidInvoiceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Void a fully-unpaid Pending invoice and reverse its ledger posting.

    Only Pending (nothing collected) invoices are voidable — Paid / Partially
    Paid involve collected money and need a refund/credit-note flow instead."""
    invoice = db.query(Invoice).with_for_update().filter(Invoice.invoice_id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status != "Pending":
        raise HTTPException(
            status_code=400,
            detail=f"Only fully-unpaid Pending invoices can be voided; this one is '{invoice.status}'.",
        )

    # Reverse every posted GL entry for this invoice's items so A/R + revenue
    # net to zero. reverse_entry requires status='posted', so already-reversed
    # entries are skipped — keeping the void idempotent at the ledger level.
    item_ids = [it.id for it in invoice.items]
    if item_ids:
        posted = (
            db.query(JournalEntry)
            .filter(JournalEntry.source_type == "billing.invoice.created",
                    JournalEntry.source_id.in_(item_ids),
                    JournalEntry.status == "posted")
            .all()
        )
        for entry in posted:
            reverse_entry(db, entry.entry_id, current_user["user_id"], payload.reason or "Invoice voided")

    old = {"status": invoice.status}
    invoice.status = "Cancelled"
    log_audit(
        db, current_user["user_id"], "UPDATE", "Invoice", str(invoice_id),
        old, {"status": "Cancelled", "reason": payload.reason},
        request.client.host if request.client else None,
    )
    db.commit()
    return {"message": "Invoice voided.", "invoice_id": invoice_id}
```

Confirm `Optional`, `Invoice`, `RequirePermission`, `get_current_user`, `Request`, `log_audit`, `HTTPException` are imported in billing.py (add any missing). `InvoiceItem.id` is the PK used as the posting `source_id` (verify the column name is `id` via `grep -n "class InvoiceItem" -A8 app/models/billing.py`; if it's `item_id`, use that).

- [ ] **Step 4: Restart server, run the test → PASS**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_billing_void.py -v
```

Expected: PASS (3 tests). If `test_void_pending_invoice_drops_from_queue` fails at `_charge_consult_fee`, add the fee-setup call noted under Step 1 and re-run.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/billing.py backend/tests/test_billing_void.py
git commit -m "feat(billing): void a fully-unpaid Pending invoice with GL reversal

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 4: Backend checkpoint

**Files:** none (verification).

- [ ] **Step 1: Run all three new suites together**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_prescription_cancel.py tests/test_radiology_cancel.py tests/test_billing_void.py -v
```

Expected: all PASS. (Do not run `tests/test_api.py` — ~34 known pre-existing failures.)

---

### Task 5: Triage queue card Remove + Cancel (frontend)

**Files:**
- Modify: `frontend/src/pages/Triage.jsx` (the "Awaiting Triage" queue card grid, ~lines 168-181)

**Interfaces:**
- Consumes: shipped `PATCH /api/queue/{id}/checkout` (Remove → Completed) and `PATCH /api/queue/{id}/cancel` body `{reason}` (Cancel → Cancelled). `get_triage_queue` already excludes both.

- [ ] **Step 1: Read the triage queue card block**

```bash
grep -n "handlePatientSelect\|item.queue_id\|queue.map\|Awaiting Triage" frontend/src/pages/Triage.jsx
```

Find the `queue.map((item) => ...)` card (a `<button>` that calls `handlePatientSelect`). You will add two small action buttons inside each card without breaking the select.

- [ ] **Step 2: Add the remove/cancel handlers**

Near `fetchQueue` in `Triage.jsx`, add:

```jsx
const removeFromTriage = async (e, queueId) => {
    e.stopPropagation();
    try {
        await apiClient.patch(`/queue/${queueId}/checkout`);
        toast.success('Removed from triage queue.');
        fetchQueue();
    } catch {
        toast.error('Could not remove from the queue.');
    }
};

const cancelFromTriage = async (e, queueId) => {
    e.stopPropagation();
    const reason = window.prompt('Cancel reason (optional):') ?? null;
    try {
        await apiClient.patch(`/queue/${queueId}/cancel`, { reason });
        toast.success('Patient cancelled.');
        fetchQueue();
    } catch {
        toast.error('Could not cancel.');
    }
};
```

- [ ] **Step 3: Render the actions inside each queue card**

The cards are `<button>` elements; nested buttons are invalid HTML, so convert the outer card from a `<button>` to a `<div role="button" tabIndex={0}>` with `onClick={() => handlePatientSelect(item)}` and `onKeyDown` for Enter/Space, OR keep the card a button and place the action buttons as siblings in a footer row of the card. Simplest faithful approach: keep the existing card button, and add a small action row beneath the card content inside the same grid cell:

```jsx
<div className="mt-2 flex items-center justify-end gap-1">
    <button type="button" onClick={(e) => removeFromTriage(e, item.queue_id)}
        className="text-2xs px-2 py-0.5 rounded-md text-ink-500 hover:text-brand-700 hover:bg-brand-50 dark:hover:bg-ink-800">
        Remove
    </button>
    <button type="button" onClick={(e) => cancelFromTriage(e, item.queue_id)}
        className="text-2xs px-2 py-0.5 rounded-md text-ink-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10">
        Cancel
    </button>
</div>
```

If the card is a single `<button>`, move the action row OUT of the button (as a sibling within the grid cell wrapper) so it is not a nested button — wrap the card + action row in a `<div key={item.queue_id} className="...">`. Match the existing card's wrapper classes; do not change the select behavior.

- [ ] **Step 4: Lint + build**

```bash
cd frontend && npx eslint src/pages/Triage.jsx && npm run build 2>&1 | tail -3
```

Expected: 0 errors; build ✓.

- [ ] **Step 5: Run the existing Triage test**

```bash
cd frontend && npx vitest run src/pages/Triage.test.jsx
```

Expected: PASS (the disposition test is unaffected).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Triage.jsx
git commit -m "feat(triage): per-row Remove + Cancel on the Awaiting Triage queue

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 6: Pharmacy pending-prescription Cancel button (frontend)

**Files:**
- Modify: `frontend/src/pages/Pharmacy.jsx` (the pending-prescription card / active-order actions)
- Test: `frontend/src/pages/Pharmacy.test.jsx` (extend if it covers the queue cleanly)

**Interfaces:**
- Consumes: `POST /api/clinical/prescriptions/{record_id}/cancel` body `{reason}` (Task 1).

- [ ] **Step 1: Read how the pending list + active order render and how "return" is wired**

```bash
grep -n "prescriptions/pending\|/return\|activeOrder\|record_id\|Return\|dispense" frontend/src/pages/Pharmacy.jsx
```

Find where the "Return to doctor" action lives (it POSTs `/clinical/prescriptions/{record_id}/return`). The Cancel action mirrors it.

- [ ] **Step 2: Add the cancel handler**

```jsx
const cancelPrescription = async (recordId) => {
    const reason = window.prompt('Reason for cancelling this prescription:') ?? null;
    if (reason === null) return; // user dismissed
    try {
        await apiClient.post(`/clinical/prescriptions/${recordId}/cancel`, { reason });
        toast.success('Prescription cancelled.');
        fetchPending(); // use whatever the page calls to reload the pending list
    } catch (err) {
        toast.error(err?.response?.data?.detail || 'Could not cancel prescription.');
    }
};
```

Match the real reload function name (from Step 1 — e.g. `fetchPending`/`loadQueue`).

- [ ] **Step 3: Render a Cancel button next to the existing actions**

Beside the "Return to doctor" / "Dispense" buttons for the active order (or on each pending card), add:

```jsx
<button type="button" onClick={() => cancelPrescription(activeOrder.record_id)}
    className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50 dark:hover:bg-rose-500/10">
    Cancel script
</button>
```

Use the correct record id accessor from Step 1 (`activeOrder.record_id` or the card's `record_id`).

- [ ] **Step 4: Lint + build + existing test**

```bash
cd frontend && npx eslint src/pages/Pharmacy.jsx && npm run build 2>&1 | tail -3 && npx vitest run src/pages/Pharmacy.test.jsx
```

Expected: 0 errors; build ✓; Pharmacy tests PASS (extend the test only if it already exercises the pending queue; otherwise leave it).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Pharmacy.jsx frontend/src/pages/Pharmacy.test.jsx
git commit -m "feat(pharmacy): cancel a pending prescription from the queue

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 7: Radiology request Cancel button (frontend)

**Files:**
- Modify: `frontend/src/pages/Radiology.jsx`

**Interfaces:**
- Consumes: `POST /api/radiology/{request_id}/cancel` body `{reason}` (Task 2).

- [ ] **Step 1: Read the request list + active request actions**

```bash
grep -n "request_id\|/status\|activeRequest\|status === 'Pending'\|fetch" frontend/src/pages/Radiology.jsx
```

Find where a request row / active request renders its status actions, and the reload function name.

- [ ] **Step 2: Add the cancel handler**

```jsx
const cancelRequest = async (requestId) => {
    const reason = window.prompt('Reason for cancelling this imaging request:') ?? null;
    if (reason === null) return;
    try {
        await apiClient.post(`/radiology/${requestId}/cancel`, { reason });
        toast.success('Request cancelled.');
        fetchData(); // use the page's real reload function (from Step 1)
    } catch (err) {
        toast.error(err?.response?.data?.detail || 'Could not cancel the request.');
    }
};
```

- [ ] **Step 3: Render a Cancel button for non-completed requests**

Where the active request's status controls render (e.g. the `status === 'Pending'` branch), add:

```jsx
<button type="button" onClick={() => cancelRequest(activeRequest.request_id)}
    className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50 dark:hover:bg-rose-500/10">
    Cancel request
</button>
```

- [ ] **Step 4: Lint + build**

```bash
cd frontend && npx eslint src/pages/Radiology.jsx && npm run build 2>&1 | tail -3
```

Expected: 0 errors; build ✓. (No Radiology unit test exists; lint+build is the gate.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Radiology.jsx
git commit -m "feat(radiology): cancel an imaging request from the queue

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 8: Billing invoice Void button + final verification

**Files:**
- Modify: `frontend/src/pages/Billing.jsx`

**Interfaces:**
- Consumes: `POST /api/billing/invoices/{invoice_id}/void` body `{reason}` (Task 3).

- [ ] **Step 1: Read the invoice-queue row rendering**

```bash
grep -n "invoice_id\|billing/queue\|fetchQueue\|status\|inv\." frontend/src/pages/Billing.jsx
```

Find the invoice row map and the reload function (`fetchQueue`).

- [ ] **Step 2: Add the void handler**

```jsx
const voidInvoice = async (invoiceId) => {
    if (!window.confirm('Void this unpaid invoice? This reverses its ledger posting.')) return;
    const reason = window.prompt('Reason for voiding:') ?? null;
    if (reason === null) return;
    try {
        await apiClient.post(`/billing/invoices/${invoiceId}/void`, { reason });
        toast.success('Invoice voided.');
        fetchQueue();
    } catch (err) {
        toast.error(err?.response?.data?.detail || 'Could not void the invoice.');
    }
};
```

- [ ] **Step 3: Render a Void button on each invoice row**

```jsx
<button type="button" onClick={() => voidInvoice(inv.invoice_id)}
    className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50 dark:hover:bg-rose-500/10">
    Void
</button>
```

Use the real row accessor from Step 1 (`inv.invoice_id`).

- [ ] **Step 4: Lint + build**

```bash
cd frontend && npx eslint src/pages/Billing.jsx && npm run build 2>&1 | tail -3
```

Expected: 0 errors; build ✓.

- [ ] **Step 5: Full frontend lint + build + backend suites (final gate)**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && REDIS_URL="" python -m pytest tests/test_prescription_cancel.py tests/test_radiology_cancel.py tests/test_billing_void.py -q
```

Expected: frontend lint 0 errors, build ✓; backend three suites PASS.

- [ ] **Step 6: Commit, push, open PR**

```bash
git add frontend/src/pages/Billing.jsx
git commit -m "feat(billing): void an unpaid invoice from the cashier queue

Co-Authored-By: RuFlo <ruv@ruv.net>"
git push -u origin feat/queue-deletion-all-modules
gh pr create --base development --title "feat: perfect deletion (soft-cancel) across all queues" --body "$(cat <<'EOF'
Adds a reliable soft-cancel to every queue that lacked one: Triage (Remove + Cancel), Pharmacy pending prescriptions (Cancel), Radiology requests (Cancel), Billing invoices (Void). Each is soft (status flip) with a reason + audit; entries drop out of their worklist. The Billing void reverses the invoice's GL posting via the existing accounting.reverse_entry, and is restricted to fully-unpaid Pending invoices.

No schema change — all status values already exist; the migration gate stays a no-op.

See docs/superpowers/specs/2026-06-25-queue-deletion-all-modules-design.md.

🤖 Generated with [RuFlo](https://github.com/ruvnet/ruflo)
EOF
)"
```

Expected: PR opened against `development`; CI runs.

---

## Self-Review

**Spec coverage:**
- Stream 1 (Triage remove/cancel, frontend-only) → Task 5. ✅
- Stream 2 (Pharmacy prescription cancel) → Task 1 (backend) + Task 6 (frontend). ✅
- Stream 3 (Radiology cancel) → Task 2 (backend) + Task 7 (frontend). ✅
- Stream 4 (Billing void + GL reversal, Pending-only guard) → Task 3 (backend) + Task 8 (frontend). ✅
- Soft-cancel + reason + audit everywhere → every backend task writes `log_audit` and flips a status string; no hard deletes. ✅
- No schema change → no model/migration edits in any task. ✅
- Per-module permissions → pharmacy:manage (T1), radiology:manage (T2), billing:manage (T3), patients:write via shipped endpoints (T5). ✅

**Placeholder scan:** No TBD/TODO. Each code step shows code; each test step shows the command + expected result. The "verify the real route/reload-fn name" notes are paired with explicit grep steps that reveal the exact names — acceptable because these are hand-written pages, not fixed signatures.

**Type consistency:**
- Request bodies all `{"reason": Optional[str]}` — `CancelPrescriptionRequest` (T1), `RadiologyCancelRequest` (T2), `VoidInvoiceRequest` (T3). ✅
- Endpoints return `{"message", <id key>}` consistently. ✅
- `reverse_entry(db, entry_id, user_id, reason)` used exactly per its real signature (T3). ✅
- Frontend handlers call the exact endpoints the backend tasks define. ✅

**Note for executor:** the frontend tasks (5–8) modify hand-written pages; always run the Step-1 grep first and bind to the real reload-function and id-accessor names rather than the illustrative `fetchQueue`/`fetchData`/`fetchPending` placeholders.

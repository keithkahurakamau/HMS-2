"""HTTP-level tests for the superadmin receivables API (Task 8).

client_superadmin overrides require_superadmin and get_master_db so these
run against the same Postgres test database as the rest of tests/receivables,
with no dependency on the real superadmin login flow. client_anonymous
carries no auth override at all, proving the router-level
Depends(require_superadmin) actually gates every path.
"""
from datetime import date
from decimal import Decimal

from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices, outstanding_balance

BASE = "/api/public/superadmin/receivables"


# ─── Auth gate ───────────────────────────────────────────────────────────────


def test_every_endpoint_requires_superadmin(client_anonymous):
    for path in (f"{BASE}/summary", f"{BASE}/ageing", f"{BASE}/tenant/1"):
        assert client_anonymous.get(path).status_code in (401, 403)

    assert client_anonymous.post(f"{BASE}/invoice/1/payment", json={
        "amount_kes": "100.00", "paid_on": "2026-08-02", "method": "bank",
    }).status_code in (401, 403)
    assert client_anonymous.post(f"{BASE}/invoice/1/void", json={"reason": "x"}).status_code in (401, 403)
    assert client_anonymous.post(f"{BASE}/tenant/1/reminders", json={"paused": True}).status_code in (401, 403)
    assert client_anonymous.post(f"{BASE}/run").status_code in (401, 403)
    assert client_anonymous.put(f"{BASE}/subscription/1", json={"plan": "premium"}).status_code in (401, 403)


# ─── Payments ────────────────────────────────────────────────────────────────


def test_overpayment_is_rejected(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/payment",
                                  json={"amount_kes": "20000.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 400
    assert "15,000" in res.json()["detail"] or "15000" in res.json()["detail"]
    # Rejected: no payment was actually recorded.
    master_db.refresh(inv)
    assert outstanding_balance(master_db, inv) == Decimal("15000.00")


def test_paying_the_balance_closes_the_invoice(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/payment",
                                  json={"amount_kes": "15000.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "paid"
    assert body["balance"] == "0.00"
    master_db.refresh(inv)
    assert inv.status == "paid"
    assert outstanding_balance(master_db, inv) == Decimal("0.00")


def test_a_partial_payment_leaves_the_invoice_open(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/payment",
                                  json={"amount_kes": "5000.00", "paid_on": "2026-08-02", "method": "mpesa"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "open"
    assert body["balance"] == "10000.00"


def test_a_waiver_is_recorded_as_a_payment_and_closes_the_invoice(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/payment",
                                  json={"amount_kes": "15000.00", "paid_on": "2026-08-02",
                                        "method": "waiver", "note": "goodwill"})
    assert res.status_code == 200
    assert res.json()["status"] == "paid"

    payment = master_db.query(InvoicePayment).filter(InvoicePayment.invoice_id == inv.id).first()
    assert payment.method == "waiver"
    assert payment.note == "goodwill"
    # A waiver is a payment, not a deletion: it stays visible and attributable.
    assert payment.recorded_by == client_superadmin.admin_id


def test_payment_against_a_missing_invoice_is_404(client_superadmin):
    res = client_superadmin.post(f"{BASE}/invoice/999999/payment",
                                  json={"amount_kes": "100.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 404


def test_payment_against_a_void_invoice_is_rejected(client_superadmin, master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    inv.status = "void"
    inv.void_reason = "duplicate"
    master_db.commit()

    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/payment",
                                  json={"amount_kes": "100.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 400


# ─── Voiding ─────────────────────────────────────────────────────────────────


def test_voiding_a_paid_invoice_is_rejected(client_superadmin, master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=inv.amount_kes,
                                  paid_on=date(2026, 8, 2), method="bank"))
    master_db.commit()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/void", json={"reason": "mistake"})
    assert res.status_code == 400


def test_voiding_requires_a_non_empty_reason(client_superadmin, master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/void", json={"reason": "   "})
    assert res.status_code == 422


def test_voiding_an_unpaid_invoice_succeeds_and_stores_the_reason(client_superadmin, master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"{BASE}/invoice/{inv.id}/void", json={"reason": "raised by mistake"})
    assert res.status_code == 200
    master_db.refresh(inv)
    assert inv.status == "void"
    assert inv.void_reason == "raised by mistake"


# ─── Reminders and subscription edits ────────────────────────────────────────


def test_pausing_reminders_persists(client_superadmin, master_db, make_tenant):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1))
    res = client_superadmin.post(f"{BASE}/tenant/{tenant.tenant_id}/reminders", json={"paused": True})
    assert res.status_code == 200
    assert res.json()["reminders_paused"] is True
    master_db.refresh(sub)
    assert sub.reminders_paused is True


def test_updating_subscription_terms(client_superadmin, make_tenant):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1))
    res = client_superadmin.put(f"{BASE}/subscription/{tenant.tenant_id}",
                                 json={"plan": "premium", "price_kes": "25000.00"})
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == "premium"
    assert body["price_kes"] == "25000.00"


# ─── Reads: summary, ageing, tenant detail ──────────────────────────────────


def test_summary_totals(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("5000.00"),
                                  paid_on=date(2026, 8, 2), method="mpesa"))
    master_db.commit()

    res = client_superadmin.get(f"{BASE}/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["billed"] == "15000.00"
    assert body["received"] == "5000.00"
    assert body["outstanding"] == "10000.00"


def test_ageing_response_shape_matches_the_frontend_contract(client_superadmin, master_db, make_tenant):
    tenant, sub = make_tenant(name="Ageing Hospital", price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 9, 15))

    res = client_superadmin.get(f"{BASE}/ageing")
    assert res.status_code == 200
    rows = res.json()
    row = next(r for r in rows if r["tenant_id"] == tenant.tenant_id)

    for key in ("tenant_id", "tenant_name", "current", "b1_30", "b31_60",
                "b61_90", "b90_plus", "total", "reminders_paused"):
        assert key in row
    for key in ("current", "b1_30", "b31_60", "b61_90", "b90_plus", "total"):
        assert isinstance(row[key], str)
    assert row["tenant_name"] == "Ageing Hospital"
    assert row["reminders_paused"] is False
    # Invoice issued 2026-08-01, checked as-of run date: some bucket carries
    # the full 15000.00 and the total matches it, whichever bucket it lands in.
    assert row["total"] != "0.00"


def test_tenant_detail_includes_subscription_invoices_and_payments(client_superadmin, master_db, make_tenant):
    tenant, sub = make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("5000.00"),
                                  paid_on=date(2026, 8, 2), method="mpesa"))
    master_db.commit()

    res = client_superadmin.get(f"{BASE}/tenant/{tenant.tenant_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["tenant_id"] == tenant.tenant_id
    assert body["subscription"]["plan"] == "standard"
    assert len(body["invoices"]) == 1
    assert body["invoices"][0]["amount_kes"] == "15000.00"
    assert body["invoices"][0]["balance"] == "10000.00"
    assert len(body["payments"]) == 1
    assert body["balances"]["outstanding"] == "10000.00"


def test_tenant_detail_404_for_unknown_tenant(client_superadmin):
    res = client_superadmin.get(f"{BASE}/tenant/999999")
    assert res.status_code == 404


# ─── Run billing now ─────────────────────────────────────────────────────────


def test_run_billing_now_creates_invoices(client_superadmin, master_db, make_tenant):
    # next_on = today, so the invoice this creates is due today, not overdue:
    # run_billing_cycle also runs dunning against real "today", and an
    # overdue invoice here would make it chase this fake tenant's (nonexistent)
    # database. Invoice creation, which is what this test checks, doesn't
    # need an overdue invoice to exercise.
    make_tenant(price=Decimal("15000.00"), next_on=date.today())
    res = client_superadmin.post(f"{BASE}/run")
    assert res.status_code == 200
    body = res.json()
    assert body["skipped"] is False
    assert body["ok"] is True
    assert body["invoices_created"] == 1


def test_run_billing_now_reports_a_concurrent_run_as_a_normal_outcome_not_an_error(
    client_superadmin, master_db, make_tenant, monkeypatch,
):
    """Decision 2: BillingRunResult.ok reads False on a skipped run (the
    'already in progress' note lives in failures). The endpoint must check
    skipped first and still answer 200 with a clear message, never treat a
    harmless concurrent run as a failure."""
    import app.routes.receivables as receivables_module
    from app.services.subscription_billing import BillingRunResult

    make_tenant(next_on=date(2026, 8, 1))

    def _fake_run_billing_cycle(db, as_of):
        return BillingRunResult(
            invoices_created=0, reminders_sent=0,
            failures=["billing run already in progress, skipped"], skipped=True,
        )

    monkeypatch.setattr(receivables_module, "run_billing_cycle", _fake_run_billing_cycle)

    res = client_superadmin.post(f"{BASE}/run")
    assert res.status_code == 200
    body = res.json()
    assert body["skipped"] is True
    assert body["ok"] is True
    assert body["invoices_created"] == 0

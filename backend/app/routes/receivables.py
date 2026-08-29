"""Superadmin (platform operator) receivables ledger.

Read and write surface over app.services.subscription_billing: what each
hospital owes the platform, what has been received, and the operator
actions (record a payment, void an invoice, pause reminders, run billing
now, edit the subscription terms). Everything here is notify-only: no
endpoint suspends, restricts, or downgrades a tenant, it only records money
and reminders against the ledger.

Mounted under the same public superadmin prefix as payhero_superadmin.py,
so paths land at /api/public/superadmin/receivables/... and every endpoint
is gated behind require_superadmin.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.database import get_master_db
from app.core.dependencies import require_superadmin
from app.models.master import Tenant
from app.models.subscription_billing import (
    InvoicePayment, Subscription, SubscriptionInvoice,
)
from app.schemas.receivables import (
    AgeingRow, PaymentIn, RemindersIn, RunResult, SubscriptionUpdateIn,
    SummaryOut, VoidIn,
)
from app.services.subscription_billing import (
    ageing_bucket, days_overdue, outstanding_balance, run_billing_cycle,
)

router = APIRouter(
    prefix="/api/public/superadmin/receivables",
    tags=["Superadmin - Receivables"],
    dependencies=[Depends(require_superadmin)],
)

# Bucket label (from ageing_bucket) to the fixed response key the frontend
# was built against.
_BUCKET_KEYS = {
    "current": "current",
    "1-30": "b1_30",
    "31-60": "b31_60",
    "61-90": "b61_90",
    "90+": "b90_plus",
}


def _money(value) -> str:
    """Format a Decimal (or anything Decimal() accepts) as a two-decimal
    string. Never a float: that is how rounding bugs enter a billing system."""
    return str(Decimal(value).quantize(Decimal("0.01")))


def _subscription_view(sub: Subscription) -> dict:
    return {
        "id": sub.id,
        "tenant_id": sub.tenant_id,
        "plan": sub.plan,
        "price_kes": _money(sub.price_kes),
        "cycle": sub.cycle,
        "status": sub.status,
        "started_on": sub.started_on.isoformat(),
        "next_invoice_on": sub.next_invoice_on.isoformat(),
        "reminders_paused": sub.reminders_paused,
    }


# ─── Read endpoints ──────────────────────────────────────────────────────────


@router.get("/summary", response_model=SummaryOut)
def summary(master_db: Session = Depends(get_master_db)):
    """Platform-wide totals as of today. A voided invoice never counts
    toward billed, received, outstanding, or overdue: it was cancelled,
    not collected. A waiver (InvoicePayment.method == "waiver") never
    counts toward received either: it is money written off, not money
    that came in, and this figure sits next to projected MRR precisely so
    the operator can see the real cash position."""
    as_of = date.today()
    invoices = (
        master_db.query(SubscriptionInvoice)
        .filter(SubscriptionInvoice.status != "void")
        .all()
    )

    billed = Decimal("0.00")
    outstanding = Decimal("0.00")
    overdue = Decimal("0.00")
    for inv in invoices:
        billed += Decimal(inv.amount_kes)
        balance = outstanding_balance(master_db, inv)
        if balance <= 0:
            continue
        outstanding += balance
        if inv.due_on < as_of:
            overdue += balance

    received = master_db.query(
        func.coalesce(func.sum(InvoicePayment.amount_kes), 0)
    ).join(
        SubscriptionInvoice, InvoicePayment.invoice_id == SubscriptionInvoice.id
    ).filter(
        SubscriptionInvoice.status != "void",
        InvoicePayment.method != "waiver",
    ).scalar()

    return {
        "billed": _money(billed),
        "received": _money(received),
        "outstanding": _money(outstanding),
        "overdue": _money(overdue),
    }


@router.get("/ageing", response_model=list[AgeingRow])
def ageing(master_db: Session = Depends(get_master_db)):
    """One row per billed tenant, bucketed by days overdue. Only open
    invoices with a balance still owed contribute to a bucket, so a tenant
    that is fully paid up still gets a row, just an all-zero one."""
    as_of = date.today()
    subs = (
        master_db.query(Subscription, Tenant)
        .join(Tenant, Subscription.tenant_id == Tenant.tenant_id)
        .order_by(Tenant.name)
        .all()
    )

    rows: list[dict] = []
    for sub, tenant in subs:
        buckets = {key: Decimal("0.00") for key in _BUCKET_KEYS.values()}
        invoices = (
            master_db.query(SubscriptionInvoice)
            .filter(
                SubscriptionInvoice.tenant_id == tenant.tenant_id,
                SubscriptionInvoice.status == "open",
            )
            .all()
        )
        for inv in invoices:
            balance = outstanding_balance(master_db, inv)
            if balance <= 0:
                continue
            key = _BUCKET_KEYS[ageing_bucket(days_overdue(inv, as_of))]
            buckets[key] += balance

        total = sum(buckets.values(), Decimal("0.00"))
        rows.append({
            "tenant_id": tenant.tenant_id,
            "tenant_name": tenant.name,
            **{key: _money(v) for key, v in buckets.items()},
            "total": _money(total),
            "reminders_paused": sub.reminders_paused,
        })

    return rows


@router.get("/tenant/{tenant_id}")
def tenant_detail(tenant_id: int, master_db: Session = Depends(get_master_db)):
    """Subscription, every invoice, every payment, and the running balances
    for one tenant. The console's drill-down view."""
    tenant = master_db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    sub = master_db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    invoices = (
        master_db.query(SubscriptionInvoice)
        .filter(SubscriptionInvoice.tenant_id == tenant_id)
        .order_by(SubscriptionInvoice.period_start.desc())
        .all()
    )

    as_of = date.today()
    invoice_rows: list[dict] = []
    payment_rows: list[dict] = []
    outstanding_total = Decimal("0.00")
    overdue_total = Decimal("0.00")

    for inv in invoices:
        balance = outstanding_balance(master_db, inv)
        if inv.status != "void" and balance > 0:
            outstanding_total += balance
            if inv.due_on < as_of:
                overdue_total += balance

        # A void invoice was cancelled, not collected: it must never show a
        # live-looking balance in the drawer, even though outstanding_balance
        # would still compute one off amount_kes minus payments.
        displayed_balance = Decimal("0.00") if inv.status == "void" else balance

        invoice_rows.append({
            "id": inv.id,
            "number": inv.number,
            "period_start": inv.period_start.isoformat(),
            "period_end": inv.period_end.isoformat(),
            "amount_kes": _money(inv.amount_kes),
            "issued_on": inv.issued_on.isoformat(),
            "due_on": inv.due_on.isoformat(),
            "status": inv.status,
            "void_reason": inv.void_reason,
            "balance": _money(displayed_balance),
            "days_overdue": days_overdue(inv, as_of),
            "ageing_bucket": ageing_bucket(days_overdue(inv, as_of)) if inv.status == "open" else None,
        })

        payments = (
            master_db.query(InvoicePayment)
            .filter(InvoicePayment.invoice_id == inv.id)
            .order_by(InvoicePayment.paid_on)
            .all()
        )
        for p in payments:
            payment_rows.append({
                "id": p.id,
                "invoice_id": p.invoice_id,
                "amount_kes": _money(p.amount_kes),
                "paid_on": p.paid_on.isoformat(),
                "method": p.method,
                "note": p.note,
                "recorded_by": p.recorded_by,
            })

    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "subscription": _subscription_view(sub) if sub else None,
        "invoices": invoice_rows,
        "payments": payment_rows,
        "balances": {
            "outstanding": _money(outstanding_total),
            "overdue": _money(overdue_total),
        },
    }


# ─── Write endpoints ─────────────────────────────────────────────────────────


@router.post("/invoice/{invoice_id}/payment")
def record_payment(
    invoice_id: int,
    payload: PaymentIn,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    """Record a payment or a waiver (method="waiver"). A waiver is a
    payment, not a deletion: the invoice closes and the write-off stays
    visible and attributable to whoever recorded it."""
    invoice = master_db.query(SubscriptionInvoice).filter(
        SubscriptionInvoice.id == invoice_id
    ).with_for_update().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == "void":
        raise HTTPException(status_code=400, detail="Cannot record a payment against a void invoice.")

    balance = outstanding_balance(master_db, invoice)
    if payload.amount_kes > balance:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Payment of KES {payload.amount_kes:,.2f} exceeds the "
                f"outstanding balance of KES {balance:,.2f}."
            ),
        )

    payment = InvoicePayment(
        invoice_id=invoice.id,
        amount_kes=payload.amount_kes,
        paid_on=payload.paid_on,
        method=payload.method,
        note=payload.note,
        recorded_by=admin.get("admin_id"),
    )
    master_db.add(payment)
    master_db.flush()

    new_balance = outstanding_balance(master_db, invoice)
    if new_balance <= 0:
        invoice.status = "paid"
    master_db.commit()
    master_db.refresh(invoice)

    return {
        "invoice_id": invoice.id,
        "payment_id": payment.id,
        "status": invoice.status,
        "balance": _money(new_balance),
    }


@router.post("/invoice/{invoice_id}/void")
def void_invoice(
    invoice_id: int,
    payload: VoidIn,
    master_db: Session = Depends(get_master_db),
):
    """Void an invoice raised in error. Rejected once any payment (or
    waiver) has been recorded against it: that must be dealt with first,
    voiding is not a way to hide a paid invoice."""
    invoice = master_db.query(SubscriptionInvoice).filter(
        SubscriptionInvoice.id == invoice_id
    ).with_for_update().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == "void":
        raise HTTPException(status_code=400, detail="Invoice is already void.")

    has_payment = master_db.query(InvoicePayment).filter(
        InvoicePayment.invoice_id == invoice.id
    ).first()
    if has_payment:
        raise HTTPException(
            status_code=400,
            detail="Invoice has a payment recorded; deal with the payment before voiding.",
        )

    invoice.status = "void"
    invoice.void_reason = payload.reason
    master_db.commit()

    return {"invoice_id": invoice.id, "status": invoice.status, "void_reason": invoice.void_reason}


@router.post("/tenant/{tenant_id}/reminders")
def set_reminders(
    tenant_id: int,
    payload: RemindersIn,
    master_db: Session = Depends(get_master_db),
):
    """Pause or resume dunning reminders for one tenant. Notify-only:
    pausing reminders never touches the tenant's access to the app."""
    sub = master_db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found for this tenant.")

    sub.reminders_paused = payload.paused
    master_db.commit()

    return {"tenant_id": tenant_id, "reminders_paused": sub.reminders_paused}


@router.post("/run", response_model=RunResult)
def run_now(master_db: Session = Depends(get_master_db)):
    """Run the billing cycle now, via the same entry point the daily cron
    uses, so the console and the cron cannot interleave (both serialise on
    subscription_billing.billing_lock inside run_billing_cycle).

    result.ok reads False on a skipped run too, because the "already in
    progress" note lives in result.failures. skipped is checked first and
    reported as a normal (200) outcome; only a genuine per-subscription
    failure (skipped is False, ok is False) is reported as a failure.
    """
    result = run_billing_cycle(master_db, date.today())

    if result.skipped:
        return {
            "ok": True,
            "skipped": True,
            "invoices_created": 0,
            "reminders_sent": 0,
            "failures": [],
            "message": "Billing run already in progress, skipped.",
        }

    if not result.ok:
        return {
            "ok": False,
            "skipped": False,
            "invoices_created": result.invoices_created,
            "reminders_sent": result.reminders_sent,
            "failures": result.failures,
            "message": f"Billing run completed with {len(result.failures)} failure(s).",
        }

    return {
        "ok": True,
        "skipped": False,
        "invoices_created": result.invoices_created,
        "reminders_sent": result.reminders_sent,
        "failures": [],
        "message": "Billing run completed.",
    }


@router.put("/subscription/{tenant_id}")
def update_subscription(
    tenant_id: int,
    payload: SubscriptionUpdateIn,
    master_db: Session = Depends(get_master_db),
):
    """Edit the billing terms: plan, price, status. Notify-only, same as
    the rest of this router: changing status here never suspends, restricts,
    or downgrades the tenant's actual access to the app."""
    sub = master_db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found for this tenant.")

    if payload.plan is not None:
        sub.plan = payload.plan
    if payload.price_kes is not None:
        sub.price_kes = payload.price_kes
    if payload.status is not None:
        sub.status = payload.status

    master_db.commit()
    master_db.refresh(sub)

    return _subscription_view(sub)

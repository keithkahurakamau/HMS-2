"""Per-tenant Daraja admin: hospital-wide till config, the unmatched-receipt
queue, and the transaction audit log.

Ported from routes/payhero_admin.py's shape, not reinvented. Scope is
deliberately the hospital-wide default config (MpesaConfig.department_id IS
NULL): per-department till administration already exists at the service
layer (app/services/daraja/reservation.py's config_for,
app/services/daraja/stk.py) and is exercised at that layer by
tests/daraja/test_department_tills.py, but a per-department admin surface is
not part of this task's scope.

Every secret column is Fernet-encrypted at rest and never echoed back: the
config view returns booleans (``has_consumer_key`` etc.), never the value
itself, the same discipline routes/payhero_admin.py already documents. The
callback token is the one deliberate exception, and it follows the
reveal-once pattern every API key UI uses: rotate-token hands back the
plaintext token (embedded in the real callback URLs) exactly once, at the
moment of rotation, which is the moment an operator actually needs it to
register with Safaricom. The standing GET (callback-urls) never shows it
again, only a masked placeholder. An operator who loses the URL rotates to
get a new one, which also kills the leaked old one: the correct incentive,
and it needs no new permission codename beyond the existing write gate.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, condecimal
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.c2b import c2b_readiness, register_c2b_urls
from app.services.daraja.settlement import settle_invoice_match
from app.services.daraja.status import _base_hint_token
from app.services.daraja.tokens import mint_callback_token, store_callback_token
from app.utils.encryption import encrypt_data

router = APIRouter(prefix="/api/admin/mpesa", tags=["Payments, M-Pesa Admin"])

# Reused from the Pay Hero admin surface: no dedicated write codename exists
# for the Daraja rail (the earlier "mpesa:manage" codename was renamed to
# "payhero:manage" by migration aa2b7c3d8e91, see
# app/core/dependencies.py's RequirePermission docstring), and both
# integrations configure the same underlying capability, collecting M-Pesa
# at the till, until Task 12 removes Pay Hero. Introducing a second,
# parallel write codename here would let a role hold one without the other
# for no operational reason.
_MANAGE = "payhero:manage"
_READ_ANY = ("payhero:manage", "mpesa:read")


# ─── Schemas ────────────────────────────────────────────────────────────────


class MpesaConfigSchema(BaseModel):
    shortcode: str = Field(min_length=4, max_length=20)
    shortcode_type: str = Field(default="paybill", pattern="^(paybill|till)$")
    environment: str = Field(default="sandbox", pattern="^(sandbox|production)$")

    # Secrets: optional on every save. Blank/omitted means "leave the
    # currently stored value alone": a config update must never be able to
    # wipe a working credential just because the form round-tripped it blank.
    consumer_key: Optional[str] = Field(default=None, max_length=255)
    consumer_secret: Optional[str] = Field(default=None, max_length=255)
    passkey: Optional[str] = Field(default=None, max_length=255)
    initiator_name: Optional[str] = Field(default=None, max_length=80)
    initiator_password: Optional[str] = Field(default=None, max_length=255)

    refunds_enabled: bool = False
    refund_max_amount: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("10000.00")
    refund_daily_cap: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("50000.00")
    refund_dual_approval_above: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("5000.00")

    account_reference: str = Field(default="HMS-BILLING", max_length=50)
    transaction_desc: str = Field(default="Hospital Bill Payment", max_length=100)


class AssignReceiptRequest(BaseModel):
    invoice_id: int


# ─── Config CRUD ────────────────────────────────────────────────────────────


def _default_config(db: Session) -> Optional[MpesaConfig]:
    """The hospital-wide default config row, active or not.

    Used by the WRITE path (update_mpesa_config): a save must find and
    reactivate an existing inactive row rather than insert a second
    department_id IS NULL row, which the partial unique index
    uq_mpesa_configs_default forbids. Read paths that need to know whether
    M-Pesa is actually usable right now should use _active_default_config
    instead.
    """
    return db.query(MpesaConfig).filter(MpesaConfig.department_id.is_(None)).first()


def _active_default_config(db: Session) -> Optional[MpesaConfig]:
    """The hospital-wide default config, active only.

    Matches app/services/daraja/reservation.py's config_for exactly (it
    filters on department_id IS NULL AND is_active == True for the same
    row): a deactivated default must read back as "not configured" here
    the same way it is treated as "not configured" on the actual payment
    path, not as a stale-but-visible row.
    """
    return (
        db.query(MpesaConfig)
        .filter(
            MpesaConfig.department_id.is_(None),
            MpesaConfig.is_active == True,  # noqa: E712
        )
        .first()
    )


def _public_view(config: Optional[MpesaConfig]) -> dict:
    if not config:
        return {"configured": False, "mpesa_active": False}
    return {
        "configured": True,
        "mpesa_active": bool(
            config.consumer_key_encrypted
            and config.consumer_secret_encrypted
            and config.passkey_encrypted
            and config.is_active
        ),
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "environment": config.environment,
        "has_consumer_key": bool(config.consumer_key_encrypted),
        "has_consumer_secret": bool(config.consumer_secret_encrypted),
        "has_passkey": bool(config.passkey_encrypted),
        "initiator_name": config.initiator_name,
        "has_initiator_password": bool(config.initiator_password_encrypted),
        "callback_token_configured": bool(config.callback_token_encrypted),
        "refunds_enabled": config.refunds_enabled,
        "refund_max_amount": str(config.refund_max_amount),
        "refund_daily_cap": str(config.refund_daily_cap),
        "refund_dual_approval_above": str(config.refund_dual_approval_above),
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "c2b_urls_registered_at": (
            config.c2b_urls_registered_at.isoformat() if config.c2b_urls_registered_at else None
        ),
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


@router.get("/config")
def get_mpesa_config(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
):
    return _public_view(_active_default_config(db))


@router.post("/config")
def update_mpesa_config(
    payload: MpesaConfigSchema,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission(_MANAGE)),
):
    config = _default_config(db)
    if config is None:
        config = MpesaConfig(department_id=None)
        db.add(config)

    config.shortcode = payload.shortcode.strip()
    config.shortcode_type = payload.shortcode_type
    config.environment = payload.environment
    if payload.consumer_key:
        config.consumer_key_encrypted = encrypt_data(payload.consumer_key.strip())
    if payload.consumer_secret:
        config.consumer_secret_encrypted = encrypt_data(payload.consumer_secret.strip())
    if payload.passkey:
        config.passkey_encrypted = encrypt_data(payload.passkey.strip())
    if payload.initiator_name:
        config.initiator_name = payload.initiator_name.strip()
    if payload.initiator_password:
        config.initiator_password_encrypted = encrypt_data(payload.initiator_password.strip())

    config.refunds_enabled = payload.refunds_enabled
    config.refund_max_amount = payload.refund_max_amount
    config.refund_daily_cap = payload.refund_daily_cap
    config.refund_dual_approval_above = payload.refund_dual_approval_above
    config.account_reference = payload.account_reference
    config.transaction_desc = payload.transaction_desc
    config.updated_by = user["user_id"]
    config.is_active = True

    # Mint the callback token pair on first save only: rotating it on every
    # unrelated field edit would silently invalidate every STK/C2B/status
    # URL already registered with Safaricom for this till.
    if not config.callback_token_encrypted:
        store_callback_token(config, mint_callback_token())

    db.commit()
    return {"message": "M-Pesa configuration saved.", **_public_view(config)}


# ─── C2B registration, readiness, callback URLs, token rotation ────────────
# I2: C2B is the "most dangerous flow in the migration" (see
# app/services/daraja/c2b.py's own module docstring): walk-in payments to a
# hospital's PayBill have no prior record to check an unsigned callback
# against, so a till that is never registered with Safaricom simply never
# receives Confirmation traffic at all, money at the till, nothing on the
# books, with no error anywhere to notice. register_c2b_urls is the only
# thing that tells Safaricom where to send that traffic, so it needs a
# route the same way the six inbound callbacks needed one.


@router.post("/register-c2b")
def register_c2b(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(_MANAGE)),
):
    """Register the Confirmation and Validation URLs with Safaricom for
    every active till in this tenant (hospital default and any department
    tills). Safe to call again after a token rotation or a shortcode
    change: it re-registers, it does not toggle anything."""
    return register_c2b_urls(db, callback_tenant=request.headers.get("X-Tenant-ID"))


@router.get("/c2b-readiness")
def get_c2b_readiness(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
):
    """Per-till readiness: whether C2B URLs are registered AND whether
    initiator credentials exist to verify a payment once one arrives. A
    till can show registered=true and still never settle a single payment
    if it has no initiator credentials; see handle_confirmation's own
    credential-failure handling in app/services/daraja/c2b.py."""
    return c2b_readiness(db)


# The placeholder that stands in for the token segment on a masked (not
# revealed) callback URL. Matches app/utils/log_redact.py's own
# "<redacted>" convention so the same word means the same thing everywhere
# a Daraja callback token is withheld from an output, log line or API
# response alike.
_MASKED_TOKEN = "<redacted>"


def _callback_urls_for_configs(
    configs: list[MpesaConfig], tenant_hint: Optional[str], *, reveal: bool,
) -> list[dict]:
    """(config_id, shortcode, department_id, the five callback URLs) per
    config, token segment either real (reveal=True, rotate-token only) or
    masked (reveal=False, the standing callback-urls GET). Building both
    shapes through one function keeps the URL structure itself, and the
    error shape for a config with no token minted yet, identical between
    the two call sites: only the token segment ever differs.
    """
    results = []
    for config in configs:
        try:
            base, hint, token = _base_hint_token(config, tenant_hint)
        except HTTPException as exc:
            results.append({
                "config_id": config.id,
                "shortcode": config.shortcode,
                "department_id": config.department_id,
                "error": exc.detail,
            })
            continue
        display_token = token if reveal else _MASKED_TOKEN
        results.append({
            "config_id": config.id,
            "shortcode": config.shortcode,
            "department_id": config.department_id,
            "stk_callback_url": f"{base}/api/payments/mpesa/stk/callback/{hint}/{display_token}",
            "c2b_validation_url": f"{base}/api/payments/mpesa/c2b/validation/{hint}/{display_token}",
            "c2b_confirmation_url": f"{base}/api/payments/mpesa/c2b/confirmation/{hint}/{display_token}",
            "status_result_url": f"{base}/api/payments/mpesa/status/result/{hint}/{display_token}",
            "status_timeout_url": f"{base}/api/payments/mpesa/status/timeout/{hint}/{display_token}",
        })
    return results


@router.get("/callback-urls")
def get_callback_urls(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(_MANAGE)),
):
    """The callback URL shape for every active till, token MASKED.

    Round 1 of this route returned the plaintext token here, reasoning
    that an operator legitimately needs the real URL for Safaricom
    portal-side registration. That need is real but narrower than a
    standing GET: payhero:manage (this route's own gate) is held by roles
    documented as read-only for M-Pesa (the Accountant role grants it
    specifically "for cross-checking"), so a standing reveal handed the
    live credential to a role never meant to hold one. The plaintext token
    is now revealed exactly once, in rotate-token's response, at the
    moment an operator actually needs it. This route stays gated on the
    write permission regardless, not downgraded to the any-of read set:
    see tests/daraja/test_routes.py's dedicated permission test for why
    that boundary is pinned even though nothing secret is returned here
    any more.
    """
    tenant_hint = request.headers.get("X-Tenant-ID")
    configs = db.query(MpesaConfig).filter(MpesaConfig.is_active == True).all()  # noqa: E712
    return {"tills": _callback_urls_for_configs(configs, tenant_hint, reveal=False)}


@router.post("/rotate-token")
def rotate_callback_token(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(_MANAGE)),
):
    """Mint a fresh callback token for the hospital-wide default till, and
    reveal it exactly once, embedded in the real callback URLs this
    response carries: the same reveal-once pattern every API key UI uses.
    callback-urls never shows the plaintext again after this call returns;
    an operator who loses this response has to rotate again to see it.

    The whole authentication design in app/core/daraja_callback.py rests
    on this token being unguessable AND rotatable; without this route a
    leaked token had no remediation short of a manual database UPDATE.
    Rotating invalidates every Confirmation/Validation URL already
    registered with Safaricom for this till (the old token is baked into
    those URLs at registration time): register-c2b must be called again
    afterwards for the API-based registration path, and the URLs in this
    response are what a portal-side registration pastes in directly.
    Scoped to the hospital default only, matching this file's config-CRUD
    scope; a per-department token rotation route is not part of this
    surface.
    """
    config = _default_config(db)
    if config is None:
        raise HTTPException(status_code=400, detail="M-Pesa is not configured yet.")
    store_callback_token(config, mint_callback_token())
    db.commit()
    urls = _callback_urls_for_configs([config], request.headers.get("X-Tenant-ID"), reveal=True)
    return {
        "message": (
            "Callback token rotated. This is the only time the new token is "
            "shown: copy the URLs below into the Safaricom developer portal "
            "if you register manually, or call register-c2b to re-register "
            "via the API. Existing URLs registered with the old token are "
            "now dead."
        ),
        "urls": urls[0] if urls else None,
        **_public_view(config),
    }


# ─── Unmatched-receipt queue ────────────────────────────────────────────────


@router.get("/unmatched")
def list_unmatched_receipts(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
    limit: int = 100,
):
    rows = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.match_basis == "unmatched")
        .order_by(MpesaTransaction.transaction_date.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "id": r.id,
            "phone_number": r.phone_number,
            "amount": str(r.amount or 0),
            "receipt_number": r.receipt_number,
            "bill_ref_number": r.bill_ref_number,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
        }
        for r in rows
    ]


@router.post("/unmatched/{txn_id}/assign")
def assign_unmatched_receipt(
    txn_id: int,
    payload: AssignReceiptRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _user: dict = Depends(RequirePermission(_MANAGE)),
):
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if txn.match_basis and txn.match_basis != "unmatched":
        raise HTTPException(status_code=400, detail=f"Receipt already in state '{txn.match_basis}'.")

    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invoice is already fully paid.")

    # I3: lock the invoice row before settling, the same discipline every
    # other Daraja settlement path uses (see status.py's own comment on why
    # populate_existing() is not optional here: an unlocked read against an
    # invoice already loaded into this session would settle against a
    # stale amount_paid). Two settlements racing this invoice without the
    # lock would have the second discard the first's credit, under-crediting
    # a patient for money they already paid.
    invoice = (
        db.query(Invoice)
        .filter(Invoice.invoice_id == invoice.invoice_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invoice is already fully paid.")

    txn.status = "Success"
    settle_invoice_match(
        db,
        invoice=invoice,
        txn=txn,
        match_basis="manual",
        user_id=current_user.get("user_id"),
    )
    db.commit()
    db.refresh(txn)
    return {"status": "assigned", "invoice_id": invoice.invoice_id, "transaction_id": txn.id}


# ─── Transactions audit ─────────────────────────────────────────────────────


@router.get("/transactions")
def get_transactions(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
):
    transactions = (
        db.query(MpesaTransaction)
        .order_by(MpesaTransaction.transaction_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "invoice_id": t.invoice_id,
            "phone_number": t.phone_number,
            "amount": str(t.amount) if t.amount is not None else None,
            "status": t.status,
            "receipt_number": t.receipt_number,
            "external_reference": t.external_reference,
            "result_desc": t.result_desc,
            "transaction_type": t.transaction_type,
            "bill_ref_number": t.bill_ref_number,
            "match_basis": t.match_basis,
            "verified_at": t.verified_at.isoformat() if t.verified_at else None,
            "created_at": t.transaction_date.isoformat() if t.transaction_date else None,
        }
        for t in transactions
    ]

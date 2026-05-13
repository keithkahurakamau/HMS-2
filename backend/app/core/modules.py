"""
Module catalogue + tenant entitlement resolution.

MediFleet sells the platform as a base subscription plus à-la-carte modules.
Each tenant carries a JSON ``feature_flags`` column on the master ``tenants``
row, of the shape::

    {"pharmacy": true, "radiology": false, ...}

This file is the single source of truth for:

  * what modules exist (their key, label, default-on status, and description),
  * which URL prefixes they govern,
  * which modules are *always on* and cannot be gated off (Support is one —
    locking a tenant out of support would prevent them from buying more).

The gate middleware (see ``module_gate.py``) imports the URL → module map
defined here.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config.database import MasterSessionLocal
from app.models.master import Tenant

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleDef:
    key: str
    label: str
    description: str
    default_enabled: bool = False  # opt-in by default
    always_on: bool = False  # cannot be disabled even by explicit flag


# Order here drives the order shown in the Tenant Modules UI.
MODULES: Tuple[ModuleDef, ...] = (
    # ── always-on (base subscription) ────────────────────────────────────
    ModuleDef("patients",     "Patient Registry",   "Register and search patients.",            True, True),
    ModuleDef("appointments", "Appointments",       "Book and manage appointments.",            True, True),
    ModuleDef("dashboard",    "Dashboard",          "Role-based home page and worker agenda.",  True, True),
    ModuleDef("settings",     "Settings",           "Account, branding, security settings.",    True, True),
    ModuleDef("support",      "Support",            "In-app helpdesk to the MediFleet team.",   True, True),
    ModuleDef("messaging",    "Internal Messaging", "Staff-to-staff messaging.",                True, True),
    ModuleDef("notifications","Notifications",      "System and clinical notifications.",       True, True),
    ModuleDef("users",        "User Management",    "Staff, roles, permissions.",               True, True),
    ModuleDef("auth",         "Authentication",     "Login, refresh, password reset.",          True, True),

    # ── optional add-ons (à-la-carte) ────────────────────────────────────
    ModuleDef("clinical",     "Clinical Desk",      "Encounters, diagnoses, prescriptions.",    True),
    ModuleDef("laboratory",   "Laboratory",         "Lab orders, results, billing integration.", False),
    ModuleDef("radiology",    "Radiology",          "Imaging orders, reports, DICOM viewer.",   False),
    ModuleDef("pharmacy",     "Pharmacy",           "Dispensing, stock movement, alerts.",      False),
    ModuleDef("inventory",    "Inventory",          "Stores, suppliers, purchase orders.",      False),
    ModuleDef("wards",        "Wards & In-Patient", "Bed management, admissions, rounds.",      False),
    ModuleDef("billing",      "Billing",            "Invoicing, statements, payment plans.",    False),
    ModuleDef("cheques",      "Cheques",            "Cheque receipting and reconciliation.",    False),
    ModuleDef("medical_history","Medical History",  "Longitudinal patient history.",            False),
    ModuleDef("mpesa",        "M-Pesa",             "Mobile-money collections and refunds.",    False),
    ModuleDef("analytics",    "Analytics",          "Aggregated dashboards and reports.",       False),
    ModuleDef("patient_portal","Patient Portal",    "Self-service portal for patients.",        False),
    ModuleDef("branding",     "Branding",           "Logos, colours, document templates.",      False),
    ModuleDef("referrals",    "Referrals",          "Out-bound and in-bound referrals.",        False),
    ModuleDef("privacy",      "Privacy",            "Consent, DSAR, audit logs.",               False),
)

# Convenience lookups.
BY_KEY: Dict[str, ModuleDef] = {m.key: m for m in MODULES}
ALWAYS_ON: frozenset = frozenset(m.key for m in MODULES if m.always_on)
DEFAULT_ENABLED: frozenset = frozenset(m.key for m in MODULES if m.default_enabled or m.always_on)

# URL-prefix → module key. Longest-prefix wins, so /api/public/branding/...
# doesn't accidentally hit the public router's gate.
URL_PREFIX_MAP: Tuple[Tuple[str, str], ...] = (
    # always-on routes — listed first for clarity, gate.py short-circuits them.
    ("/api/auth/",                        "auth"),
    ("/api/users/",                       "users"),
    ("/api/admin/",                       "users"),
    ("/api/me/",                          "users"),
    ("/api/support/",                     "support"),
    ("/api/notifications/",               "notifications"),
    ("/api/messaging/",                   "messaging"),
    ("/api/dashboard/",                   "dashboard"),
    ("/api/settings/",                    "settings"),
    ("/api/patients/",                    "patients"),
    ("/api/appointments/",                "appointments"),
    ("/api/queue/",                       "patients"),
    # optional modules.
    ("/api/clinical/",                    "clinical"),
    ("/api/laboratory/",                  "laboratory"),
    ("/api/radiology/",                   "radiology"),
    ("/api/pharmacy/",                    "pharmacy"),
    ("/api/inventory/",                   "inventory"),
    ("/api/wards/",                       "wards"),
    ("/api/billing/",                     "billing"),
    ("/api/cheques/",                     "cheques"),
    ("/api/medical-history/",             "medical_history"),
    ("/api/medical_history/",             "medical_history"),
    ("/api/mpesa/",                       "mpesa"),
    ("/api/analytics/",                   "analytics"),
    ("/api/patient-portal/",              "patient_portal"),
    ("/api/branding/",                    "branding"),
    ("/api/referrals/",                   "referrals"),
    ("/api/privacy/",                     "privacy"),
)


def url_to_module(path: str) -> Optional[str]:
    """Return the module key responsible for *path*, or None for paths that
    fall outside the gated surface (public, websocket, health check, etc.)."""
    if not path.startswith("/api/"):
        return None
    if path.startswith("/api/public/"):
        return None
    for prefix, mod in URL_PREFIX_MAP:
        if path.startswith(prefix):
            return mod
    return None


# ─── Tenant entitlements ────────────────────────────────────────────────────
def _parse_flags(raw: Optional[str]) -> Dict[str, bool]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k): bool(v) for k, v in data.items()}
    except (ValueError, TypeError):
        logger.warning("Tenant feature_flags JSON is malformed; treating as empty.")
        return {}


def resolve_enabled_modules(flags_raw: Optional[str]) -> List[str]:
    """Compose the effective enabled set: defaults ∪ explicit-true ∪ always-on
    − explicit-false (for non-always-on modules).
    """
    flags = _parse_flags(flags_raw)
    enabled: set = set(DEFAULT_ENABLED)
    for key, value in flags.items():
        if key not in BY_KEY:
            continue
        if value:
            enabled.add(key)
        else:
            if key not in ALWAYS_ON:
                enabled.discard(key)
    # Always-on are never disable-able, regardless of flags.
    enabled |= ALWAYS_ON
    return sorted(enabled)


def is_module_enabled(flags_raw: Optional[str], module_key: str) -> bool:
    if module_key in ALWAYS_ON:
        return True
    return module_key in set(resolve_enabled_modules(flags_raw))


# Tenant entitlement lookup, cached briefly so the gate middleware doesn't
# hammer the master DB on every request. Cache by tenant db_name; values are
# the raw feature_flags JSON string (or empty string for "no flags row").
_TENANT_FLAG_CACHE_PREFIX = "tenant:flags"
_TENANT_FLAG_TTL = 60  # seconds — short enough that toggles in the admin UI
                       # show up quickly, long enough to cut DB load.


def get_tenant_flags_cached(tenant_db_name: str) -> str:
    """Return the raw feature_flags JSON for *tenant_db_name*, cached for
    `_TENANT_FLAG_TTL` seconds. Returns ``""`` when the tenant is unknown
    or has no flags row."""
    from app.core import cache  # local import — avoids cycle at module load
    hit = cache.get(_TENANT_FLAG_CACHE_PREFIX, tenant_db_name, tenant=None)
    if hit is not None:
        return hit

    raw: str = ""
    session: Session = MasterSessionLocal()
    try:
        tenant = session.query(Tenant).filter(Tenant.db_name == tenant_db_name).first()
        if tenant and tenant.feature_flags:
            raw = tenant.feature_flags
    finally:
        session.close()

    cache.set(_TENANT_FLAG_CACHE_PREFIX, tenant_db_name, raw, ttl_seconds=_TENANT_FLAG_TTL, tenant=None)
    return raw


def invalidate_tenant_flags_cache(tenant_db_name: Optional[str] = None) -> None:
    """Drop the cached entitlement for a tenant (or every tenant)."""
    from app.core import cache
    if tenant_db_name:
        cache.invalidate(_TENANT_FLAG_CACHE_PREFIX, tenant_db_name, tenant=None)
    else:
        cache.invalidate_prefix(_TENANT_FLAG_CACHE_PREFIX, tenant=None)


def serialize_module_catalogue(enabled: Iterable[str]) -> List[Dict]:
    """Return the public shape used by the /api/me/modules endpoint."""
    enabled_set = set(enabled)
    return [
        {
            "key": m.key,
            "label": m.label,
            "description": m.description,
            "enabled": m.key in enabled_set,
            "always_on": m.always_on,
        }
        for m in MODULES
    ]

"""Module-aligned permission catalogue + role grants

Revision ID: f1a8d3c92e57
Revises: e7c63a82d51f
Create Date: 2026-05-17 14:00:00.000000

Adds one permission per superadmin-toggleable module so admins can grant
per-module access from the role editor instead of bundled aliases (e.g.
``inventory:*`` was previously gated behind ``pharmacy:read``). Refreshes
auto-stub descriptions to the human-readable strings now tracked in
``PERMISSION_DESCRIPTIONS``. Idempotent — only inserts/grants rows that
are missing.

The complementary `tenant_provisioning.backfill_admin_permissions` hook
performs the same reconciliation on every boot; this migration ensures
the change lands even on tenants that don't go through the boot path
(e.g. a fresh deploy with stale `alembic_version`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a8d3c92e57"
down_revision: Union[str, Sequence[str], None] = "e7c63a82d51f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Keep this in lockstep with PERMISSION_CATALOG in
# app/services/tenant_provisioning.py. Only the *new* codenames go here —
# pre-existing ones are left alone except for description refresh.
NEW_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("dashboard:view",         "Access the role-based home dashboard"),
    ("appointments:read",      "View the appointment calendar"),
    ("appointments:manage",    "Book, reschedule, and cancel appointments"),
    ("inventory:read",         "View stores, suppliers, and stock levels"),
    ("inventory:manage",       "Manage stores, batches, transfers, purchase orders"),
    ("radiology:read",         "View imaging orders and reports"),
    ("wards:read",             "View ward roster, admissions, and bed status"),
    ("mpesa:read",             "View M-Pesa transaction log and reconciliation"),
    ("mpesa:manage",           "Configure Daraja credentials and register C2B"),
    ("referrals:read",         "View incoming and outgoing referrals"),
    ("branding:manage",        "Customise logo, colours, and document templates"),
    ("notifications:manage",   "Configure notification templates and channels"),
    ("analytics:view",         "View aggregated dashboards and reports"),
    ("patient_portal:manage",  "Administer the patient self-service portal"),
    ("privacy:read",           "Review KDPA consent, DSAR, and privacy logs"),
    ("privacy:manage",         "Manage KDPA consent, DSAR, and privacy logs"),
)

# Additive role grants — codenames the named role should receive whenever
# the migration runs. Mirrors the non-Admin entries of ROLE_GRANTS.
ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "Doctor": (
        "appointments:read", "appointments:manage",
        "inventory:read", "radiology:read", "wards:read",
        "referrals:read", "dashboard:view", "laboratory:manage",
    ),
    "Nurse": (
        "appointments:read", "appointments:manage",
        "wards:read", "inventory:read", "dashboard:view",
    ),
    "Pharmacist": (
        "inventory:read", "inventory:manage",
        "appointments:read", "dashboard:view",
    ),
    "Lab Technician": (
        "inventory:read", "appointments:read", "dashboard:view",
    ),
    "Radiologist": (
        "radiology:read", "appointments:read", "dashboard:view",
    ),
    "Receptionist": (
        "appointments:read", "appointments:manage", "mpesa:read", "dashboard:view",
    ),
    "Accountant": (
        "mpesa:read", "analytics:view", "appointments:read", "dashboard:view",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. UPSERT permission rows.
    for code, desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (codename, description) "
                "SELECT :c, :d "
                "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :c)"
            ).bindparams(c=code, d=desc)
        )
        # Refresh stale auto-stub descriptions ("Allows X") without
        # clobbering any custom edits an admin may have made.
        op.execute(
            sa.text(
                "UPDATE permissions SET description = :d "
                "WHERE codename = :c AND description = :stub"
            ).bindparams(c=code, d=desc, stub=f"Allows {code}")
        )

    # 2. Grant the new permissions to the Admin role wholesale — Admin is
    #    defined as having every codename in the catalogue.
    for code, _desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.role_id, p.permission_id "
                "FROM roles r CROSS JOIN permissions p "
                "WHERE p.codename = :c AND r.name = 'Admin' "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM role_permissions rp "
                "    WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id"
                ")"
            ).bindparams(c=code)
        )

    # 3. Additive grants for the other built-in roles.
    for role_name, codes in ROLE_GRANTS.items():
        for code in codes:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT r.role_id, p.permission_id "
                    "FROM roles r CROSS JOIN permissions p "
                    "WHERE p.codename = :c AND r.name = :role "
                    "AND NOT EXISTS ("
                    "    SELECT 1 FROM role_permissions rp "
                    "    WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id"
                    ")"
                ).bindparams(c=code, role=role_name)
            )


def downgrade() -> None:
    # Drop the role grants first, then the permission rows.
    for code, _desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id IN ("
                "    SELECT permission_id FROM permissions WHERE codename = :c"
                ")"
            ).bindparams(c=code)
        )
        op.execute(
            sa.text("DELETE FROM permissions WHERE codename = :c").bindparams(c=code)
        )

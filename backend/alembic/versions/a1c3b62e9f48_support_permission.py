"""Add support:manage permission, grant to Admin

Revision ID: a1c3b62e9f48
Revises: f9b2c81e4a37
Create Date: 2026-05-12 18:00:00.000000

The support_tickets / support_messages tables themselves live on the
master DB (managed by scripts/migrate_all_tenants.py's MASTER_DB_PATCHES
block). This migration only seeds the *permission* on tenant DBs so the
Admin role can call /api/support/.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c3b62e9f48"
down_revision: Union[str, Sequence[str], None] = "f9b2c81e4a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO permissions (codename, description) "
            "SELECT :c, :d WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :c)"
        ).bindparams(c="support:manage", d="Raise and follow up MediFleet support tickets")
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'support:manage'
          AND r.name = 'Admin'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename = 'support:manage');"
    )
    op.execute("DELETE FROM permissions WHERE codename = 'support:manage';")

"""Grant patients:write to Nurse (midwife newborn registration)

The one-click newborn→patient registration requires patients:write. Nurses
are the ones present at the delivery, so without this a midwife hits a 403
and the newborn gets registered late (or by someone who wasn't there).

Revision ID: c4f1a2b8d6e3
Revises: b7e4a1c9d2f5
Create Date: 2026-07-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c4f1a2b8d6e3"
down_revision: Union[str, Sequence[str], None] = "b7e4a1c9d2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'patients:write'
          AND r.name = 'Nurse'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT role_id FROM roles WHERE name = 'Nurse')
          AND permission_id IN (
              SELECT permission_id FROM permissions WHERE codename = 'patients:write'
          );
        """
    )

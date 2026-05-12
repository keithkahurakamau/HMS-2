"""Radiology revamp — exam catalog + priority/billed_price/contrast

Revision ID: a91c3d27e845
Revises: f3d8e91a64b2
Create Date: 2026-05-12 14:30:00.000000

Adds:
- radiology_exam_catalog       (master directory of imaging services)
- radiology_requests.catalog_id (optional FK back to catalog)
- radiology_requests.priority   (Routine / Urgent / STAT)
- radiology_requests.billed_price (locked at order time)
- radiology_results.contrast_used (free-text descriptor)
- adds 'radiology:manage' permission.

Idempotent so it can be re-run safely on partially-migrated tenants.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91c3d27e845"
down_revision: Union[str, Sequence[str], None] = "f3d8e91a64b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "radiology_exam_catalog" not in inspector.get_table_names():
        op.create_table(
            "radiology_exam_catalog",
            sa.Column("catalog_id", sa.Integer(), primary_key=True),
            sa.Column("exam_name", sa.String(length=200), nullable=False),
            sa.Column("modality", sa.String(length=50), nullable=False),
            sa.Column("body_part", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("base_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("requires_prep", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("requires_contrast", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("default_findings_template", sa.Text(), nullable=True),
            sa.Column("default_impression_template", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.UniqueConstraint("exam_name", name="uq_radiology_exam_catalog_exam_name"),
        )
        op.create_index(
            "ix_radiology_exam_catalog_exam_name",
            "radiology_exam_catalog",
            ["exam_name"],
        )

    op.execute(
        "ALTER TABLE radiology_requests "
        "ADD COLUMN IF NOT EXISTS catalog_id INTEGER REFERENCES radiology_exam_catalog(catalog_id) ON DELETE SET NULL;"
    )
    op.execute(
        "ALTER TABLE radiology_requests "
        "ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'Routine';"
    )
    op.execute(
        "ALTER TABLE radiology_requests "
        "ADD COLUMN IF NOT EXISTS billed_price NUMERIC(10, 2);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_radiology_requests_catalog_id "
        "ON radiology_requests (catalog_id);"
    )

    op.execute(
        "ALTER TABLE radiology_results "
        "ADD COLUMN IF NOT EXISTS contrast_used VARCHAR(120);"
    )

    op.execute(
        """
        INSERT INTO permissions (codename, description)
        SELECT 'radiology:manage',
               'Create and edit the radiology exam catalog'
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions WHERE codename = 'radiology:manage'
        );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'radiology:manage'
          AND r.name IN ('Admin', 'Radiologist', 'Radiology Tech')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename = 'radiology:manage');"
    )
    op.execute("DELETE FROM permissions WHERE codename = 'radiology:manage';")
    op.execute("ALTER TABLE radiology_results DROP COLUMN IF EXISTS contrast_used;")
    op.execute("DROP INDEX IF EXISTS ix_radiology_requests_catalog_id;")
    op.execute("ALTER TABLE radiology_requests DROP COLUMN IF EXISTS billed_price;")
    op.execute("ALTER TABLE radiology_requests DROP COLUMN IF EXISTS priority;")
    op.execute("ALTER TABLE radiology_requests DROP COLUMN IF EXISTS catalog_id;")
    op.execute("DROP INDEX IF EXISTS ix_radiology_exam_catalog_exam_name;")
    op.execute("DROP TABLE IF EXISTS radiology_exam_catalog;")

"""Lab flexibility revamp — barcode-optional, reusable reagents, dynamic parameters

Revision ID: f3d8e91a64b2
Revises: e2c5b9314f78
Create Date: 2026-05-12 14:00:00.000000

Adds:
- inventory_items.is_reusable          (reagents/glassware that get logged
                                        on use but don't decrement stock)
- inventory_usage_logs.is_reusable_use (per-usage flag — was this usage a
                                        reusable item?)
- lab_test_catalog.requires_barcode    (defaults False — only LIS-grade
                                        analyzers need barcodes)
- lab_catalog_parameters               (per-test result-field definitions
                                        with units & reference ranges, so
                                        new tests are pure data, no code)
- adds 'laboratory:manage' permission and grants it to Admin + Lab Tech.

Idempotent: ``ADD COLUMN IF NOT EXISTS`` / guarded INSERTs so re-running on a
partially-migrated tenant is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3d8e91a64b2"
down_revision: Union[str, Sequence[str], None] = "e2c5b9314f78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- inventory_items.is_reusable -------------------------------------
    op.execute(
        "ALTER TABLE inventory_items "
        "ADD COLUMN IF NOT EXISTS is_reusable BOOLEAN NOT NULL DEFAULT FALSE;"
    )

    # --- inventory_usage_logs.is_reusable_use -----------------------------
    op.execute(
        "ALTER TABLE inventory_usage_logs "
        "ADD COLUMN IF NOT EXISTS is_reusable_use BOOLEAN NOT NULL DEFAULT FALSE;"
    )

    # --- lab_test_catalog.requires_barcode --------------------------------
    op.execute(
        "ALTER TABLE lab_test_catalog "
        "ADD COLUMN IF NOT EXISTS requires_barcode BOOLEAN NOT NULL DEFAULT FALSE;"
    )

    # --- lab_catalog_parameters table ------------------------------------
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "lab_catalog_parameters" not in inspector.get_table_names():
        op.create_table(
            "lab_catalog_parameters",
            sa.Column("parameter_id", sa.Integer(), primary_key=True),
            sa.Column(
                "catalog_id",
                sa.Integer(),
                sa.ForeignKey("lab_test_catalog.catalog_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("key", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("value_type", sa.String(length=20), nullable=False, server_default=sa.text("'number'")),
            sa.Column("choices", sa.Text(), nullable=True),
            sa.Column("ref_low", sa.Float(), nullable=True),
            sa.Column("ref_high", sa.Float(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.create_index(
            "ix_lab_catalog_parameters_catalog_id",
            "lab_catalog_parameters",
            ["catalog_id"],
        )

    # --- new permission --------------------------------------------------
    op.execute(
        """
        INSERT INTO permissions (codename, description)
        SELECT 'laboratory:manage',
               'Create and edit the laboratory test catalog'
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions WHERE codename = 'laboratory:manage'
        );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'laboratory:manage'
          AND r.name IN ('Admin', 'Lab Tech', 'Laboratory')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename = 'laboratory:manage');"
    )
    op.execute("DELETE FROM permissions WHERE codename = 'laboratory:manage';")
    op.execute("DROP INDEX IF EXISTS ix_lab_catalog_parameters_catalog_id;")
    op.execute("DROP TABLE IF EXISTS lab_catalog_parameters;")
    op.execute("ALTER TABLE lab_test_catalog DROP COLUMN IF EXISTS requires_barcode;")
    op.execute("ALTER TABLE inventory_usage_logs DROP COLUMN IF EXISTS is_reusable_use;")
    op.execute("ALTER TABLE inventory_items DROP COLUMN IF EXISTS is_reusable;")

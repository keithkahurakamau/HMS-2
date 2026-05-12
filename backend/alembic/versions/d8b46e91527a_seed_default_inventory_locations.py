"""Seed default inventory locations

Revision ID: d8b46e91527a
Revises: c3a8d6e2b914
Create Date: 2026-05-08 11:00:00.000000

The frontend always assumed Main Store / Pharmacy / Laboratory / Wards exist,
but tenant_provisioning never inserted them. Adding a stock batch against
"Wards" failed with a ForeignKeyViolation because location_id=4 had no row in
``locations``. This migration backfills every existing tenant idempotently;
``tenant_provisioning`` is updated in the same change so freshly-provisioned
tenants come up with the same set already in place.

The seed is idempotent (``WHERE NOT EXISTS``), so it is safe to re-run on
tenants that already have any subset of the locations.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d8b46e91527a"
down_revision: Union[str, Sequence[str], None] = "c3a8d6e2b914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_LOCATIONS = [
    ("Main Store", "Central inventory store — receives all procurements"),
    ("Pharmacy", "Dispensing point for prescriptions and OTC sales"),
    ("Laboratory", "Reagents and consumables for diagnostic testing"),
    ("Wards", "Bedside consumables and PRN drug stock"),
]


def upgrade() -> None:
    for name, description in _DEFAULT_LOCATIONS:
        op.execute(
            f"""
            INSERT INTO locations (name, description)
            SELECT '{name}', '{description}'
            WHERE NOT EXISTS (
                SELECT 1 FROM locations WHERE name = '{name}'
            );
            """
        )


def downgrade() -> None:
    # Pulling the rows out is risky because stock_batches references them.
    # Refuse the downgrade rather than orphaning data — the operator can
    # delete rows manually after migrating data away.
    raise RuntimeError(
        "Refusing to downgrade default-locations seed: stock_batches and "
        "stock_transfers reference these rows. Migrate dependent data first."
    )

"""radiology_request indexes (perf)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-25

Additive indexes on the radiology worklist's hot filter/join columns. No data change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_radiology_requests_patient_id", "radiology_requests", ["patient_id"])
    op.create_index("ix_radiology_requests_status", "radiology_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_radiology_requests_status", table_name="radiology_requests")
    op.drop_index("ix_radiology_requests_patient_id", table_name="radiology_requests")

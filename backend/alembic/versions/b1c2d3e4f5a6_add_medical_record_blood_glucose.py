"""add medical_record blood_glucose

Revision ID: b1c2d3e4f5a6
Revises: a6f2d9c4e7b1
Create Date: 2026-06-24

Additive, nullable column so the doctor's encounter can store the Random Blood
Sugar (RBS) captured at triage. Backward-compatible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a6f2d9c4e7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("medical_records") as batch:
        batch.add_column(sa.Column("blood_glucose", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("medical_records") as batch:
        batch.drop_column("blood_glucose")

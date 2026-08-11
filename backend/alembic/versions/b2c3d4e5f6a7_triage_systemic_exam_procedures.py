"""Triage parity: triage_records.systemic_exam + procedures (JSON strings)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("triage_records", sa.Column("systemic_exam", sa.Text(), nullable=True))
    op.add_column("triage_records", sa.Column("procedures", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("triage_records", "procedures")
    op.drop_column("triage_records", "systemic_exam")

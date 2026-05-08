"""Add per-user permission overrides

Revision ID: c3a8d6e2b914
Revises: f7a9c2d1e480
Create Date: 2026-05-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a8d6e2b914'
down_revision: Union[str, Sequence[str], None] = 'f7a9c2d1e480'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_permission_overrides",
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id", sa.Integer(),
            sa.ForeignKey("permissions.permission_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_perm_overrides_user", "user_permission_overrides", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_perm_overrides_user", table_name="user_permission_overrides")
    op.drop_table("user_permission_overrides")

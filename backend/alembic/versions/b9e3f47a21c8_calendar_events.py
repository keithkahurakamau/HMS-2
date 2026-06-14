"""Personal calendar events

Revision ID: b9e3f47a21c8
Revises: a3f9c1d8b240
Create Date: 2026-06-14 10:00:00.000000

1 new tenant table:
- calendar_events  (user-scoped personal events overlaid on the shared
                    appointments calendar: leave, meetings, reminders)

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9e3f47a21c8"
down_revision: Union[str, Sequence[str], None] = "a3f9c1d8b240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _missing(inspector, "calendar_events"):
        op.create_table(
            "calendar_events",
            sa.Column("event_id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.user_id", ondelete="CASCADE"),
                      index=True, nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=40), nullable=False, server_default="personal"),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_calendar_user_start", "calendar_events", ["user_id", "start_at"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS calendar_events CASCADE;")

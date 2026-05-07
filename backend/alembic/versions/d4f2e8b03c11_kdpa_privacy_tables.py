"""KDPA privacy tables and append-only audit guards

Revision ID: d4f2e8b03c11
Revises: c91a2f4b8d10
Create Date: 2026-05-07 12:00:00.000000

Adds the breach_incidents table and installs PostgreSQL triggers that
prevent UPDATE / DELETE on the audit_logs and data_access_logs tables.
This makes those tables append-only at the database layer — even a
compromised admin with direct DB access cannot quietly rewrite history.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f2e8b03c11'
down_revision: Union[str, Sequence[str], None] = 'c91a2f4b8d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION enforce_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only. UPDATE and DELETE are forbidden under KDPA audit retention.', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # 1. breach_incidents table
    op.create_table(
        "breach_incidents",
        sa.Column("incident_id", sa.Integer(), primary_key=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reported_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default=sa.text("'Medium'")),
        sa.Column("nature", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_categories", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("estimated_records_affected", sa.Integer(), nullable=True),
        sa.Column("affected_patient_ids", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("likely_consequences", sa.Text(), nullable=True),
        sa.Column("mitigation_steps", sa.Text(), nullable=True),
        sa.Column("odpc_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("odpc_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("odpc_reference", sa.String(length=100), nullable=True),
        sa.Column("patients_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patients_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'Open'")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_breach_status_detected", "breach_incidents", ["status", "detected_at"])

    # 2. Append-only triggers on audit tables
    op.execute(APPEND_ONLY_FN)
    for table in ("audit_logs", "data_access_logs"):
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_{table}_no_update ON {table};
            CREATE TRIGGER trg_{table}_no_update
              BEFORE UPDATE OR DELETE ON {table}
              FOR EACH ROW EXECUTE FUNCTION enforce_append_only();
        """)


def downgrade() -> None:
    for table in ("audit_logs", "data_access_logs"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_update ON {table};")
    op.execute("DROP FUNCTION IF EXISTS enforce_append_only();")

    op.drop_index("idx_breach_status_detected", table_name="breach_incidents")
    op.drop_table("breach_incidents")

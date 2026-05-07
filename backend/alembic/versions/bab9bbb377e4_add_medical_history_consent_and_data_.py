"""Add Medical History, Consent, and Data Access Log tables

Revision ID: bab9bbb377e4
Revises: ea2c5028a38c
Create Date: 2026-04-30 10:23:49.176898

NOTE: A previous version of this migration was empty (`pass`). It is now
implemented so `alembic upgrade head` works against a clean database.
Adds:
    consent_records         — KDPA / Health Act 2017 informed consent
    medical_history_entries — long-form patient medical history
    data_access_logs        — KDPA read-access ledger
Also drops the legacy `drug_inventory` table that the initial schema
created but no model references.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bab9bbb377e4'
down_revision: Union[str, Sequence[str], None] = 'ea2c5028a38c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. consent_records
    op.create_table(
        'consent_records',
        sa.Column('consent_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('consent_type', sa.String(length=100), nullable=False),
        sa.Column('consent_given', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('consent_method', sa.String(length=100), nullable=False, server_default=sa.text("'Written'")),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('consent_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consented_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.patient_id']),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('consent_id'),
    )
    op.create_index(op.f('ix_consent_records_patient_id'), 'consent_records', ['patient_id'], unique=False)
    op.create_index(op.f('ix_consent_records_consented_at'), 'consent_records', ['consented_at'], unique=False)
    op.create_index('idx_consent_patient_type', 'consent_records', ['patient_id', 'consent_type'], unique=False)

    # 2. medical_history_entries
    op.create_table(
        'medical_history_entries',
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('entry_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('event_date', sa.String(length=50), nullable=True),
        sa.Column('severity', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True, server_default=sa.text("'Active'")),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_sensitive', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.patient_id']),
        sa.ForeignKeyConstraint(['record_id'], ['medical_records.record_id']),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('entry_id'),
    )
    op.create_index(op.f('ix_medical_history_entries_patient_id'), 'medical_history_entries', ['patient_id'], unique=False)
    op.create_index(op.f('ix_medical_history_entries_record_id'), 'medical_history_entries', ['record_id'], unique=False)
    op.create_index(op.f('ix_medical_history_entries_recorded_by'), 'medical_history_entries', ['recorded_by'], unique=False)
    op.create_index(op.f('ix_medical_history_entries_entry_type'), 'medical_history_entries', ['entry_type'], unique=False)
    op.create_index(op.f('ix_medical_history_entries_created_at'), 'medical_history_entries', ['created_at'], unique=False)
    op.create_index('idx_history_patient_type', 'medical_history_entries', ['patient_id', 'entry_type'], unique=False)
    op.create_index('idx_history_patient_sensitive', 'medical_history_entries', ['patient_id', 'is_sensitive'], unique=False)

    # 3. data_access_logs (KDPA read-access ledger; append-only enforced by d4f2e8b03c11)
    op.create_table(
        'data_access_logs',
        sa.Column('log_id', sa.Integer(), nullable=False),
        sa.Column('accessed_by', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('access_reason', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['accessed_by'], ['users.user_id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.patient_id']),
        sa.PrimaryKeyConstraint('log_id'),
    )
    op.create_index(op.f('ix_data_access_logs_accessed_by'), 'data_access_logs', ['accessed_by'], unique=False)
    op.create_index(op.f('ix_data_access_logs_patient_id'), 'data_access_logs', ['patient_id'], unique=False)
    op.create_index(op.f('ix_data_access_logs_accessed_at'), 'data_access_logs', ['accessed_at'], unique=False)
    op.create_index('idx_access_log_patient', 'data_access_logs', ['patient_id', 'accessed_at'], unique=False)

    # 4. Drop legacy drug_inventory (no model references it)
    op.execute("DROP TABLE IF EXISTS drug_inventory CASCADE;")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_access_log_patient', table_name='data_access_logs')
    op.drop_index(op.f('ix_data_access_logs_accessed_at'), table_name='data_access_logs')
    op.drop_index(op.f('ix_data_access_logs_patient_id'), table_name='data_access_logs')
    op.drop_index(op.f('ix_data_access_logs_accessed_by'), table_name='data_access_logs')
    op.drop_table('data_access_logs')

    op.drop_index('idx_history_patient_sensitive', table_name='medical_history_entries')
    op.drop_index('idx_history_patient_type', table_name='medical_history_entries')
    op.drop_index(op.f('ix_medical_history_entries_created_at'), table_name='medical_history_entries')
    op.drop_index(op.f('ix_medical_history_entries_entry_type'), table_name='medical_history_entries')
    op.drop_index(op.f('ix_medical_history_entries_recorded_by'), table_name='medical_history_entries')
    op.drop_index(op.f('ix_medical_history_entries_record_id'), table_name='medical_history_entries')
    op.drop_index(op.f('ix_medical_history_entries_patient_id'), table_name='medical_history_entries')
    op.drop_table('medical_history_entries')

    op.drop_index('idx_consent_patient_type', table_name='consent_records')
    op.drop_index(op.f('ix_consent_records_consented_at'), table_name='consent_records')
    op.drop_index(op.f('ix_consent_records_patient_id'), table_name='consent_records')
    op.drop_table('consent_records')

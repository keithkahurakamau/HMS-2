"""add_radiology_tables

Revision ID: 9ce4ed8c39f3
Revises: 9302d7caa6cd
Create Date: 2026-05-06 12:15:26.189294

NOTE: A previous version of this migration was the result of a botched
autogenerate run — it tried to re-create the M-Pesa tables (already created
by 9302d7caa6cd) and dropped tenant-registry tables that don't belong in
tenant databases. It also failed to actually add the radiology tables that
the filename promises. This file rewrites the migration to do what it says
on the tin: add the two radiology tables and nothing else.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ce4ed8c39f3'
down_revision: Union[str, Sequence[str], None] = '9302d7caa6cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add radiology_requests and radiology_results."""
    op.create_table(
        'radiology_requests',
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=False),
        sa.Column('exam_type', sa.String(length=100), nullable=False),
        sa.Column('clinical_notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True, server_default='Pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.patient_id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('request_id'),
    )
    op.create_index(op.f('ix_radiology_requests_request_id'), 'radiology_requests', ['request_id'], unique=False)

    op.create_table(
        'radiology_results',
        sa.Column('result_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('performed_by', sa.Integer(), nullable=False),
        sa.Column('findings', sa.Text(), nullable=False),
        sa.Column('conclusion', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['radiology_requests.request_id']),
        sa.ForeignKeyConstraint(['performed_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('result_id'),
        sa.UniqueConstraint('request_id'),
    )
    op.create_index(op.f('ix_radiology_results_result_id'), 'radiology_results', ['result_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema — drop radiology tables."""
    op.drop_index(op.f('ix_radiology_results_result_id'), table_name='radiology_results')
    op.drop_table('radiology_results')
    op.drop_index(op.f('ix_radiology_requests_request_id'), table_name='radiology_requests')
    op.drop_table('radiology_requests')

"""Add messaging tables and admin-managed departments

Revision ID: f7a9c2d1e480
Revises: e5b91d2c4f33
Create Date: 2026-05-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a9c2d1e480'
down_revision: Union[str, Sequence[str], None] = 'e5b91d2c4f33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- departments -------------------------------------------------
    op.create_table(
        "departments",
        sa.Column("department_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )
    op.create_index("ix_departments_name", "departments", ["name"])

    op.create_table(
        "department_members",
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.department_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- conversations ----------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.department_id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("department_id", name="uq_conversations_department_id"),
    )
    op.create_index("ix_conversations_kind", "conversations", ["kind"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    op.create_table(
        "conversation_participants",
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conv_participants_user", "conversation_participants", ["user_id"])

    # --- messages ----------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("message_id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_conv_created", "messages", ["conversation_id", "created_at"])

    # --- seed messaging permissions ---------------------------------
    # Idempotent: only insert if not already present so re-runs are safe.
    op.execute(
        """
        INSERT INTO permissions (codename, description)
        SELECT v.codename, v.description
        FROM (VALUES
            ('messaging:read',     'Read internal staff messages'),
            ('messaging:write',    'Send internal staff messages'),
            ('departments:manage', 'Create and manage departments'),
            ('roles:manage',       'Create and manage custom roles')
        ) AS v(codename, description)
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions p WHERE p.codename = v.codename
        );
        """
    )

    # Grant baseline messaging perms to every existing role so all staff can chat.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE p.codename IN ('messaging:read', 'messaging:write')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )

    # Grant department/role management to Admin only.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'Admin'
          AND p.codename IN ('departments:manage', 'roles:manage')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    # Remove granted permissions, then the permission rows themselves.
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT permission_id FROM permissions
            WHERE codename IN ('messaging:read', 'messaging:write', 'departments:manage', 'roles:manage')
        );
        """
    )
    op.execute(
        """
        DELETE FROM permissions
        WHERE codename IN ('messaging:read', 'messaging:write', 'departments:manage', 'roles:manage');
        """
    )

    op.drop_index("ix_messages_conv_created", table_name="messages")
    op.drop_index("ix_messages_sender_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conv_participants_user", table_name="conversation_participants")
    op.drop_table("conversation_participants")

    op.drop_index("ix_conversations_last_message_at", table_name="conversations")
    op.drop_index("ix_conversations_kind", table_name="conversations")
    op.drop_table("conversations")

    op.drop_table("department_members")
    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_table("departments")

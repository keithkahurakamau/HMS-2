"""Hospital settings — per-tenant key/value configuration store

Revision ID: b27f4e91d563
Revises: a91c3d27e845
Create Date: 2026-05-12 15:00:00.000000

Adds:
- hospital_settings table (category, key, value, data_type…)
- settings:read / settings:manage permissions, granted to Admin role
- seeds a baseline set of default rows (branding, lab, radiology, billing,
  notifications, working_hours) so the Settings page is immediately useful
  out of the box.

Idempotent — re-runs are safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b27f4e91d563"
down_revision: Union[str, Sequence[str], None] = "a91c3d27e845"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_SETTINGS = [
    # category, key, label, description, data_type, value, is_sensitive, sort_order
    ("branding", "hospital_name", "Hospital name", "Displayed on every print-out and dashboard.", "string", "", False, 1),
    ("branding", "tagline", "Tagline", "Short subtitle below the hospital name on letterheads.", "string", "", False, 2),
    ("branding", "primary_color", "Primary brand color", "Hex code used for UI accents.", "string", "#2563eb", False, 3),
    ("branding", "logo_url", "Logo URL", "Public URL of the hospital logo (PNG/SVG).", "string", "", False, 4),

    ("working_hours", "weekday_open", "Weekday opening", "Front-desk opens (24-hour, HH:MM).", "string", "08:00", False, 1),
    ("working_hours", "weekday_close", "Weekday closing", "Front-desk closes (24-hour, HH:MM).", "string", "17:00", False, 2),
    ("working_hours", "saturday_open", "Saturday opening", "", "string", "09:00", False, 3),
    ("working_hours", "saturday_close", "Saturday closing", "", "string", "13:00", False, 4),
    ("working_hours", "sunday_open", "Sunday opening", "Leave blank if closed.", "string", "", False, 5),
    ("working_hours", "sunday_close", "Sunday closing", "Leave blank if closed.", "string", "", False, 6),
    ("working_hours", "appointment_slot_minutes", "Appointment slot (min)", "", "number", "30", False, 7),

    ("billing", "currency", "Currency code", "ISO 4217 (KES, USD…).", "string", "KES", False, 1),
    ("billing", "tax_rate_pct", "VAT / tax rate (%)", "Applied on taxable invoices.", "number", "16", False, 2),
    ("billing", "invoice_prefix", "Invoice prefix", "Goes on every printed invoice number.", "string", "INV-", False, 3),
    ("billing", "lock_pricing_on_order", "Lock pricing on order", "Once a lab/imaging order is placed, the price won't change.", "boolean", "true", False, 4),

    ("laboratory", "default_turnaround_hours", "Default turnaround (h)", "Used when a catalog entry doesn't specify its own.", "number", "24", False, 1),
    ("laboratory", "barcode_default", "Barcode by default", "Default value for the catalog 'Requires barcode' checkbox.", "boolean", "false", False, 2),
    ("laboratory", "critical_value_notify", "Notify critical values", "Auto-DM the ordering doctor for out-of-range flags.", "boolean", "true", False, 3),

    ("radiology", "default_modality", "Default modality", "Pre-selects this modality in new exam dialogs.", "string", "X-Ray", False, 1),
    ("radiology", "report_signing_required", "Require radiologist sign-off", "", "boolean", "true", False, 2),

    ("notifications", "email_from", "Outbound email From:", "RFC-5321 address used by transactional mail.", "string", "no-reply@hospital.local", False, 1),
    ("notifications", "sms_sender_id", "SMS sender ID", "Letterhead the SMS gateway shows on the patient's phone.", "string", "HMS", False, 2),
    ("notifications", "remind_before_hours", "Appointment reminder (h)", "Hours before the appointment to send a reminder.", "number", "24", False, 3),

    ("privacy", "kdpa_dpo_email", "Data protection officer email", "Used in subject access response letters.", "string", "", False, 1),
    ("privacy", "breach_notify_minutes", "Breach window (minutes)", "KDPA Section 43 default is 72 hours = 4320.", "number", "4320", False, 2),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "hospital_settings" not in inspector.get_table_names():
        op.create_table(
            "hospital_settings",
            sa.Column("setting_id", sa.Integer(), primary_key=True),
            sa.Column("category", sa.String(length=60), nullable=False),
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("label", sa.String(length=200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("data_type", sa.String(length=20), nullable=False, server_default="string"),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.UniqueConstraint("category", "key", name="uq_hospital_settings_category_key"),
        )
        op.create_index("ix_hospital_settings_category", "hospital_settings", ["category"])
        op.create_index("ix_hospital_settings_key", "hospital_settings", ["key"])

    for (category, key, label, description, data_type, value, is_sensitive, sort_order) in DEFAULT_SETTINGS:
        op.execute(
            sa.text(
                """
                INSERT INTO hospital_settings (category, key, label, description, data_type, value, is_sensitive, sort_order)
                SELECT :category, :key, :label, :description, :data_type, :value, :is_sensitive, :sort_order
                WHERE NOT EXISTS (
                    SELECT 1 FROM hospital_settings WHERE category = :category AND key = :key
                )
                """
            ).bindparams(
                category=category, key=key, label=label, description=description,
                data_type=data_type, value=value, is_sensitive=is_sensitive,
                sort_order=sort_order,
            )
        )

    for codename, description in [
        ("settings:read", "View hospital settings"),
        ("settings:manage", "Edit hospital settings"),
    ]:
        op.execute(
            sa.text(
                "INSERT INTO permissions (codename, description) "
                "SELECT :c, :d WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :c)"
            ).bindparams(c=codename, d=description)
        )

    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename IN ('settings:read', 'settings:manage')
          AND r.name IN ('Admin')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )
    # Every role gets read so the settings can drive UX, but only Admin can write.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'settings:read'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename IN ('settings:read', 'settings:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('settings:read', 'settings:manage');")
    op.execute("DROP INDEX IF EXISTS ix_hospital_settings_key;")
    op.execute("DROP INDEX IF EXISTS ix_hospital_settings_category;")
    op.execute("DROP TABLE IF EXISTS hospital_settings;")

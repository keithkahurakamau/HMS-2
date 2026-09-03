"""mpesa_events: the Daraja event log

Revision ID: a2f7c9e4d658
Revises: f0a1b2c3d4e5
Create Date: 2026-09-03 00:00:00.000000

A brand new table, tenant database (same rule as mpesa_configs /
mpesa_transactions / mpesa_refunds, the opposite of platform_mpesa_*): one
row per Daraja interaction, whatever its outcome, so a cashier can answer
"what happened to this payment" without an engineer reading application
logs. See app/models/mpesa_events.py and
app/services/daraja/events.py for the shape and the redaction that makes it
safe to show hospital staff in a browser.

Idempotent, like its neighbours in this package: CREATE TABLE / CREATE
INDEX IF NOT EXISTS throughout, so re-running on an already-migrated
tenant is a no-op.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a2f7c9e4d658"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mpesa_events (
            id                    SERIAL PRIMARY KEY,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            flow                  VARCHAR(40) NOT NULL,
            direction             VARCHAR(10) NOT NULL,
            outcome               VARCHAR(20) NOT NULL,
            http_status           INTEGER,
            daraja_result_code    VARCHAR(20),
            daraja_result_desc    VARCHAR(255),
            duration_ms           INTEGER,
            error_detail          TEXT,
            mpesa_transaction_id  INTEGER,
            mpesa_refund_id       INTEGER,
            mpesa_config_id       INTEGER,
            checkout_request_id   VARCHAR(100),
            conversation_id       VARCHAR(64),
            receipt_number        VARCHAR(50),
            request_payload       TEXT,
            response_payload      TEXT
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mpesa_events_created_at ON mpesa_events (created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mpesa_events_flow ON mpesa_events (flow);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mpesa_events_outcome ON mpesa_events (outcome);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_mpesa_transaction_id "
        "ON mpesa_events (mpesa_transaction_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_mpesa_refund_id "
        "ON mpesa_events (mpesa_refund_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_mpesa_config_id "
        "ON mpesa_events (mpesa_config_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_checkout_request_id "
        "ON mpesa_events (checkout_request_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_conversation_id "
        "ON mpesa_events (conversation_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_events_receipt_number "
        "ON mpesa_events (receipt_number);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mpesa_events;")

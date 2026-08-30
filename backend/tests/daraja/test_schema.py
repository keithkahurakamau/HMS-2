from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.config.database import Base


def test_tables_registered_in_metadata():
    names = set(Base.metadata.tables)
    assert {"mpesa_configs", "mpesa_transactions", "mpesa_refunds"} <= names


def test_receipt_number_is_unique():
    """The replay defence. A repeated callback must not double-credit."""
    assert MpesaTransaction.__table__.c.receipt_number.unique is True


def test_originator_conversation_id_is_unique():
    """The double-refund defence."""
    assert MpesaRefund.__table__.c.originator_conversation_id.unique is True


def test_callback_token_is_unique():
    assert MpesaConfig.__table__.c.callback_token.unique is True


def test_no_plaintext_secret_columns():
    """Every credential column must carry the _encrypted suffix."""
    suspicious = {"consumer_key", "consumer_secret", "passkey", "initiator_password"}
    assert suspicious.isdisjoint(set(MpesaConfig.__table__.c.keys()))

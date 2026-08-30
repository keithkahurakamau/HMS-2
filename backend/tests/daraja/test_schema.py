from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.config.database import Base
from app.utils.encryption import decrypt_data
from app.services.daraja.tokens import (
    mint_callback_token,
    store_callback_token,
    token_lookup_hash,
)


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
    assert MpesaConfig.__table__.c.callback_token_lookup.unique is True


def test_no_plaintext_secret_columns():
    """Every credential column must carry the _encrypted suffix."""
    suspicious = {
        "consumer_key", "consumer_secret", "passkey", "initiator_password",
        "callback_token",
    }
    assert suspicious.isdisjoint(set(MpesaConfig.__table__.c.keys()))


def test_token_lookup_hash_is_deterministic_and_not_plaintext():
    token = mint_callback_token()
    first = token_lookup_hash(token)
    second = token_lookup_hash(token)
    assert first == second
    assert first != token


class _StubConfig:
    """Plain stand-in for MpesaConfig with just the two token attributes.

    Instantiating the real MpesaConfig here would force SQLAlchemy to
    configure every mapper in the app's declarative registry (including
    relationships on unrelated models this isolated test suite never loads),
    which is unrelated to what this test is checking: that
    store_callback_token sets its two attributes consistently on whatever
    object it is given.
    """

    callback_token_encrypted = None
    callback_token_lookup = None


def test_store_callback_token_sets_both_columns_consistently():
    config = _StubConfig()
    token = mint_callback_token()
    store_callback_token(config, token)

    assert config.callback_token_encrypted is not None
    assert config.callback_token_lookup is not None
    assert config.callback_token_lookup == token_lookup_hash(token)
    assert config.callback_token_encrypted != token
    assert decrypt_data(config.callback_token_encrypted) == token

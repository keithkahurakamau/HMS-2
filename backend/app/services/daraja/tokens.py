"""Callback token minting, hashing and storage for MpesaConfig.

Daraja does not sign callbacks, so the unguessable token in the callback URL
path is one of the three things standing between us and a forged payment.
It has to satisfy two opposite needs at once:

  - An outbound STK push builds its own CallBackURL at request time, so we
    need the plaintext token BACK. That rules out a one-way hash: hashing is
    the standard API-key pattern, but it only lets us recognise a token we
    are handed, not reconstruct one to put in a URL.
  - An inbound callback has to be resolved to a tenant by an indexed equality
    lookup. That rules out storing only Fernet ciphertext: Fernet is
    non-deterministic, so encrypting the same token twice gives different
    ciphertext, and an encrypted column cannot back an equality lookup.

So the token is held in two columns: an encrypted, reversible form for
outbound use, and a deterministic keyed-hash form for inbound lookup. This
module is the only place that should write either column, because the two
must always be set together. A config with a lookup hash but no recoverable
token cannot send an STK push; a config with a token but no lookup hash
cannot receive its callbacks. Neither failure is acceptable and neither is
loud, so `store_callback_token` is the single seam that keeps them in sync.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from typing import Union

from app.config.settings import settings
from app.models.mpesa import MpesaConfig
from app.models.platform_mpesa import PlatformMpesaConfig
from app.utils.encryption import encrypt_data


def mint_callback_token() -> str:
    """Generate a fresh, high-entropy callback token."""
    return secrets.token_urlsafe(32)


def token_lookup_hash(token: str) -> str:
    """Deterministic HMAC-SHA256 hex digest of a callback token.

    Keyed on the application's existing SECRET_KEY (via settings.jwt_secret)
    rather than a new environment variable: SECRET_KEY is already a required,
    validated secret on every deployment, and ENCRYPTION_KEY is already
    spoken for as the Fernet key that encrypts callback_token_encrypted. A
    keyed hash (HMAC) is used rather than a bare hash so the lookup value
    cannot be reproduced by anyone who only knows the token format, without
    also knowing the application secret.
    """
    if not token:
        raise ValueError("token is required")
    key = settings.jwt_secret.encode("utf-8")
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()


def store_callback_token(config: Union[MpesaConfig, PlatformMpesaConfig], token: str) -> None:
    """Set both callback token columns on config, consistently, and stamp
    callback_token_rotated_at.

    Widened to accept PlatformMpesaConfig as well as MpesaConfig: the
    platform's own subscription-billing rail (app/models/platform_mpesa.py)
    reuses this exact function to keep its callback token pair in sync,
    the same way MpesaConfig does. The body only ever sets attributes that
    both models carry (callback_token_encrypted, callback_token_lookup,
    callback_token_rotated_at), so nothing here actually changes; only the
    type hint was wrong before.

    This is the only supported way to write either column: setting one
    without the other leaves the config unable to either send an STK push
    (missing the encrypted, recoverable token) or receive its callbacks
    (missing the lookup hash), and both failures are silent until a payment
    actually happens.

    The timestamp is what lets an operator answer "which token is live"
    without ever seeing the token itself: a rotated_at that is newer than
    when a URL was registered with Safaricom means that URL is dead,
    without exposing any part of the value that changed. Stamped on every
    call, including the first-ever mint, since a config's token really did
    just change, from nothing to something.
    """
    if not token:
        raise ValueError("token is required")
    config.callback_token_encrypted = encrypt_data(token)
    config.callback_token_lookup = token_lookup_hash(token)
    config.callback_token_rotated_at = datetime.now(timezone.utc)

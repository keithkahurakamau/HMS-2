import base64
from datetime import datetime

import pytest

from app.services.daraja.credentials import (
    _CERT_DIR,
    daraja_timestamp,
    normalize_msisdn,
    security_credential,
    stk_password,
)

# BLOCKED (Task 1, Step 3): the authentic Safaricom sandbox/production .cer
# files could not be obtained. The Daraja developer portal now requires a
# logged-in session to reach the certificate download, and the only
# certificates reachable from the public safaricom GitHub org (and its
# community mirrors) are historical and expired (sandbox: expired 2016,
# production: expired 2018), so they are not trustworthy stand-ins for the
# key Safaricom currently uses to decrypt SecurityCredential. Rather than
# commit a certificate that could be silently wrong, these two tests are
# skipped until backend/app/vendor/safaricom/sandbox.cer is added for real.
_missing_sandbox_cert = not (_CERT_DIR / "sandbox.cer").exists()
_no_sandbox_cert_reason = (
    "backend/app/vendor/safaricom/sandbox.cer is missing: the authentic "
    "Safaricom certificate could not be sourced (see Task 1 report)"
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0712345678", "254712345678"),
        ("+254712345678", "254712345678"),
        ("254712345678", "254712345678"),
        (" 0712 345 678 ", "254712345678"),
        ("712345678", "254712345678"),
    ],
)
def test_normalize_msisdn(raw, expected):
    assert normalize_msisdn(raw) == expected


@pytest.mark.parametrize("bad", ["", None, "abc", "07123", "0712345678901234"])
def test_normalize_msisdn_rejects_garbage(bad):
    with pytest.raises(ValueError):
        normalize_msisdn(bad)


def test_daraja_timestamp_shape():
    ts = daraja_timestamp(datetime(2026, 8, 29, 14, 5, 3))
    assert ts == "20260829140503"


def test_stk_password_is_base64_of_concatenation():
    ts = "20260829140503"
    pw = stk_password("174379", "PASSKEY", ts)
    assert base64.b64decode(pw).decode() == "174379" + "PASSKEY" + ts


@pytest.mark.skipif(_missing_sandbox_cert, reason=_no_sandbox_cert_reason)
def test_security_credential_is_not_the_plaintext():
    cred = security_credential("initiator-pw", "sandbox")
    assert cred and "initiator-pw" not in cred
    # RSA output is base64 and materially longer than the input.
    assert len(base64.b64decode(cred)) >= 128


@pytest.mark.skipif(_missing_sandbox_cert, reason=_no_sandbox_cert_reason)
def test_security_credential_rejects_unknown_environment():
    with pytest.raises(ValueError):
        security_credential("x", "staging")

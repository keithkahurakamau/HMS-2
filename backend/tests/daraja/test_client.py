import time
from types import SimpleNamespace

import pytest

from app.services.daraja.client import DarajaClient, DarajaError, _TOKEN_CACHE


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_cache():
    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


def _config(**over):
    base = dict(
        consumer_key="ck",
        consumer_secret="cs",
        environment="sandbox",
        shortcode="174379",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_token_is_fetched_once_and_reused(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_get)
    client = DarajaClient(_config())
    assert client.access_token() == "tok"
    assert client.access_token() == "tok"
    assert len(calls) == 1


def test_expired_token_is_refetched(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok2", "expires_in": "3599"}),
    )
    _TOKEN_CACHE["ck"] = ("stale", time.monotonic() - 1)
    client = DarajaClient(_config())
    assert client.access_token() == "tok2"


def test_token_cache_is_keyed_by_consumer_key(monkeypatch):
    """Two tenants must never share a token. This is the isolation guarantee."""
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok-b", "expires_in": "3599"}),
    )
    _TOKEN_CACHE["ck"] = ("tok-a", time.monotonic() + 3000)
    other = DarajaClient(_config(consumer_key="ck-other"))
    assert other.access_token() == "tok-b"
    assert _TOKEN_CACHE["ck"][0] == "tok-a"


def test_post_raises_daraja_error_on_4xx(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )
    monkeypatch.setattr(
        "app.services.daraja.client.requests.post",
        lambda url, **kw: FakeResponse(400, {"errorMessage": "Bad Request"}),
    )
    client = DarajaClient(_config())
    with pytest.raises(DarajaError) as exc:
        client.post("/mpesa/stkpush/v1/processrequest", {})
    assert exc.value.status_code == 400
    assert "Bad Request" in str(exc.value)


def test_401_refreshes_the_token_once_then_retries(monkeypatch):
    tokens = iter(["stale-tok", "fresh-tok"])
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": next(tokens), "expires_in": "3599"}),
    )
    seen = []

    def fake_post(url, **kw):
        seen.append(kw["headers"]["Authorization"])
        return FakeResponse(401 if len(seen) == 1 else 200, {"ok": True})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)
    client = DarajaClient(_config())
    assert client.post("/x", {}) == {"ok": True}
    assert seen == ["Bearer stale-tok", "Bearer fresh-tok"]

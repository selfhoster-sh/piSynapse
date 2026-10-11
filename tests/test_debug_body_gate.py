"""Week-1 pack, item: /debug beacon body read must be size-gated (2026-10-11).

The beacon key (_k) is extracted from the JSON body in security_middleware
BEFORE the body-size limit further down and BEFORE authentication. The old
code called `await request.body()` unconditionally: an unauthenticated
caller could make the server buffer an attacker-sized payload into memory
before being rejected with 401. `_debug_beacon_key` now gates the read on
Content-Length (real beacons are tiny and always carry it); chunked or
oversized requests are answered as keyless without reading the body.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main as mainmod


class _FakeRequest:
    """Minimal Request double: headers + a body() spy."""

    def __init__(self, headers, body=b""):
        self.headers = headers
        self._body = body
        self.body_read_count = 0

    async def body(self):
        self.body_read_count += 1
        return self._body


def test_header_key_short_circuits_body_read():
    req = _FakeRequest({"x-api-key": "k1"})
    assert asyncio.run(mainmod._debug_beacon_key(req)) == "k1"
    assert req.body_read_count == 0


def test_small_body_key_extracted():
    req = _FakeRequest(
        {"content-length": "25"}, body=b'{"_k": "beacon-key", "x": 1}'
    )
    assert asyncio.run(mainmod._debug_beacon_key(req)) == "beacon-key"
    assert req.body_read_count == 1


def test_legacy_k_field_still_supported():
    req = _FakeRequest({"content-length": "14"}, body=b'{"k": "legacy"}')
    assert asyncio.run(mainmod._debug_beacon_key(req)) == "legacy"


def test_oversized_content_length_never_reads_body():
    req = _FakeRequest({"content-length": str(mainmod._DEBUG_MAX_BODY_BYTES + 1)})
    assert asyncio.run(mainmod._debug_beacon_key(req)) == ""
    assert req.body_read_count == 0  # the memory-exhaustion guard


def test_missing_content_length_never_reads_body():
    # Chunked transfer encoding carries no Content-Length.
    req = _FakeRequest({})
    assert asyncio.run(mainmod._debug_beacon_key(req)) == ""
    assert req.body_read_count == 0


def test_non_digit_content_length_never_reads_body():
    req = _FakeRequest({"content-length": "not-a-number"})
    assert asyncio.run(mainmod._debug_beacon_key(req)) == ""
    assert req.body_read_count == 0


def test_malformed_json_swallowed_keyless():
    req = _FakeRequest({"content-length": "10"}, body=b"not json")
    assert asyncio.run(mainmod._debug_beacon_key(req)) == ""


def test_non_string_key_rejected():
    req = _FakeRequest({"content-length": "10"}, body=b'{"_k": 123}')
    assert asyncio.run(mainmod._debug_beacon_key(req)) == ""


# ── Middleware-level: the 401/413 contract survives the gate ─────────────────

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.middleware("http")(mainmod.trusted_host_middleware)
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/debug")
    async def debug():
        return {"ok": True}

    monkeypatch.setattr(mainmod, "API_KEY", "secret-key")
    monkeypatch.setenv("API_KEY", "secret-key")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", set())
    return TestClient(app, base_url="http://localhost")


def test_debug_oversized_beacon_without_key_is_401(client):
    # Pre-gate behavior preserved: keyless oversized beacons answer 401 —
    # but now WITHOUT buffering the body first.
    r = client.post(
        "/debug",
        content=b'{"_k": "wrong"}',
        headers={"content-length": str(mainmod._DEBUG_MAX_BODY_BYTES + 1)},
    )
    assert r.status_code == 401


def test_debug_valid_header_key_with_oversized_body_is_413(client):
    # Authenticated via header, but the payload itself violates the 8 KB
    # beacon cap → the later body-size gate still fires.
    r = client.post(
        "/debug",
        content=b"x" * (mainmod._DEBUG_MAX_BODY_BYTES + 1),
        headers={
            "x-api-key": "secret-key",
            "content-length": str(mainmod._DEBUG_MAX_BODY_BYTES + 1),
        },
    )
    assert r.status_code == 413


def test_debug_valid_beacon_key_in_body_passes(client):
    r = client.post("/debug", json={"_k": "secret-key", "event": "test"})
    assert r.status_code == 200

from pathlib import Path

import pytest

from koschei.universe_remote_app_v1 import (
    UniverseRemoteAppError,
    _key_hex,
    _port,
    _ttl,
    build_envelope_provider_v1,
)


def test_port_uses_railway_port_and_rejects_invalid(monkeypatch):
    monkeypatch.setenv("PORT", "9123")
    assert _port() == 9123
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(UniverseRemoteAppError):
        _port()


def test_ttl_is_bounded(monkeypatch):
    monkeypatch.setenv("KOSCHEI_UNIVERSE_TTL_SECONDS", "60")
    assert _ttl() == 60
    monkeypatch.setenv("KOSCHEI_UNIVERSE_TTL_SECONDS", "301")
    with pytest.raises(UniverseRemoteAppError):
        _ttl()


def test_observer_keys_require_256_bits_of_hex(monkeypatch):
    monkeypatch.setenv("K", "ab" * 32)
    assert _key_hex("K") == bytes.fromhex("ab" * 32)
    monkeypatch.setenv("K", "ab" * 31)
    with pytest.raises(UniverseRemoteAppError):
        _key_hex("K")
    monkeypatch.setenv("K", "not-hex")
    with pytest.raises(UniverseRemoteAppError):
        _key_hex("K")


def test_real_project_provider_issues_authority_free_envelope(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    source = root / "examples" / "hello.ks"
    monkeypatch.setenv("KOSCHEI_UNIVERSE_PROJECT", str(source))
    monkeypatch.setenv("KOSCHEI_UNIVERSE_OBSERVER_SIGNING_KEY_HEX", "11" * 32)
    monkeypatch.setenv("KOSCHEI_UNIVERSE_TTL_SECONDS", "30")
    provider, key = build_envelope_provider_v1()
    envelope = provider()
    assert key == bytes.fromhex("11" * 32)
    assert envelope.authority is False
    assert envelope.payload["authority"] is False
    assert envelope.payload["nodes"]
    assert envelope.expires_at_unix - envelope.issued_at_unix == 30

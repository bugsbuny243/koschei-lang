"""Koschei Universe production remote observer app v2."""
from __future__ import annotations

import os
from pathlib import Path
import time

from .universe_project_provider_v1 import build_project_universe_v1
from .universe_remote_gateway_v4 import serve_remote_observer_v4
from .universe_remote_observer_v1 import issue_remote_observer_v1
from .universe_web_v1 import universe_payload_v1


class UniverseRemoteAppError(ValueError):
    pass


def _env_required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise UniverseRemoteAppError(f"missing required environment variable: {name}")
    return value


def _key_hex(name: str, *, exact: int | None = None) -> bytes:
    raw = _env_required(name)
    try:
        value = bytes.fromhex(raw)
    except ValueError as exc:
        raise UniverseRemoteAppError(f"{name} must be hexadecimal") from exc
    if exact is not None and len(value) != exact:
        raise UniverseRemoteAppError(f"{name} must contain exactly {exact * 8} bits")
    if exact is None and len(value) < 32:
        raise UniverseRemoteAppError(f"{name} must contain at least 256 bits")
    return value


def _int_env(name: str, default: str, low: int, high: int) -> int:
    raw = os.environ.get(name, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise UniverseRemoteAppError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise UniverseRemoteAppError(f"{name} must be {low}..{high}")
    return value


def _port() -> int:
    """Return the bounded Railway/public listener port."""

    return _int_env("PORT", "8876", 1, 65535)


def _ttl() -> int:
    """Return the bounded remote-observer envelope lifetime."""

    return _int_env("KOSCHEI_UNIVERSE_TTL_SECONDS", "60", 5, 300)


def build_envelope_provider_v1():
    project_path = Path(_env_required("KOSCHEI_UNIVERSE_PROJECT")).resolve()
    signing_key = _key_hex("KOSCHEI_UNIVERSE_OBSERVER_SIGNING_KEY_HEX")
    ttl = _ttl()
    if not project_path.is_file() or project_path.suffix != ".ks":
        raise UniverseRemoteAppError("KOSCHEI_UNIVERSE_PROJECT must point to an existing .ks file")

    def provider():
        project = build_project_universe_v1(project_path)
        payload = universe_payload_v1(projection=project.projection, live=project.live)
        return issue_remote_observer_v1(
            payload=payload,
            signing_key=signing_key,
            issued_at_unix=int(time.time()),
            ttl_seconds=ttl,
        )
    return provider, signing_key


def main() -> int:
    provider, signing_key = build_envelope_provider_v1()
    serve_remote_observer_v4(
        provider,
        login_hash=_key_hex("KOSCHEI_UNIVERSE_LOGIN_SHA256_HEX", exact=32),
        session_key=_key_hex("KOSCHEI_UNIVERSE_SESSION_KEY_HEX"),
        signing_key=signing_key,
        host=os.environ.get("KOSCHEI_UNIVERSE_HOST", "0.0.0.0"),
        port=_port(),
        session_ttl_seconds=_int_env("KOSCHEI_UNIVERSE_SESSION_TTL_SECONDS", "1800", 60, 86400),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Koschei Universe production remote observer app v1.

Railway/container entrypoint for the read-only mobile Universe. It binds a real
checked Koschei project projection to short-lived signed observer envelopes.
Secrets stay server-side and the browser remains authority-free.
"""
from __future__ import annotations

import os
from pathlib import Path
import time

from .universe_project_provider_v1 import build_project_universe_v1
from .universe_remote_gateway_v3 import serve_remote_observer_v3
from .universe_remote_observer_v1 import issue_remote_observer_v1
from .universe_web_v1 import universe_payload_v1


class UniverseRemoteAppError(ValueError):
    pass


def _env_required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise UniverseRemoteAppError(f"missing required environment variable: {name}")
    return value


def _key_hex(name: str) -> bytes:
    raw = _env_required(name)
    try:
        value = bytes.fromhex(raw)
    except ValueError as exc:
        raise UniverseRemoteAppError(f"{name} must be hexadecimal") from exc
    if len(value) < 32:
        raise UniverseRemoteAppError(f"{name} must contain at least 256 bits")
    return value


def _port() -> int:
    raw = os.environ.get("PORT", "8876")
    try:
        port = int(raw)
    except ValueError as exc:
        raise UniverseRemoteAppError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise UniverseRemoteAppError("PORT out of range")
    return port


def _ttl() -> int:
    raw = os.environ.get("KOSCHEI_UNIVERSE_TTL_SECONDS", "60")
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise UniverseRemoteAppError("KOSCHEI_UNIVERSE_TTL_SECONDS must be an integer") from exc
    if not 5 <= ttl <= 300:
        raise UniverseRemoteAppError("KOSCHEI_UNIVERSE_TTL_SECONDS must be 5..300")
    return ttl


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
    bearer = _key_hex("KOSCHEI_UNIVERSE_BEARER_TOKEN_HEX")
    host = os.environ.get("KOSCHEI_UNIVERSE_HOST", "0.0.0.0")
    serve_remote_observer_v3(
        provider,
        bearer_token=bearer.hex().encode("ascii"),
        signing_key=signing_key,
        host=host,
        port=_port(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

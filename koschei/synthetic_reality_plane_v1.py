"""Koschei Synthetic Reality Plane v1.

Creates a closed config/telemetry/log/incident reality on top of a validated
Living Synthetic System. It consumes only synthetic identities and an independent
reality key. No canonical source/path/hash/config reader or reverse resolver exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from koschei.living_synthetic_system_v1 import (
    LivingSyntheticSystem,
    validate_living_synthetic_system,
)
from koschei.no_return_shadow_graph_v1 import ShadowGraph


class SyntheticRealityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SyntheticConfig:
    config_id: str
    service_id: str
    package_id: str
    mode_token: str


@dataclass(frozen=True, slots=True)
class SyntheticTelemetry:
    metric_id: str
    service_id: str
    trace_step: int
    value: int


@dataclass(frozen=True, slots=True)
class SyntheticLog:
    log_id: str
    service_id: str
    trace_step: int
    event_token: str


@dataclass(frozen=True, slots=True)
class SyntheticIncident:
    incident_id: str
    service_id: str
    log_id: str
    severity: int


@dataclass(frozen=True, slots=True)
class SyntheticRealityPlane:
    universe_id: str
    epoch: int
    configs: tuple[SyntheticConfig, ...]
    telemetry: tuple[SyntheticTelemetry, ...]
    logs: tuple[SyntheticLog, ...]
    incidents: tuple[SyntheticIncident, ...]
    provenance: str
    deployable: bool
    reality_digest: str


def _require_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise SyntheticRealityError("reality_key must contain at least 256 bits")
    return key


def _tok(key: bytes, universe_id: str, epoch: int, label: str, value: str, n: int = 24) -> str:
    msg = (
        b"koschei/synthetic-reality-plane/v1\x00"
        + universe_id.encode("utf-8") + b"\x00"
        + str(epoch).encode("ascii") + b"\x00"
        + label.encode("ascii") + b"\x00"
        + value.encode("utf-8")
    )
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:n]


def build_synthetic_reality(*, system: LivingSyntheticSystem, graph: ShadowGraph,
                            reality_key: bytes) -> SyntheticRealityPlane:
    validate_living_synthetic_system(system, graph)
    key = _require_key(reality_key)
    service_ids = {s.service_id for s in system.services}
    package_ids = {p.package_id for p in system.packages}

    configs = tuple(
        SyntheticConfig(
            config_id="cfg-" + _tok(key, system.universe_id, system.epoch, "config", svc.service_id),
            service_id=svc.service_id,
            package_id=system.packages[i % len(system.packages)].package_id,
            mode_token="mode-" + _tok(key, system.universe_id, system.epoch, "mode", svc.service_id, 12),
        )
        for i, svc in enumerate(system.services)
    )

    telemetry = tuple(
        SyntheticTelemetry(
            metric_id="met-" + _tok(key, system.universe_id, system.epoch, "metric", f"{t.step}:{t.service_id}"),
            service_id=t.service_id,
            trace_step=t.step,
            value=int(_tok(key, system.universe_id, system.epoch, "value", str(t.step), 8), 16) % 10000,
        )
        for t in system.traces
    )

    logs = tuple(
        SyntheticLog(
            log_id="log-" + _tok(key, system.universe_id, system.epoch, "log", f"{t.step}:{t.event_token}"),
            service_id=t.service_id,
            trace_step=t.step,
            event_token="obs-" + _tok(key, system.universe_id, system.epoch, "observed", t.event_token),
        )
        for t in system.traces
    )

    incidents = tuple(
        SyntheticIncident(
            incident_id="inc-" + _tok(key, system.universe_id, system.epoch, "incident", log.log_id),
            service_id=log.service_id,
            log_id=log.log_id,
            severity=(int(_tok(key, system.universe_id, system.epoch, "severity", log.log_id, 4), 16) % 5) + 1,
        )
        for i, log in enumerate(logs) if i % 7 == 0
    )

    # Defensive closure check before constructing the immutable plane.
    if any(c.service_id not in service_ids or c.package_id not in package_ids for c in configs):
        raise SyntheticRealityError("config escaped synthetic namespace")
    if any(m.service_id not in service_ids for m in telemetry):
        raise SyntheticRealityError("telemetry escaped synthetic namespace")

    payload = "|".join(
        [system.universe_id, str(system.epoch)]
        + [f"{c.config_id}:{c.service_id}:{c.package_id}:{c.mode_token}" for c in configs]
        + [f"{m.metric_id}:{m.service_id}:{m.trace_step}:{m.value}" for m in telemetry]
        + [f"{l.log_id}:{l.service_id}:{l.trace_step}:{l.event_token}" for l in logs]
        + [f"{i.incident_id}:{i.service_id}:{i.log_id}:{i.severity}" for i in incidents]
    ).encode("utf-8")

    return SyntheticRealityPlane(
        universe_id=system.universe_id,
        epoch=system.epoch,
        configs=configs,
        telemetry=telemetry,
        logs=logs,
        incidents=incidents,
        provenance="synthetic-reality-plane",
        deployable=False,
        reality_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def validate_synthetic_reality(plane: SyntheticRealityPlane, system: LivingSyntheticSystem,
                               graph: ShadowGraph) -> None:
    validate_living_synthetic_system(system, graph)
    if not isinstance(plane, SyntheticRealityPlane):
        raise SyntheticRealityError("invalid synthetic reality plane")
    if plane.provenance != "synthetic-reality-plane" or plane.deployable is not False:
        raise SyntheticRealityError("synthetic reality provenance/deployability invariant failed")
    if plane.universe_id != system.universe_id or plane.epoch != system.epoch:
        raise SyntheticRealityError("synthetic reality escaped its universe")
    service_ids = {s.service_id for s in system.services}
    package_ids = {p.package_id for p in system.packages}
    log_ids = {l.log_id for l in plane.logs}
    if any(c.service_id not in service_ids or c.package_id not in package_ids for c in plane.configs):
        raise SyntheticRealityError("config escapes synthetic namespace")
    if any(m.service_id not in service_ids for m in plane.telemetry):
        raise SyntheticRealityError("telemetry escapes synthetic namespace")
    if any(l.service_id not in service_ids for l in plane.logs):
        raise SyntheticRealityError("log escapes synthetic namespace")
    for incident in plane.incidents:
        if incident.service_id not in service_ids or incident.log_id not in log_ids:
            raise SyntheticRealityError("incident escapes synthetic namespace")
        if incident.severity not in {1, 2, 3, 4, 5}:
            raise SyntheticRealityError("invalid synthetic incident severity")


def require_canonical_reality_promotion(_plane: SyntheticRealityPlane) -> None:
    raise SyntheticRealityError("synthetic reality can never enter canonical build/sign/deploy")

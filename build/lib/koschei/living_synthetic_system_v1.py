"""Koschei Living Synthetic System v1.

Builds a deterministic, non-deployable synthetic service/package/trace layer on
top of a validated No-Return Shadow Graph. All identities are derived only from
the shadow universe and an independent synthetic-system key. No canonical name,
path, hash, source reference, resolver, or promotion primitive is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from koschei.no_return_shadow_graph_v1 import ShadowGraph, validate_no_return_graph


class SyntheticSystemError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SyntheticService:
    service_id: str
    node_id: str
    endpoint_token: str


@dataclass(frozen=True, slots=True)
class SyntheticPackage:
    package_id: str
    owner_service_id: str
    dependency_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticTraceStep:
    step: int
    service_id: str
    package_id: str
    event_token: str


@dataclass(frozen=True, slots=True)
class LivingSyntheticSystem:
    universe_id: str
    epoch: int
    services: tuple[SyntheticService, ...]
    packages: tuple[SyntheticPackage, ...]
    traces: tuple[SyntheticTraceStep, ...]
    provenance: str
    deployable: bool
    system_digest: str


def _require_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise SyntheticSystemError("system_key must contain at least 256 bits")
    return key


def _tok(key: bytes, universe_id: str, epoch: int, label: str, value: str, n: int = 24) -> str:
    msg = (
        b"koschei/living-synthetic-system/v1\x00"
        + universe_id.encode("utf-8") + b"\x00"
        + str(epoch).encode("ascii") + b"\x00"
        + label.encode("ascii") + b"\x00"
        + value.encode("utf-8")
    )
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:n]


def build_living_synthetic_system(*, graph: ShadowGraph, system_key: bytes,
                                  trace_length: int = 24) -> LivingSyntheticSystem:
    validate_no_return_graph(graph)
    key = _require_key(system_key)
    if not isinstance(trace_length, int) or isinstance(trace_length, bool) or trace_length < 8 or trace_length > 4096:
        raise SyntheticSystemError("trace_length must be an integer in [8, 4096]")

    services = tuple(
        SyntheticService(
            service_id="svc-" + _tok(key, graph.universe_id, graph.epoch, "service", node.node_id),
            node_id=node.node_id,
            endpoint_token="ep-" + _tok(key, graph.universe_id, graph.epoch, "endpoint", node.node_id),
        )
        for node in graph.nodes
    )

    packages_list: list[SyntheticPackage] = []
    for i, svc in enumerate(services):
        package_id = "pkg-" + _tok(key, graph.universe_id, graph.epoch, "package", svc.service_id)
        deps = (
            "pkg-" + _tok(key, graph.universe_id, graph.epoch, "package", services[(i + 1) % len(services)].service_id),
        )
        packages_list.append(SyntheticPackage(package_id, svc.service_id, deps))
    packages = tuple(packages_list)

    traces = tuple(
        SyntheticTraceStep(
            step=i,
            service_id=services[i % len(services)].service_id,
            package_id=packages[(i * 3) % len(packages)].package_id,
            event_token="evt-" + _tok(key, graph.universe_id, graph.epoch, "trace", str(i)),
        )
        for i in range(trace_length)
    )

    payload = "|".join(
        [graph.universe_id, str(graph.epoch)]
        + [f"{s.service_id}:{s.node_id}:{s.endpoint_token}" for s in services]
        + [f"{p.package_id}:{p.owner_service_id}:{','.join(p.dependency_ids)}" for p in packages]
        + [f"{t.step}:{t.service_id}:{t.package_id}:{t.event_token}" for t in traces]
    ).encode("utf-8")

    return LivingSyntheticSystem(
        universe_id=graph.universe_id,
        epoch=graph.epoch,
        services=services,
        packages=packages,
        traces=traces,
        provenance="living-synthetic-system",
        deployable=False,
        system_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def validate_living_synthetic_system(system: LivingSyntheticSystem, graph: ShadowGraph) -> None:
    validate_no_return_graph(graph)
    if not isinstance(system, LivingSyntheticSystem):
        raise SyntheticSystemError("invalid synthetic system")
    if system.provenance != "living-synthetic-system" or system.deployable is not False:
        raise SyntheticSystemError("synthetic system provenance/deployability invariant failed")
    if system.universe_id != graph.universe_id or system.epoch != graph.epoch:
        raise SyntheticSystemError("synthetic system escaped its shadow universe")
    node_ids = {n.node_id for n in graph.nodes}
    service_ids = {s.service_id for s in system.services}
    package_ids = {p.package_id for p in system.packages}
    if not service_ids or not package_ids:
        raise SyntheticSystemError("synthetic system must contain services and packages")
    if any(s.node_id not in node_ids for s in system.services):
        raise SyntheticSystemError("service references non-shadow node")
    if any(not sid.startswith("svc-") for sid in service_ids):
        raise SyntheticSystemError("non-synthetic service identity present")
    if any(not pid.startswith("pkg-") for pid in package_ids):
        raise SyntheticSystemError("non-synthetic package identity present")
    for package in system.packages:
        if package.owner_service_id not in service_ids:
            raise SyntheticSystemError("package owner escapes synthetic namespace")
        if any(dep not in package_ids for dep in package.dependency_ids):
            raise SyntheticSystemError("package dependency escapes synthetic namespace")
    for trace in system.traces:
        if trace.service_id not in service_ids or trace.package_id not in package_ids:
            raise SyntheticSystemError("trace escapes synthetic namespace")


def require_canonical_system_promotion(_system: LivingSyntheticSystem) -> None:
    raise SyntheticSystemError("living synthetic system can never enter canonical build/sign/deploy")

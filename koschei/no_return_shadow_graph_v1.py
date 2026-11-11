"""Koschei No-Return Shadow Graph v1.

Builds a session+epoch scoped synthetic dependency graph on top of an Event
Horizon envelope. The graph contains only shadow identities and synthetic edges.
It exposes no canonical lookup, reverse-resolution, path fallback, or promotion
primitive. Validation fails closed on malformed or foreign graph material.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from koschei.event_horizon_isolation_v1 import VoidEnvelope


class ShadowGraphError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ShadowNode:
    node_id: str
    role: str


@dataclass(frozen=True, slots=True)
class ShadowEdge:
    src: str
    dst: str
    relation: str


@dataclass(frozen=True, slots=True)
class ShadowGraph:
    universe_id: str
    epoch: int
    root_node_id: str
    nodes: tuple[ShadowNode, ...]
    edges: tuple[ShadowEdge, ...]
    provenance: str
    deployable: bool
    graph_digest: str


def _require_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ShadowGraphError("graph_key must contain at least 256 bits")
    return key


def _node_id(key: bytes, *, universe_id: str, epoch: int, index: int, role: str) -> str:
    msg = (
        b"koschei/no-return-shadow-graph/v1\x00"
        + universe_id.encode("utf-8") + b"\x00"
        + str(epoch).encode("ascii") + b"\x00"
        + str(index).encode("ascii") + b"\x00"
        + role.encode("ascii")
    )
    return "s-" + hmac.new(key, msg, hashlib.sha256).hexdigest()[:40]


def build_shadow_graph(*, envelope: VoidEnvelope, graph_key: bytes,
                       width: int = 8) -> ShadowGraph:
    if not isinstance(envelope, VoidEnvelope):
        raise ShadowGraphError("envelope must be a VoidEnvelope")
    if envelope.provenance != "event-horizon-decoy" or envelope.deployable is not False:
        raise ShadowGraphError("foreign/canonical material cannot seed a shadow graph")
    key = _require_key(graph_key)
    if not isinstance(width, int) or isinstance(width, bool) or width < 4 or width > 64:
        raise ShadowGraphError("width must be an integer in [4, 64]")

    roles = ("entry", "logic", "state", "policy", "adapter", "worker", "cache", "sink")
    nodes = tuple(
        ShadowNode(_node_id(key, universe_id=envelope.universe_id, epoch=envelope.epoch,
                            index=i, role=roles[i % len(roles)]), roles[i % len(roles)])
        for i in range(width)
    )

    # Closed synthetic topology: every edge terminates at another shadow node.
    edges: list[ShadowEdge] = []
    for i, node in enumerate(nodes):
        edges.append(ShadowEdge(node.node_id, nodes[(i + 1) % width].node_id, "depends"))
        if width >= 6 and i % 2 == 0:
            edges.append(ShadowEdge(node.node_id, nodes[(i + 3) % width].node_id, "observes"))

    frozen_edges = tuple(edges)
    payload = "|".join(
        [envelope.universe_id, str(envelope.epoch), nodes[0].node_id]
        + [f"{n.node_id}:{n.role}" for n in nodes]
        + [f"{e.src}>{e.relation}>{e.dst}" for e in frozen_edges]
    ).encode("utf-8")
    return ShadowGraph(
        universe_id=envelope.universe_id,
        epoch=envelope.epoch,
        root_node_id=nodes[0].node_id,
        nodes=nodes,
        edges=frozen_edges,
        provenance="no-return-shadow-graph",
        deployable=False,
        graph_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def validate_no_return_graph(graph: ShadowGraph) -> None:
    if not isinstance(graph, ShadowGraph):
        raise ShadowGraphError("invalid shadow graph")
    if graph.provenance != "no-return-shadow-graph" or graph.deployable is not False:
        raise ShadowGraphError("shadow graph provenance/deployability invariant failed")
    ids = {node.node_id for node in graph.nodes}
    if not ids or graph.root_node_id not in ids:
        raise ShadowGraphError("shadow graph root is invalid")
    if len(ids) != len(graph.nodes):
        raise ShadowGraphError("shadow node identities must be unique")
    if any(not node.node_id.startswith("s-") for node in graph.nodes):
        raise ShadowGraphError("non-shadow identity present")
    for edge in graph.edges:
        if edge.src not in ids or edge.dst not in ids:
            raise ShadowGraphError("edge escapes shadow namespace")
        if edge.relation not in {"depends", "observes"}:
            raise ShadowGraphError("unknown shadow relation")


def resolve_shadow_node(graph: ShadowGraph, node_id: str) -> tuple[ShadowEdge, ...]:
    """Traverse only within the synthetic graph; there is no canonical resolver."""
    validate_no_return_graph(graph)
    if node_id not in {node.node_id for node in graph.nodes}:
        raise ShadowGraphError("unknown shadow node")
    return tuple(edge for edge in graph.edges if edge.src == node_id)


def require_canonical_graph_promotion(_graph: ShadowGraph) -> None:
    raise ShadowGraphError("no-return shadow graph can never enter canonical build/sign/deploy")

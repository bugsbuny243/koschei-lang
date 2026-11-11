"""Project-backed Universe provider v1.

Builds the spatial projection from a real checked Koschei module graph. No demo
or synthetic project data is introduced here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .modules import ModuleGraph, check_graph, load_graph
from .universe_live_state_v1 import UniverseLiveStateV1, bind_live_state_v1
from .universe_projection_v1 import (
    UniverseEdgeV1,
    UniverseNodeV1,
    UniverseProjectionV1,
    project_universe_v1,
)

_CTX_PROJECT = b"koschei.universe-project/v1\x00"
_CTX_EDGE = b"koschei.universe-import/v1\x00"


@dataclass(frozen=True, slots=True)
class ProjectUniverseV1:
    source: Path
    projection: UniverseProjectionV1
    live: UniverseLiveStateV1


def _module_digest(path: Path) -> bytes:
    return hashlib.sha3_256(path.read_bytes()).digest()


def _project_digest(graph: ModuleGraph, module_digests: dict[str, bytes]) -> bytes:
    h = hashlib.sha3_256(_CTX_PROJECT)
    for key in sorted(graph.modules):
        module = graph.modules[key]
        h.update(module.name.encode("utf-8") + b"\x00" + module_digests[key])
    return h.digest()


def build_project_universe_v1(source: str | Path) -> ProjectUniverseV1:
    root = Path(source).resolve()
    graph = load_graph(root)
    check_graph(graph)

    digests = {key: _module_digest(module.path) for key, module in graph.modules.items()}
    project_digest = _project_digest(graph, digests)
    project_id = f"project:{graph.root_module.name}"

    nodes: list[UniverseNodeV1] = [UniverseNodeV1(project_id, "project", project_digest)]
    key_to_id: dict[str, str] = {}
    for key, module in sorted(graph.modules.items(), key=lambda item: item[1].name):
        node_id = f"module:{module.name}"
        if node_id in key_to_id.values():
            node_id = f"module:{module.name}:{digests[key].hex()[:10]}"
        key_to_id[key] = node_id
        nodes.append(UniverseNodeV1(node_id, "module", digests[key]))

    edges: list[UniverseEdgeV1] = []
    root_edge_digest = hashlib.sha3_256(_CTX_EDGE + project_digest + digests[graph.root]).digest()
    edges.append(UniverseEdgeV1(project_id, key_to_id[graph.root], "depends", root_edge_digest))
    for source_key, module in graph.modules.items():
        for local_name, target_key in sorted(module.imports.items()):
            evidence = hashlib.sha3_256(
                _CTX_EDGE
                + digests[source_key]
                + local_name.encode("utf-8")
                + b"\x00"
                + digests[target_key]
            ).digest()
            edges.append(UniverseEdgeV1(key_to_id[source_key], key_to_id[target_key], "imports", evidence))

    projection = project_universe_v1(
        project_digest=project_digest,
        epoch=0,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
    live = bind_live_state_v1(projection=projection, events=())
    return ProjectUniverseV1(root, projection, live)

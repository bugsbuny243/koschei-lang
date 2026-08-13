from __future__ import annotations

import unittest

from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import (
    ShadowGraphError,
    build_shadow_graph,
    require_canonical_graph_promotion,
    resolve_shadow_node,
    validate_no_return_graph,
)

OID = "0123456789abcdef0123456789abcdef"
ISO = b"i" * 32
DEC = b"d" * 32
GRAPH = b"g" * 32


class NoReturnShadowGraphV1Tests(unittest.TestCase):
    def _env(self, session: str = "session-001", epoch: int = 41):
        return enter_event_horizon(
            project_id="p-shadow",
            object_id=OID,
            session_id=session,
            epoch=epoch,
            isolation_key=ISO,
            deception_key=DEC,
        )

    def test_graph_contains_only_shadow_identities_and_closed_edges(self):
        graph = build_shadow_graph(envelope=self._env(), graph_key=GRAPH, width=12)
        validate_no_return_graph(graph)
        ids = {n.node_id for n in graph.nodes}
        self.assertTrue(all(node_id.startswith("s-") for node_id in ids))
        self.assertTrue(all(e.src in ids and e.dst in ids for e in graph.edges))
        self.assertFalse(graph.deployable)
        self.assertEqual(graph.provenance, "no-return-shadow-graph")

    def test_graph_rotates_with_session_and_epoch(self):
        a = build_shadow_graph(envelope=self._env("session-001", 41), graph_key=GRAPH)
        b = build_shadow_graph(envelope=self._env("session-002", 41), graph_key=GRAPH)
        c = build_shadow_graph(envelope=self._env("session-001", 42), graph_key=GRAPH)
        self.assertNotEqual(a.graph_digest, b.graph_digest)
        self.assertNotEqual(a.graph_digest, c.graph_digest)
        self.assertNotEqual(a.root_node_id, b.root_node_id)
        self.assertNotEqual(a.root_node_id, c.root_node_id)

    def test_traversal_never_resolves_outside_shadow_namespace(self):
        graph = build_shadow_graph(envelope=self._env(), graph_key=GRAPH, width=10)
        for node in graph.nodes:
            outgoing = resolve_shadow_node(graph, node.node_id)
            self.assertTrue(all(edge.src.startswith("s-") and edge.dst.startswith("s-") for edge in outgoing))

    def test_unknown_shadow_node_fails_closed(self):
        graph = build_shadow_graph(envelope=self._env(), graph_key=GRAPH)
        with self.assertRaises(ShadowGraphError):
            resolve_shadow_node(graph, "s-does-not-exist")

    def test_graph_cannot_be_promoted_to_canonical(self):
        graph = build_shadow_graph(envelope=self._env(), graph_key=GRAPH)
        with self.assertRaises(ShadowGraphError):
            require_canonical_graph_promotion(graph)

    def test_invalid_graph_key_and_width_fail_closed(self):
        env = self._env()
        with self.assertRaises(ShadowGraphError):
            build_shadow_graph(envelope=env, graph_key=b"short")
        with self.assertRaises(ShadowGraphError):
            build_shadow_graph(envelope=env, graph_key=GRAPH, width=2)


if __name__ == "__main__":
    unittest.main()

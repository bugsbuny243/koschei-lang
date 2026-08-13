from __future__ import annotations

import unittest

from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.living_synthetic_system_v1 import build_living_synthetic_system
from koschei.synthetic_reality_plane_v1 import build_synthetic_reality

PROJECT = "koschei-adaptive-observer"
OID_A = "a1" * 32
OID_B = "b2" * 32
ISO = b"I" * 32
DEC = b"D" * 32
GRAPH = b"G" * 32
SYSTEM = b"S" * 32
REALITY = b"R" * 32


def _view(object_id: str, session: str, epoch: int):
    env = enter_event_horizon(
        project_id=PROJECT,
        object_id=object_id,
        session_id=session,
        epoch=epoch,
        isolation_key=ISO,
        deception_key=DEC,
    )
    graph = build_shadow_graph(envelope=env, graph_key=GRAPH, width=8)
    system = build_living_synthetic_system(graph=graph, system_key=SYSTEM, trace_length=24)
    reality = build_synthetic_reality(system=system, graph=graph, reality_key=REALITY)
    return env, graph, system, reality


def _shape(view):
    env, graph, system, reality = view
    return (
        len(env.content), len(graph.nodes), len(graph.edges),
        len(system.services), len(system.packages), len(system.traces),
        len(reality.configs), len(reality.telemetry), len(reality.logs), len(reality.incidents),
    )


def _rotating_identity_tokens(view):
    env, graph, system, reality = view
    out = {env.universe_id, env.shadow_object_id, env.content_sha256, graph.graph_digest,
           system.system_digest, reality.reality_digest}
    out.update(n.node_id for n in graph.nodes)
    out.update(s.service_id for s in system.services)
    out.update(p.package_id for p in system.packages)
    out.update(t.event_token for t in system.traces)
    out.update(c.config_id for c in reality.configs)
    out.update(l.log_id for l in reality.logs)
    out.update(i.incident_id for i in reality.incidents)
    return out


def _shape_tokens(view):
    # Metric identifiers are intentionally a fixed synthetic schema. They are
    # public shape, not per-object/session identity, and therefore must be
    # evaluated for label parity rather than uniqueness.
    reality = view[3]
    return {m.metric_id for m in reality.telemetry}


class AdaptiveObserverCorrelationV1Tests(unittest.TestCase):
    def test_128_session_history_has_no_reused_rotating_identity_token(self):
        seen: set[str] = set()
        for i in range(128):
            current = _rotating_identity_tokens(_view(OID_A, f"observer-{i:03d}-aaaaaaaa", i))
            self.assertTrue(seen.isdisjoint(current))
            seen.update(current)

    def test_same_object_and_different_object_have_same_public_shape_contract(self):
        for i in range(64):
            a = _shape(_view(OID_A, f"shape-{i:03d}-aaaaaaaa", i))
            b = _shape(_view(OID_B, f"shape-{i:03d}-bbbbbbbb", i))
            self.assertEqual(a, b)

    def test_repeated_shape_history_carries_no_object_label_signal(self):
        history_a = [_shape(_view(OID_A, f"hist-{i:03d}-aaaaaaaa", i)) for i in range(64)]
        history_b = [_shape(_view(OID_B, f"hist-{i:03d}-bbbbbbbb", i)) for i in range(64)]
        self.assertEqual(history_a, history_b)

    def test_cross_session_rotating_identity_sets_are_disjoint_for_same_object(self):
        for i in range(32):
            a = _rotating_identity_tokens(_view(OID_A, f"left-{i:03d}-aaaaaaaa", i))
            b = _rotating_identity_tokens(_view(OID_A, f"right-{i:03d}-bbbbbbbb", i))
            self.assertTrue(a.isdisjoint(b))

    def test_public_shape_schema_is_object_independent(self):
        for i in range(32):
            a = _shape_tokens(_view(OID_A, f"obj-a-{i:03d}-aaaaaaaa", i))
            b = _shape_tokens(_view(OID_B, f"obj-b-{i:03d}-bbbbbbbb", i))
            self.assertEqual(a, b)

    def test_long_history_exposes_no_canonical_object_identifiers(self):
        material = []
        for i in range(32):
            material.append(repr(_view(OID_A, f"canon-{i:03d}-aaaaaaaa", i)).lower())
        exposed = "\n".join(material)
        self.assertNotIn(OID_A.lower(), exposed)
        self.assertNotIn(OID_B.lower(), exposed)


if __name__ == "__main__":
    unittest.main()

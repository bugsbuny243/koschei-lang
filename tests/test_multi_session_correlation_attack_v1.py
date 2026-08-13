from __future__ import annotations

import hashlib
import unittest

from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.living_synthetic_system_v1 import build_living_synthetic_system
from koschei.synthetic_reality_plane_v1 import build_synthetic_reality_plane


PROJECT = "koschei-correlation-lab"
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
    reality = build_synthetic_reality_plane(system=system, reality_key=REALITY)
    return env, graph, system, reality


def _public_fingerprint(view) -> str:
    env, graph, system, reality = view
    # Deliberately limited to attacker-visible structural surface. No canonical id/path/source.
    material = "|".join(
        [
            str(len(env.content)),
            str(len(graph.nodes)),
            str(len(graph.edges)),
            str(len(system.services)),
            str(len(system.packages)),
            str(len(system.traces)),
            str(len(reality.config)),
            str(len(reality.telemetry)),
            str(len(reality.logs)),
            str(len(reality.incidents)),
            env.content_sha256,
            graph.graph_digest,
            system.system_digest,
            reality.reality_digest,
        ]
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class MultiSessionCorrelationAttackV1Tests(unittest.TestCase):
    def test_same_object_rotates_across_64_session_epoch_views(self):
        fps = {
            _public_fingerprint(_view(OID_A, f"session-{i:03d}-aaaaaaaa", i))
            for i in range(64)
        }
        self.assertEqual(len(fps), 64)

    def test_cross_object_views_do_not_collapse_to_same_fingerprint(self):
        for i in range(32):
            a = _public_fingerprint(_view(OID_A, f"session-{i:03d}-aaaaaaaa", i))
            b = _public_fingerprint(_view(OID_B, f"session-{i:03d}-bbbbbbbb", i))
            self.assertNotEqual(a, b)

    def test_shadow_identity_sets_have_zero_overlap_across_sessions(self):
        a = _view(OID_A, "session-alpha-aaaaaaaa", 7)[1]
        b = _view(OID_A, "session-bravo-bbbbbbbb", 7)[1]
        self.assertTrue({n.node_id for n in a.nodes}.isdisjoint({n.node_id for n in b.nodes}))

    def test_service_package_and_event_tokens_rotate_across_sessions(self):
        a = _view(OID_A, "session-charlie-cccccccc", 9)[2]
        b = _view(OID_A, "session-delta-dddddddd", 9)[2]
        self.assertTrue({s.service_id for s in a.services}.isdisjoint({s.service_id for s in b.services}))
        self.assertTrue({p.package_id for p in a.packages}.isdisjoint({p.package_id for p in b.packages}))
        self.assertTrue({t.event_token for t in a.traces}.isdisjoint({t.event_token for t in b.traces}))

    def test_reality_tokens_rotate_across_epochs(self):
        a = _view(OID_A, "session-echo-eeeeeeee", 11)[3]
        b = _view(OID_A, "session-echo-eeeeeeee", 12)[3]
        self.assertNotEqual(a.reality_digest, b.reality_digest)
        self.assertTrue({x.log_id for x in a.logs}.isdisjoint({x.log_id for x in b.logs}))
        self.assertTrue({x.incident_id for x in a.incidents}.isdisjoint({x.incident_id for x in b.incidents}))

    def test_public_surface_contains_no_canonical_object_id(self):
        env, graph, system, reality = _view(OID_A, "session-foxtrot-ffffffff", 13)
        exposed = repr((env, graph, system, reality)).lower()
        self.assertNotIn(OID_A.lower(), exposed)


if __name__ == "__main__":
    unittest.main()

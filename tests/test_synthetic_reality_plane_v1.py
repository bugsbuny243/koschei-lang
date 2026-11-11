from __future__ import annotations

import unittest

from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.living_synthetic_system_v1 import build_living_synthetic_system
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.synthetic_reality_plane_v1 import (
    SyntheticRealityError,
    build_synthetic_reality,
    require_canonical_reality_promotion,
    validate_synthetic_reality,
)


OID = "a" * 64
ISO = b"i" * 32
DEC = b"d" * 32
GRAPH = b"g" * 32
SYSTEM = b"s" * 32
REALITY = b"r" * 32


def build(session: str = "session-0001", epoch: int = 11):
    env = enter_event_horizon(
        project_id="koschei", object_id=OID, session_id=session, epoch=epoch,
        isolation_key=ISO, deception_key=DEC,
    )
    graph = build_shadow_graph(envelope=env, graph_key=GRAPH, width=8)
    system = build_living_synthetic_system(graph=graph, system_key=SYSTEM, trace_length=32)
    plane = build_synthetic_reality(system=system, graph=graph, reality_key=REALITY)
    return graph, system, plane


class SyntheticRealityPlaneV1Tests(unittest.TestCase):
    def test_reality_is_deterministic_inside_same_universe(self):
        g1, s1, p1 = build()
        g2, s2, p2 = build()
        self.assertEqual(p1, p2)
        validate_synthetic_reality(p1, s1, g1)
        validate_synthetic_reality(p2, s2, g2)

    def test_session_or_epoch_rotates_entire_reality(self):
        _, _, a = build("session-0001", 11)
        _, _, b = build("session-0002", 11)
        _, _, c = build("session-0001", 12)
        self.assertNotEqual(a.reality_digest, b.reality_digest)
        self.assertNotEqual(a.reality_digest, c.reality_digest)

    def test_config_telemetry_logs_and_incidents_are_cross_consistent(self):
        graph, system, plane = build()
        validate_synthetic_reality(plane, system, graph)
        service_ids = {s.service_id for s in system.services}
        package_ids = {p.package_id for p in system.packages}
        log_ids = {l.log_id for l in plane.logs}
        self.assertTrue(all(c.service_id in service_ids and c.package_id in package_ids for c in plane.configs))
        self.assertTrue(all(m.service_id in service_ids for m in plane.telemetry))
        self.assertTrue(all(l.service_id in service_ids for l in plane.logs))
        self.assertTrue(all(i.service_id in service_ids and i.log_id in log_ids for i in plane.incidents))

    def test_reality_contains_no_canonical_identity_or_path_material(self):
        _, _, plane = build()
        blob = repr(plane).lower()
        self.assertNotIn(OID.lower(), blob)
        self.assertNotIn("canonical", blob)
        self.assertNotIn("/src/", blob)
        self.assertNotIn("\\src\\", blob)

    def test_reality_is_permanently_non_deployable_and_non_promotable(self):
        _, _, plane = build()
        self.assertFalse(plane.deployable)
        self.assertEqual(plane.provenance, "synthetic-reality-plane")
        with self.assertRaises(SyntheticRealityError):
            require_canonical_reality_promotion(plane)

    def test_foreign_universe_validation_fails_closed(self):
        graph_a, system_a, plane_a = build("session-0001", 11)
        graph_b, system_b, _ = build("session-0002", 11)
        with self.assertRaises(SyntheticRealityError):
            validate_synthetic_reality(plane_a, system_b, graph_b)
        validate_synthetic_reality(plane_a, system_a, graph_a)


if __name__ == "__main__":
    unittest.main()

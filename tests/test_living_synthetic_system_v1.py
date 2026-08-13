from __future__ import annotations

import unittest

from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.living_synthetic_system_v1 import (
    SyntheticSystemError,
    build_living_synthetic_system,
    require_canonical_system_promotion,
    validate_living_synthetic_system,
)

OID = "0123456789abcdef0123456789abcdef"
ISO = b"i" * 32
DEC = b"d" * 32
GRAPH = b"g" * 32
SYS = b"s" * 32


class LivingSyntheticSystemV1Tests(unittest.TestCase):
    def _system(self, *, session="session-aaaaaaaa", epoch=77):
        env = enter_event_horizon(
            project_id="p", object_id=OID, session_id=session, epoch=epoch,
            isolation_key=ISO, deception_key=DEC,
        )
        graph = build_shadow_graph(envelope=env, graph_key=GRAPH, width=8)
        system = build_living_synthetic_system(graph=graph, system_key=SYS, trace_length=24)
        return graph, system

    def test_services_packages_and_traces_are_synthetic_only(self):
        graph, system = self._system()
        validate_living_synthetic_system(system, graph)
        self.assertTrue(all(s.service_id.startswith("svc-") for s in system.services))
        self.assertTrue(all(p.package_id.startswith("pkg-") for p in system.packages))
        self.assertTrue(all(t.event_token.startswith("evt-") for t in system.traces))
        self.assertFalse(system.deployable)

    def test_system_is_stable_for_same_shadow_universe(self):
        _, a = self._system()
        _, b = self._system()
        self.assertEqual(a.system_digest, b.system_digest)
        self.assertEqual(a.services, b.services)
        self.assertEqual(a.packages, b.packages)
        self.assertEqual(a.traces, b.traces)

    def test_session_or_epoch_rotation_changes_living_system(self):
        _, a = self._system(session="session-aaaaaaaa", epoch=77)
        _, b = self._system(session="session-bbbbbbbb", epoch=77)
        _, c = self._system(session="session-aaaaaaaa", epoch=78)
        self.assertNotEqual(a.system_digest, b.system_digest)
        self.assertNotEqual(a.system_digest, c.system_digest)

    def test_trace_references_remain_inside_synthetic_namespaces(self):
        graph, system = self._system()
        validate_living_synthetic_system(system, graph)
        service_ids = {s.service_id for s in system.services}
        package_ids = {p.package_id for p in system.packages}
        self.assertTrue(all(t.service_id in service_ids for t in system.traces))
        self.assertTrue(all(t.package_id in package_ids for t in system.traces))

    def test_dependencies_never_escape_synthetic_package_set(self):
        graph, system = self._system()
        validate_living_synthetic_system(system, graph)
        package_ids = {p.package_id for p in system.packages}
        for package in system.packages:
            self.assertTrue(all(dep in package_ids for dep in package.dependency_ids))

    def test_canonical_promotion_is_permanently_forbidden(self):
        _, system = self._system()
        with self.assertRaises(SyntheticSystemError):
            require_canonical_system_promotion(system)


if __name__ == "__main__":
    unittest.main()

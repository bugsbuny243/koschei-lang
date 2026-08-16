from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.native_value_domain_originality_v1 import audit_native_value_domain_surface_v1
from koschei.native_value_domains_v1 import (
    GLYPHS,
    TRUTH,
    WHOLE,
    check_native_value_domains,
)
from koschei.object_space_value_domains_v1 import (
    NATIVE_VALUE_DOMAIN_FRONTEND_V1,
    check_native_value_domain_object_space,
    encode_native_value_domain_graph_secret,
    load_authenticated_native_value_domains,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeValueDomainsV1Tests(unittest.TestCase):
    def test_whole_truth_and_glyphs_are_distinct_graph_domains(self) -> None:
        whole = check_native_value_domains(
            "witness amount 40\n"
            "witness fee 2\n"
            "witness total sum amount fee\n"
            "resolve total\n"
        )
        truth = check_native_value_domains(
            "witness enabled truth yes\n"
            "resolve enabled\n"
        )
        glyphs = check_native_value_domains(
            "witness label glyphs 5 café\n"
            "witness doubled merge label label\n"
            "resolve doubled\n"
        )
        self.assertEqual(whole.value.domain, WHOLE)
        self.assertEqual(whole.value.value, 42)
        self.assertEqual(truth.value.domain, TRUTH)
        self.assertIs(truth.value.value, True)
        self.assertEqual(glyphs.values["label"].domain, GLYPHS)
        self.assertEqual(glyphs.values["label"].value, "café")
        self.assertEqual(glyphs.value.domain, GLYPHS)
        self.assertEqual(glyphs.value.value, "cafécafé")

    def test_same_produces_truth_only_for_same_domain(self) -> None:
        checked = check_native_value_domains(
            "witness left glyphs 5 hello\n"
            "witness right glyphs 5 hello\n"
            "witness equal same left right\n"
            "resolve equal\n"
        )
        self.assertEqual(checked.value.domain, TRUTH)
        self.assertIs(checked.value.value, True)

    def test_source_order_does_not_define_execution_order(self) -> None:
        forward = check_native_value_domains(
            "witness equal same total expected\n"
            "witness expected 42\n"
            "witness total sum base fee\n"
            "witness fee 2\n"
            "witness base 40\n"
            "resolve equal\n"
        )
        canonical = check_native_value_domains(
            "witness base 40\n"
            "witness fee 2\n"
            "witness total sum base fee\n"
            "witness expected 42\n"
            "witness equal same total expected\n"
            "resolve equal\n"
        )
        self.assertEqual(forward.value, canonical.value)
        self.assertEqual(forward.dependency_order, canonical.dependency_order)

    def test_authenticated_object_space_binding_loads_exact_value_frontend(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("f1" * 16)
        root_id = bytes.fromhex("f2" * 16)
        payload = (
            "witness hello glyphs 5 hello\n"
            "witness world glyphs 5 world\n"
            "witness message merge hello world\n"
            "resolve message\n"
        ).encode("utf-8")
        objects = {root_id: payload}
        secret = encode_native_value_domain_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
        )
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = create_object_space_project(
                Path(temporary) / "space",
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=now,
                project_id=project_id,
            )
            checked = load_authenticated_native_value_domains(project)
            self.assertEqual(checked.value.value, "helloworld")
            graph, report = check_native_value_domain_object_space(project)
            self.assertIsNotNone(graph.mir)
            self.assertEqual(report.functions, 1)
            self.assertEqual(len(NATIVE_VALUE_DOMAIN_FRONTEND_V1), 32)

    def test_originality_contract_accepts_registered_domain_vocabulary(self) -> None:
        self.assertEqual(audit_native_value_domain_surface_v1(), ())


if __name__ == "__main__":
    unittest.main()

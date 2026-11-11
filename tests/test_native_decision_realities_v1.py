from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei.ast_nodes import LetStatement
from koschei.native_decision_originality_v1 import audit_native_decision_surface_v1
from koschei.native_decision_realities_v1 import (
    NativeDecisionRealityError,
    check_native_decision_reality,
)
from koschei.native_value_domains_v1 import GLYPHS, TRUTH, WHOLE
from koschei.object_space_decision_realities_v1 import (
    NATIVE_DECISION_FRONTEND_V1,
    check_native_decision_object_space,
    encode_native_decision_graph_secret,
    load_authenticated_native_decision,
)
from koschei.object_space_v1 import create_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeDecisionRealitiesV1Tests(unittest.TestCase):
    def test_truth_yes_settles_affirmative_whole_reality(self) -> None:
        checked = check_native_decision_reality(
            "witness gate truth yes\n"
            "witness approved 42\n"
            "witness denied 7\n"
            "witness result settle gate approved denied\n"
            "resolve result\n"
        )
        self.assertEqual(checked.value.domain, WHOLE)
        self.assertEqual(checked.value.value, 42)
        self.assertIn("denied", checked.structural_order)
        self.assertNotIn("denied", checked.active_order)
        self.assertIn("approved", checked.active_order)

    def test_truth_no_settles_negative_glyph_reality(self) -> None:
        checked = check_native_decision_reality(
            "witness gate truth no\n"
            "witness approved glyphs 3 yes\n"
            "witness denied glyphs 2 no\n"
            "witness result settle gate approved denied\n"
            "resolve result\n"
        )
        self.assertEqual(checked.value.domain, GLYPHS)
        self.assertEqual(checked.value.value, "no")
        self.assertNotIn("approved", checked.active_order)
        self.assertIn("denied", checked.active_order)

    def test_settle_can_select_truth_as_data_without_becoming_control_statement(self) -> None:
        checked = check_native_decision_reality(
            "witness gate truth yes\n"
            "witness positive truth yes\n"
            "witness negative truth no\n"
            "witness result settle gate positive negative\n"
            "resolve result\n"
        )
        self.assertEqual(checked.value.domain, TRUTH)
        self.assertIs(checked.value.value, True)

    def test_settle_requires_truth_condition_and_identical_candidate_domains(self) -> None:
        with self.assertRaisesRegex(NativeDecisionRealityError, "condition must be truth"):
            check_native_decision_reality(
                "witness gate 1\n"
                "witness left 2\n"
                "witness right 3\n"
                "witness result settle gate left right\n"
                "resolve result\n"
            )
        with self.assertRaisesRegex(NativeDecisionRealityError, "identical value domains"):
            check_native_decision_reality(
                "witness gate truth yes\n"
                "witness left 2\n"
                "witness right glyphs 1 x\n"
                "witness result settle gate left right\n"
                "resolve result\n"
            )

    def test_unselected_candidate_is_still_statically_validated(self) -> None:
        with self.assertRaisesRegex(NativeDecisionRealityError, "exceeds signed Int64 reality"):
            check_native_decision_reality(
                "witness gate truth yes\n"
                "witness good 42\n"
                "witness top 9223372036854775807\n"
                "witness one 1\n"
                "witness bad sum top one\n"
                "witness result settle gate good bad\n"
                "resolve result\n"
            )

    def test_backend_realization_omits_unselected_candidate_path(self) -> None:
        checked = check_native_decision_reality(
            "witness gate truth yes\n"
            "witness goodbase 40\n"
            "witness good sum goodbase 2\n"
            "witness badbase 900\n"
            "witness bad sum badbase 1\n"
            "witness result settle gate good bad\n"
            "resolve result\n"
        )
        function = checked.lowered.declarations[0]
        names = tuple(
            statement.name
            for statement in function.body.statements
            if isinstance(statement, LetStatement)
        )
        self.assertEqual(names, checked.active_order)
        self.assertIn("goodbase", names)
        self.assertIn("good", names)
        self.assertNotIn("badbase", names)
        self.assertNotIn("bad", names)
        self.assertEqual(checked.value.value, 42)

    def test_source_clause_order_is_not_decision_execution_order(self) -> None:
        forward = check_native_decision_reality(
            "witness result settle gate chosen rejected\n"
            "witness rejected 9\n"
            "witness chosen 42\n"
            "witness gate truth yes\n"
            "resolve result\n"
        )
        canonical = check_native_decision_reality(
            "witness gate truth yes\n"
            "witness chosen 42\n"
            "witness rejected 9\n"
            "witness result settle gate chosen rejected\n"
            "resolve result\n"
        )
        self.assertEqual(forward.value, canonical.value)
        self.assertEqual(forward.structural_order, canonical.structural_order)
        self.assertEqual(forward.active_order, canonical.active_order)

    def test_authenticated_object_space_binding_uses_distinct_decision_frontend(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("91" * 16)
        root_id = bytes.fromhex("92" * 16)
        payload = (
            "witness gate truth yes\n"
            "witness chosen glyphs 2 ok\n"
            "witness rejected glyphs 2 no\n"
            "witness result settle gate chosen rejected\n"
            "resolve result\n"
        ).encode("utf-8")
        objects = {root_id: payload}
        secret = encode_native_decision_graph_secret(
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
            checked = load_authenticated_native_decision(project)
            self.assertEqual(checked.value.value, "ok")
            graph, report = check_native_decision_object_space(project)
            self.assertIsNotNone(graph.mir)
            self.assertEqual(report.functions, 1)
            self.assertEqual(len(NATIVE_DECISION_FRONTEND_V1), 32)

    def test_originality_contract_accepts_settle_with_explicit_provenance(self) -> None:
        self.assertEqual(audit_native_decision_surface_v1(), ())


if __name__ == "__main__":
    unittest.main()

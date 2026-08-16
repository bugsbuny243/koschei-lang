from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_decision_realities_v1 import check_native_decision_reality
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_decision_realities_v1 import (
    DECISION_GRAPH_MAGIC_V1,
    ObjectSpaceDecisionRealityError,
    encode_native_decision_graph_secret,
)
from koschei.object_space_value_domains_v1 import (
    VALUE_DOMAIN_GRAPH_MAGIC_V1,
    ObjectSpaceValueDomainError,
)
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


def execute_lowered(source: str):
    checked = check_native_decision_reality(source)
    return checked, Interpreter(checked.lowered, []).execute_main()


class NativeDecisionRealitiesExecutionV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("a5" * 16)
        self.root_id = bytes.fromhex("a6" * 16)
        self.source = (
            "witness gate truth yes\n"
            "witness chosen glyphs 2 ok\n"
            "witness rejected glyphs 6 secret\n"
            "witness result settle gate chosen rejected\n"
            "resolve result\n"
        ).encode("utf-8")
        self.objects = {self.root_id: self.source}
        self.secret = encode_native_decision_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
        )

    def create(self, root: Path):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=self.secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def opener(self, handle: bytes, *, project_override=None):
        def open_project(path: Path):
            if project_override is not None:
                return project_override
            return load_object_space_project(
                path,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=self.project_id,
                expected_epoch=1,
                temporal_policy=self.policy,
                now=self.now,
            )
        return open_project

    def test_selected_whole_truth_and_glyph_values_match_backend_execution(self) -> None:
        for source, expected in (
            (
                "witness gate truth yes\n"
                "witness chosen 42\n"
                "witness rejected 7\n"
                "witness result settle gate chosen rejected\n"
                "resolve result\n",
                42,
            ),
            (
                "witness gate truth no\n"
                "witness chosen truth yes\n"
                "witness rejected truth no\n"
                "witness result settle gate chosen rejected\n"
                "resolve result\n",
                False,
            ),
            (
                "witness gate truth yes\n"
                "witness chosen glyphs 2 ok\n"
                "witness rejected glyphs 2 no\n"
                "witness result settle gate chosen rejected\n"
                "resolve result\n",
                "ok",
            ),
        ):
            with self.subTest(expected=expected):
                checked, runtime = execute_lowered(source)
                self.assertEqual(runtime, expected)
                self.assertEqual(checked.value.value, expected)

    def test_real_object_space_run_executes_only_selected_decision_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            with object_space_check_session(self.opener(handle)):
                _, graph = commands._checked(str(root))
                mir_graph = require_mir(graph)
                mir_graph.assert_sealed()
                mir_root = mir_graph.root_module
                runtime_value = Interpreter(
                    mir_root.program,
                    [],
                    mir_graph.namespaces(),
                    dict(mir_root.imports),
                    mir_graph.enums(),
                    mir_graph.module_imports(),
                    mir_graph.structs(),
                ).execute_main()
                self.assertEqual(runtime_value, "ok")
                self.assertEqual(cli.command_run(str(root)), 0)

    def test_public_mir_and_native_source_omit_unselected_witness_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            captured = io.StringIO()
            with object_space_check_session(self.opener(handle)):
                with redirect_stdout(captured), redirect_stderr(captured):
                    self.assertEqual(cli.command_mir(str(root)), 0)
                    self.assertEqual(cli.command_emit_go(str(root)), 0)
                    self.assertEqual(cli.command_caps(str(root), True, None), 0)
            text = captured.getvalue()
            self.assertNotIn("rejected", text)
            self.assertNotIn("secret", text)
            needles = [self.project_id.hex(), self.root_id.hex()]
            needles.extend(record.locator_text for record in project.records)
            for needle in needles:
                self.assertNotIn(needle, text)

    def test_frontend_tamper_is_rejected_before_interpreter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            payload = bytearray(project.graph_secret)
            payload[-1] ^= 1
            forged = replace(project, graph_secret=bytes(payload))
            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after decision metadata tamper"),
                ) as execute:
                    with self.assertRaises(ObjectSpaceDecisionRealityError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def test_schema_downgrade_to_value_frontend_never_reinterprets_decision_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            payload = bytearray(project.graph_secret)
            self.assertEqual(bytes(payload[:16]), DECISION_GRAPH_MAGIC_V1)
            payload[:16] = VALUE_DOMAIN_GRAPH_MAGIC_V1
            forged = replace(project, graph_secret=bytes(payload))
            with object_space_check_session(self.opener(handle, project_override=forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after decision schema downgrade"),
                ) as execute:
                    with self.assertRaises(ObjectSpaceValueDomainError):
                        cli.command_run(str(root))
                    execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()

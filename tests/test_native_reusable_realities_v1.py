from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_reusable_realities_v1 import (
    NATIVE_REUSABLE_OBJECT_FRONTEND_V1,
    NativeReusableRealizationSpecV1,
    check_native_reusable_object_space,
    decode_native_reusable_graph,
    encode_native_reusable_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeReusableRealitiesV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("b1" * 16)
        self.root_id = bytes.fromhex("b2" * 16)
        self.reusable_id = bytes.fromhex("b3" * 16)
        self.realization_a = bytes.fromhex("b4" * 16)
        self.realization_b = bytes.fromhex("b5" * 16)
        self.root_source = (
            b"witness first conduit 0\n"
            b"witness second conduit 1\n"
            b"witness total sum first second\n"
            b"resolve total\n"
        )
        self.reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.reusable_id: self.reusable_source,
        }

    def _secret(self) -> bytes:
        return encode_native_reusable_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            current_epoch=1,
            realizations=(
                NativeReusableRealizationSpecV1(
                    realization_id=self.realization_a,
                    root_slot=0,
                    reusable_object_id=self.reusable_id,
                    inputs=(40, 2),
                    issued_epoch=1,
                    expires_epoch=2,
                ),
                NativeReusableRealizationSpecV1(
                    realization_id=self.realization_b,
                    root_slot=1,
                    reusable_object_id=self.reusable_id,
                    inputs=(10, 5),
                    issued_epoch=1,
                    expires_epoch=2,
                ),
            ),
        )

    def _create(self, root: Path):
        secret = self._secret()
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects,
            root_object_id=self.root_id,
            graph_secret=secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id,
        )

    def _opener(self, handle: bytes):
        def open_project(path: Path):
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

    def test_same_canonical_reality_is_realized_twice_without_source_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, _ = self._create(root)
            checked = decode_native_reusable_graph(project)

            self.assertEqual(len(project.object_payloads), 2)
            self.assertEqual(len(checked.reusable_objects), 1)
            self.assertEqual(len(checked.realizations), 2)
            self.assertEqual(
                {record.reusable_object_id for record in checked.realizations},
                {self.reusable_id},
            )
            self.assertEqual(checked.realized[self.realization_a].value, 42)
            self.assertEqual(checked.realized[self.realization_b].value, 15)
            self.assertEqual(checked.root.value, 57)
            self.assertEqual(
                {record.reusable_frontend_id for record in checked.realizations},
                {NATIVE_REUSABLE_OBJECT_FRONTEND_V1},
            )

    def test_object_space_backend_executes_reused_realizations_as_one_root_reality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self._create(root)
            graph, report = check_native_reusable_object_space(project)
            self.assertIsNotNone(graph.mir)
            self.assertEqual(report.functions, 1)

            with object_space_check_session(self._opener(handle)):
                _, routed = commands._checked(str(root))
                mir_graph = require_mir(routed)
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
                self.assertEqual(runtime_value, 57)
                self.assertEqual(cli.command_run(str(root)), 0)

    def test_reusable_source_has_no_function_call_parameter_or_template_surface(self) -> None:
        text = self.reusable_source.decode("ascii")
        for borrowed in ("fn", "function", "call", "parameter", "template", "class", "lambda"):
            self.assertNotIn(borrowed, text.split())


if __name__ == "__main__":
    unittest.main()

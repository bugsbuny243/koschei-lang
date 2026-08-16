from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_relationship_v1 import (
    NativeRelationshipSpecV1,
    encode_native_relationship_graph_secret,
)
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeRelationshipExecutionV1Tests(unittest.TestCase):
    def test_real_object_space_run_executes_composed_relationship_value(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("c1" * 16)
        root_id = bytes.fromhex("c2" * 16)
        target_id = bytes.fromhex("c3" * 16)
        relation_id = bytes.fromhex("c4" * 16)
        objects = {
            root_id: (
                b"witness remote conduit 0\n"
                b"witness fee 2\n"
                b"witness total sum remote fee\n"
                b"resolve total\n"
            ),
            target_id: (
                b"witness base 20\n"
                b"witness doubled product base 2\n"
                b"resolve doubled\n"
            ),
        }
        secret = encode_native_relationship_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
            current_epoch=1,
            relationships=(
                NativeRelationshipSpecV1(
                    relation_id=relation_id,
                    slot=0,
                    target_object_id=target_id,
                    issued_epoch=1,
                    expires_epoch=2,
                    max_target_witnesses=2,
                    max_abs_value=40,
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = create_object_space_project(
                root,
                provider=provider,
                temporal_key=temporal_key,
                objects=objects,
                root_object_id=root_id,
                graph_secret=secret,
                temporal_policy=policy,
                now=now,
                project_id=project_id,
            )

            def opener(path: Path):
                return load_object_space_project(
                    path,
                    provider=provider,
                    temporal_key=temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project.project_id,
                    expected_epoch=1,
                    temporal_policy=policy,
                    now=now,
                )

            with object_space_check_session(opener):
                # Use the exact graph that the installed Object Space command route
                # admits.  Execute its sealed MIR root directly to prove the native
                # relationship's observable program value, rather than confusing
                # that value with the CLI's process-style success status.
                _, graph = commands._checked(str(root))
                mir_graph = require_mir(graph)
                mir_graph.assert_sealed()
                mir_root = mir_graph.root_module
                value = Interpreter(
                    mir_root.program,
                    [],
                    mir_graph.namespaces(),
                    dict(mir_root.imports),
                    mir_graph.enums(),
                    mir_graph.module_imports(),
                    mir_graph.structs(),
                ).execute_main()
                self.assertEqual(value, 42)

                # Public `run` deliberately maps any non-error program result to a
                # process success code.  Preserve and test that established CLI ABI.
                self.assertEqual(cli.command_run(str(root)), 0)


if __name__ == "__main__":
    unittest.main()

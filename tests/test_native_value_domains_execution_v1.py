from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from koschei import cli
from koschei.interpreter import Interpreter
from koschei.mir import require_mir
from koschei.native_value_domains_v1 import check_native_value_domains
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_value_domains_v1 import encode_native_value_domain_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


def execute_lowered(source: str):
    checked = check_native_value_domains(source)
    value = Interpreter(checked.lowered, []).execute_main()
    return checked, value


class NativeValueDomainsExecutionV1Tests(unittest.TestCase):
    def test_whole_truth_and_glyphs_match_backend_execution(self) -> None:
        whole, whole_runtime = execute_lowered(
            "witness base 40\n"
            "witness fee 2\n"
            "witness answer sum base fee\n"
            "resolve answer\n"
        )
        self.assertEqual(whole.value.value, 42)
        self.assertEqual(whole_runtime, whole.value.value)

        truth, truth_runtime = execute_lowered(
            "witness left 42\n"
            "witness right 42\n"
            "witness equal same left right\n"
            "resolve equal\n"
        )
        self.assertIs(truth.value.value, True)
        self.assertIs(truth_runtime, truth.value.value)

        glyphs, glyph_runtime = execute_lowered(
            "witness base glyphs 1 e\n"
            "witness mark glyphs 2 \u0301\n"
            "witness joined merge base mark\n"
            "resolve joined\n"
        )
        self.assertEqual(glyphs.value.value, "é")
        self.assertEqual(glyph_runtime, glyphs.value.value)

    def test_canonical_merge_is_semantically_equal_to_canonical_literal(self) -> None:
        checked, runtime = execute_lowered(
            "witness base glyphs 1 e\n"
            "witness mark glyphs 2 \u0301\n"
            "witness joined merge base mark\n"
            "witness canonical glyphs 2 é\n"
            "witness equal same joined canonical\n"
            "resolve equal\n"
        )
        self.assertIs(checked.value.value, True)
        self.assertIs(runtime, True)

    def test_real_object_space_run_executes_native_value_domain_graph(self) -> None:
        provider = TestOnlyProvider()
        temporal_key = bytes(range(1, 65))
        policy = TemporalAccessPolicy(period_seconds=30)
        now = 1_800_000_000
        project_id = bytes.fromhex("d1" * 16)
        root_id = bytes.fromhex("d2" * 16)
        source = (
            "witness base glyphs 1 e\n"
            "witness mark glyphs 2 \u0301\n"
            "witness joined merge base mark\n"
            "resolve joined\n"
        ).encode("utf-8")
        objects = {root_id: source}
        secret = encode_native_value_domain_graph_secret(
            project_id=project_id,
            root_object_id=root_id,
            objects=objects,
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
                self.assertEqual(runtime_value, "é")
                self.assertEqual(cli.command_run(str(root)), 0)


if __name__ == "__main__":
    unittest.main()

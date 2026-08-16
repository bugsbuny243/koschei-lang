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
from koschei.native_cell_reuse_composition_v1 import (
    NativeCellReuseCompositionError,
    _BINDING,
    _HEADER,
    _OBJECT,
    decode_native_cell_reuse_composition_graph,
    encode_native_cell_reuse_composition_graph_secret,
)
from koschei.native_cell_realities_v1 import _CELL
import koschei.object_space_commands_v1 as commands
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class NativeCellReuseCompositionAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("71" * 16)
        self.root_id = bytes.fromhex("72" * 16)
        self.cell_id = bytes.fromhex("73" * 16)
        self.reusable_id = bytes.fromhex("74" * 16)
        self.schema_id = bytes.fromhex("75" * 16)
        self.realization_id = bytes.fromhex("76" * 16)
        self.root_source = b"witness value conduit 0\nresolve value\n"
        self.cell_source = (
            b"witness amount 40\n"
            b"witness fee 2\n"
            b"witness approved truth yes\n"
            b"resolve approved\n"
            b"resolve fee\n"
            b"resolve amount\n"
        )
        self.reusable_source = (
            b"witness left conduit 0\n"
            b"witness right conduit 1\n"
            b"witness total sum left right\n"
            b"resolve total\n"
        )
        self.objects = {
            self.root_id: self.root_source,
            self.cell_id: self.cell_source,
            self.reusable_id: self.reusable_source,
        }
        self.secret = encode_native_cell_reuse_composition_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            cell_object_id=self.cell_id,
            reusable_object_id=self.reusable_id,
            objects=self.objects,
            schema_id=self.schema_id,
            cell_witnesses=("amount", "fee", "approved"),
            input_cell_ordinals=(0, 1),
            root_slot=0,
            realization_id=self.realization_id,
            current_epoch=1,
            issued_epoch=1,
            expires_epoch=2,
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

    def opener(self, root: Path, project, handle):
        return load_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            temporal_handle=handle,
            expected_project_id=self.project_id,
            expected_epoch=1,
            temporal_policy=self.policy,
            now=self.now,
        )

    def test_truth_cell_cannot_enter_whole_reusable_input(self) -> None:
        with self.assertRaisesRegex(NativeCellReuseCompositionError, "requires whole"):
            encode_native_cell_reuse_composition_graph_secret(
                project_id=self.project_id,
                root_object_id=self.root_id,
                cell_object_id=self.cell_id,
                reusable_object_id=self.reusable_id,
                objects=self.objects,
                schema_id=self.schema_id,
                cell_witnesses=("amount", "fee", "approved"),
                input_cell_ordinals=(0, 2),
                root_slot=0,
                realization_id=self.realization_id,
                current_epoch=1,
                issued_epoch=1,
                expires_epoch=2,
            )

    def test_unselected_cell_domain_tamper_breaks_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            forged_bytes = bytearray(loaded.graph_secret)
            cell_table = _HEADER.size + 3 * _OBJECT.size
            forged_bytes[cell_table + 2 * _CELL.size + 36] = 1
            forged = replace(loaded, graph_secret=bytes(forged_bytes))
            with self.assertRaisesRegex(NativeCellReuseCompositionError, "full cell schema"):
                decode_native_cell_reuse_composition_graph(forged)

    def test_binding_tamper_to_truth_cell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            forged_bytes = bytearray(loaded.graph_secret)
            binding_table = _HEADER.size + 3 * _OBJECT.size + 3 * _CELL.size
            forged_bytes[binding_table + _BINDING.size + 2] = 0
            forged_bytes[binding_table + _BINDING.size + 3] = 2
            forged = replace(loaded, graph_secret=bytes(forged_bytes))
            with self.assertRaisesRegex(NativeCellReuseCompositionError, "sealed whole cell"):
                decode_native_cell_reuse_composition_graph(forged)

    def test_authority_inflation_fails_before_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            fields = list(_HEADER.unpack_from(loaded.graph_secret, 0))
            fields[-2] = 1
            forged = replace(
                loaded,
                graph_secret=_HEADER.pack(*fields) + loaded.graph_secret[_HEADER.size:],
            )

            def open_project(path: Path):
                return forged

            with object_space_check_session(open_project):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after composition authority inflation"),
                ) as execute:
                    with self.assertRaises(NativeCellReuseCompositionError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def test_cross_project_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            loaded = self.opener(root, project, handle)
            with self.assertRaisesRegex(NativeCellReuseCompositionError, "project/root"):
                decode_native_cell_reuse_composition_graph(
                    replace(loaded, project_id=bytes.fromhex("99" * 16))
                )

    def test_public_surfaces_hide_composition_storage_and_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "space"
            project, handle = self.create(root)
            output = io.StringIO()

            def open_for_session(path: Path):
                return self.opener(path, project, handle)

            with object_space_check_session(open_for_session):
                checked_project, graph = commands._checked(str(root))
                mir_text = repr(commands._public_mir_payload(graph, checked_project))
                go_source = commands._object_space_go_source(str(root))[1]
                main_start = go_source.rfind("func main()")
                self.assertGreaterEqual(main_start, 0)
                app_go = go_source[main_start:]
                with redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(cli.command_caps(str(root), True, None), 0)
                    self.assertEqual(cli.command_run(str(root)), 0)

            needles = [
                self.project_id.hex(),
                self.root_id.hex(),
                self.cell_id.hex(),
                self.reusable_id.hex(),
                self.schema_id.hex(),
                self.realization_id.hex(),
                "amount",
                "fee",
                "approved",
                "left",
                "right",
                "total",
            ]
            needles.extend(record.locator_text for record in project.records)
            for text in (mir_text, app_go, output.getvalue()):
                for needle in needles:
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()

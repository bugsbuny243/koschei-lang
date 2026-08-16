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
from tests.test_native_cell_reuse_composition_v1 import NativeCellReuseCompositionV1Tests


class NativeCellReuseCompositionAdversarialV1Tests(NativeCellReuseCompositionV1Tests):
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
            # Ordinal 2 is not bound to the reusable reality. Change truth -> whole.
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
            # Second reusable input originally points at whole cell 1. Redirect to truth cell 2.
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
            with object_space_check_session(self._opener_override(handle, forged)):
                with patch.object(
                    Interpreter,
                    "execute_main",
                    side_effect=AssertionError("interpreter reached after composition authority inflation"),
                ) as execute:
                    with self.assertRaises(NativeCellReuseCompositionError):
                        cli.command_run(str(root))
                    execute.assert_not_called()

    def _opener_override(self, handle: bytes, forged):
        def open_project(path: Path):
            return forged
        return open_project

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

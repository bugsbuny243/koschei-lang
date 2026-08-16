from __future__ import annotations

import io
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from koschei.cli import main
from koschei import object_space_check_v1 as checkmod
from koschei.object_space_check_v1 import object_space_check_session
from koschei.object_space_graph_v1 import encode_object_space_graph_secret
from koschei.object_space_v1 import create_object_space_project, load_object_space_project
from koschei.temporal_access_v1 import TemporalAccessPolicy
from tests.test_object_space_adversarial_v1 import TestOnlyProvider


class ObjectSpaceCheckAdversarialV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = TestOnlyProvider()
        self.temporal_key = bytes(range(1, 65))
        self.policy = TemporalAccessPolicy(period_seconds=30)
        self.now = 1_800_000_000
        self.project_id = bytes.fromhex("aa" * 16)
        self.root_id = bytes.fromhex("11" * 16)
        self.lib_id = bytes.fromhex("22" * 16)
        self.objects = {
            self.root_id: b"import lib\nfn main() { let x = lib.f() }\n",
            self.lib_id: b"fn f() -> Int { return 7 }\n",
        }
        self.secret = encode_object_space_graph_secret(
            project_id=self.project_id,
            root_object_id=self.root_id,
            objects=self.objects,
            target_by_import_slot={self.root_id: (self.lib_id,)},
        )

    def create(self, root: Path, *, objects=None, root_id=None, secret=None, project_id=None):
        return create_object_space_project(
            root,
            provider=self.provider,
            temporal_key=self.temporal_key,
            objects=self.objects if objects is None else objects,
            root_object_id=self.root_id if root_id is None else root_id,
            graph_secret=self.secret if secret is None else secret,
            temporal_policy=self.policy,
            now=self.now,
            project_id=self.project_id if project_id is None else project_id,
        )

    def opener(self, handle, *, project_id=None, epoch=1):
        expected_project = self.project_id if project_id is None else project_id

        def open_project(root: Path):
            return load_object_space_project(
                root,
                provider=self.provider,
                temporal_key=self.temporal_key,
                temporal_handle=handle,
                expected_project_id=expected_project,
                expected_epoch=epoch,
                temporal_policy=self.policy,
                now=self.now,
            )

        return open_project

    def invoke(self, argv: list[str]):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_partial_object_space_cannot_fall_back_to_legacy_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "partial"
            root.mkdir(mode=0o700)
            (root / "k0").write_bytes(b"malformed")
            with patch.object(
                checkmod,
                "_ORIGINAL_COMMAND_CHECK",
                side_effect=AssertionError("legacy check fallback reached"),
            ):
                code, out, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("trusted session broker", err)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlink support unavailable")
    def test_symlink_to_object_space_cannot_fall_back_to_legacy_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real = base / "real"
            alias = base / "alias"
            self.create(real)
            alias.symlink_to(real, target_is_directory=True)
            with patch.object(
                checkmod,
                "_ORIGINAL_COMMAND_CHECK",
                side_effect=AssertionError("symlink Object Space fell into legacy resolver"),
            ):
                code, out, err = self.invoke(["check", str(alias)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("trusted session broker", err)

    def test_scoped_broker_authority_is_not_inherited_by_new_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            _, handle = self.create(root)
            result: list[tuple[int, str, str]] = []

            def worker() -> None:
                result.append(self.invoke(["check", str(root)]))

            with object_space_check_session(self.opener(handle)):
                thread = threading.Thread(target=worker)
                thread.start()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
                main_code, _, main_err = self.invoke(["check", str(root)])
                self.assertEqual(main_code, 0, main_err)

            self.assertEqual(len(result), 1)
            code, out, err = result[0]
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("trusted session broker", err)

    def test_broker_noncanonical_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            self.create(root)
            with object_space_check_session(lambda _root: object()):
                code, out, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("non-canonical project value", err)

    def test_semantic_failure_does_not_leak_object_identity_or_physical_locator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            project_id = bytes.fromhex("cc" * 16)
            root_id = bytes.fromhex("44" * 16)
            objects = {root_id: b"fn main() { let x = missing_name }\n"}
            secret = encode_object_space_graph_secret(
                project_id=project_id,
                root_object_id=root_id,
                objects=objects,
                target_by_import_slot={},
            )
            project, handle = self.create(
                root,
                objects=objects,
                root_id=root_id,
                secret=secret,
                project_id=project_id,
            )

            def opener(requested: Path):
                return load_object_space_project(
                    requested,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle,
                    expected_project_id=project_id,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )

            with object_space_check_session(opener):
                code, out, err = self.invoke(["check", str(root)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("KS1101", err)
            self.assertNotIn(root_id.hex(), err)
            self.assertNotIn(project_id.hex(), err)
            for record in project.records:
                self.assertNotIn(record.locator_text, err)
            self.assertNotIn("k1/", err)

    def test_nested_session_restores_outer_authority_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root_a = base / "a"
            root_b = base / "b"
            project_a, handle_a = self.create(root_a)

            project_id_b = bytes.fromhex("dd" * 16)
            root_id_b = bytes.fromhex("55" * 16)
            objects_b = {root_id_b: b"fn main() { return }\n"}
            secret_b = encode_object_space_graph_secret(
                project_id=project_id_b,
                root_object_id=root_id_b,
                objects=objects_b,
                target_by_import_slot={},
            )
            project_b, handle_b = self.create(
                root_b,
                objects=objects_b,
                root_id=root_id_b,
                secret=secret_b,
                project_id=project_id_b,
            )

            outer = self.opener(handle_a)

            def inner(requested: Path):
                return load_object_space_project(
                    requested,
                    provider=self.provider,
                    temporal_key=self.temporal_key,
                    temporal_handle=handle_b,
                    expected_project_id=project_id_b,
                    expected_epoch=1,
                    temporal_policy=self.policy,
                    now=self.now,
                )

            with object_space_check_session(outer):
                code, _, err = self.invoke(["check", str(root_a)])
                self.assertEqual(code, 0, err)
                with object_space_check_session(inner):
                    code, _, err = self.invoke(["check", str(root_b)])
                    self.assertEqual(code, 0, err)
                code, _, err = self.invoke(["check", str(root_a)])
                self.assertEqual(code, 0, err)

            self.assertEqual(project_a.root, root_a.absolute())
            self.assertEqual(project_b.root, root_b.absolute())


if __name__ == "__main__":
    unittest.main()

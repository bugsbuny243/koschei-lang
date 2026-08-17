from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from koschei.bounded_persistence_v1 import PersistenceRuntimeError
from koschei.codegen_go import CodegenError, generate_go
from koschei.parser import parse
from koschei.semantic import SemanticError, check
from koschei.stdlib_catalog import CATALOG, validate_catalog


class BoundedPersistenceV1Tests(unittest.TestCase):
    def test_exact_object_commit_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                'let wrote = state.commit("hello") or return '
                'let loaded = state.load() or "" '
                "println(loaded) "
                "}"
            )
            check(program)

    def test_payload_budget_rejects_before_mutating_old_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            from koschei.bounded_persistence_v1 import PersistCaps
            token = PersistCaps(str(target), 3, 2000)
            with self.assertRaisesRegex(PersistenceRuntimeError, "KS3421"):
                token.commit("four")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_load_budget_and_utf8_are_fail_closed(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_bytes(b"abcd")
            token = PersistCaps(str(target), 3, 2000)
            with self.assertRaisesRegex(PersistenceRuntimeError, "KS3421"):
                token.load()
            target.write_bytes(b"\xff")
            token = PersistCaps(str(target), 3, 2000)
            with self.assertRaisesRegex(PersistenceRuntimeError, "KS3420"):
                token.load()

    def test_pre_replace_fsync_failure_keeps_old_state_and_cleans_temp(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = PersistCaps(str(target), 4096, 2000)
            real_fsync = os.fsync
            calls = 0
            def fail_first(fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("simulated fsync failure")
                real_fsync(fd)
            with mock.patch("os.fsync", side_effect=fail_first):
                with self.assertRaises(PersistenceRuntimeError):
                    token.commit("new")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertFalse(any(p.name.startswith(".state.txt.") for p in target.parent.iterdir()))

    def test_post_replace_directory_fsync_failure_is_state_uncertain_not_rollback(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = PersistCaps(str(target), 4096, 2000)
            real_fsync = os.fsync
            calls = 0
            def fail_second(fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated directory fsync failure")
                real_fsync(fd)
            with mock.patch("os.fsync", side_effect=fail_second):
                with self.assertRaisesRegex(PersistenceRuntimeError, "KS3423"):
                    token.commit("new")
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_parent_descriptor_anchor_survives_path_replacement(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trusted = root / "trusted"
            trusted.mkdir()
            target = trusted / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = PersistCaps(str(target), 4096, 2000)
            moved = root / "trusted-old"
            trusted.rename(moved)
            trusted.mkdir()
            (trusted / "state.txt").write_text("attacker", encoding="utf-8")
            token.commit("new")
            self.assertEqual((moved / "state.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual((trusted / "state.txt").read_text(encoding="utf-8"), "attacker")

    def test_symlink_parent_component_is_never_followed(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(PersistenceRuntimeError):
                PersistCaps(str(link / "state.txt"), 4096, 2000)

    def test_symlink_target_is_rejected_without_touching_external_file(self) -> None:
        from koschei.bounded_persistence_v1 import PersistCaps
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / "external.txt"
            external.write_text("external", encoding="utf-8")
            target = root / "state.txt"
            target.symlink_to(external)
            token = PersistCaps(str(target), 4096, 2000)
            with self.assertRaises(PersistenceRuntimeError):
                token.commit("new")
            self.assertEqual(external.read_text(encoding="utf-8"), "external")

    def test_static_exact_policy_and_manifest_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "state.txt")
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                "}"
            )
            check(program)

    def test_dynamic_or_relative_persistence_authority_is_rejected(self) -> None:
        dynamic = parse(
            'fn main(caps: SystemCaps) { let p = "/tmp/state" let state = caps.persist.allow(p, 4096, 2000) }'
        )
        with self.assertRaisesRegex(SemanticError, "KS2420"):
            check(dynamic)
        relative = parse(
            'fn main(caps: SystemCaps) { let state = caps.persist.allow("relative/state", 4096, 2000) }'
        )
        with self.assertRaisesRegex(SemanticError, "KS2421"):
            check(relative)

    def test_persist_capability_cannot_be_laundered_through_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "state.txt")
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                "let hidden = [state] "
                "}"
            )
            with self.assertRaisesRegex(SemanticError, "KS2401"):
                check(program)

    def test_load_and_commit_are_fallible_language_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "state.txt")
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                'let wrote = state.commit("hello") or return '
                'let loaded = state.load() or "" '
                "println(loaded) "
                "}"
            )
            check(program)

    def test_native_codegen_remains_explicitly_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "state.txt")
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                'let wrote = state.commit("hello") or return '
                "}"
            )
            check(program)
            with self.assertRaises(CodegenError) as context:
                generate_go(program)
            self.assertEqual(context.exception.code, "KS4001")

    def test_stdlib_catalog_keeps_persistence_reserved(self) -> None:
        validate_catalog(CATALOG)


if __name__ == "__main__":
    unittest.main()

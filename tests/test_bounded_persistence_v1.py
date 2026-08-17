from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from koschei.capabilities import analyze
from koschei.codegen_go import CodegenError, generate_go
from koschei.interpreter import KsError, KsUnit, PersistCaps, SystemCaps
from koschei.parser import parse
from koschei.semantic import SemanticError, check
from koschei.stdlib_catalog import CATALOG, validate_catalog


class BoundedPersistenceV1Tests(unittest.TestCase):
    def token(self, target: Path, *, max_bytes: int = 4096, deadline_ms: int = 5000) -> PersistCaps:
        value = SystemCaps().persist.allow(str(target), max_bytes, deadline_ms)
        self.assertIsInstance(value, PersistCaps)
        return value

    def test_exact_object_commit_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.json"
            token = self.token(target)
            self.assertIs(token.commit('{"version":1}'), KsUnit)
            self.assertEqual(token.load(), '{"version":1}')
            self.assertEqual(target.read_text(encoding="utf-8"), '{"version":1}')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_parent_descriptor_anchor_survives_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trusted = root / "state-dir"
            trusted.mkdir()
            target = trusted / "state.txt"
            target.write_text("old", encoding="utf-8")

            token = self.token(target)

            moved = root / "trusted-moved"
            trusted.rename(moved)
            trusted.mkdir()
            attacker_target = trusted / "state.txt"
            attacker_target.write_text("attacker", encoding="utf-8")

            self.assertIs(token.commit("sealed"), KsUnit)
            self.assertEqual((moved / "state.txt").read_text(encoding="utf-8"), "sealed")
            self.assertEqual(attacker_target.read_text(encoding="utf-8"), "attacker")
            self.assertEqual(token.load(), "sealed")

    def test_symlink_parent_component_is_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")

            token = self.token(link / "state.txt")
            result = token.commit("blocked")
            self.assertIsInstance(result, KsError)
            self.assertIn("KS3424", result.message)
            self.assertFalse((real / "state.txt").exists())

    def test_symlink_target_is_rejected_without_touching_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            target = root / "state.txt"
            try:
                target.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable")

            token = self.token(target)
            result = token.commit("blocked")
            self.assertIsInstance(result, KsError)
            self.assertIn("KS3420", result.message)
            self.assertEqual(outside.read_text(encoding="utf-8"), "secret")
            self.assertTrue(target.is_symlink())

    def test_payload_budget_rejects_before_mutating_old_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = self.token(target, max_bytes=4)

            result = token.commit("12345")
            self.assertIsInstance(result, KsError)
            self.assertIn("KS3421", result.message)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(
                [item.name for item in target.parent.iterdir() if item.name.startswith(".koschei-persist-")],
                [],
            )

    def test_load_budget_and_utf8_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.bin"
            target.write_bytes(b"12345")
            token = self.token(target, max_bytes=4)
            oversized = token.load()
            self.assertIsInstance(oversized, KsError)
            self.assertIn("KS3421", oversized.message)

            target.write_bytes(b"\xff")
            token2 = self.token(target, max_bytes=4)
            invalid = token2.load()
            self.assertIsInstance(invalid, KsError)
            self.assertIn("KS3420", invalid.message)

    def test_pre_replace_fsync_failure_keeps_old_state_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = self.token(target)

            with patch(
                "koschei.bounded_persistence_v1.os.fsync",
                side_effect=OSError("injected temp fsync failure"),
            ):
                result = token.commit("new")

            self.assertIsInstance(result, KsError)
            self.assertIn("KS3424", result.message)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(
                [item.name for item in target.parent.iterdir() if item.name.startswith(".koschei-persist-")],
                [],
            )

    def test_post_replace_directory_fsync_failure_is_state_uncertain_not_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.txt"
            target.write_text("old", encoding="utf-8")
            token = self.token(target)
            calls = 0

            def fsync_side_effect(_fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected directory fsync failure")

            with patch(
                "koschei.bounded_persistence_v1.os.fsync",
                side_effect=fsync_side_effect,
            ):
                result = token.commit("new")

            self.assertIsInstance(result, KsError)
            self.assertIn("KS3423", result.message)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_static_exact_policy_and_manifest_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "state.txt")
            program = parse(
                "fn main(caps: SystemCaps) { "
                f'let state = caps.persist.allow("{target}", 4096, 2000) '
                "}"
            )
            check(program)
            manifest = analyze(program)
            persist = [grant for grant in manifest.grants if grant.domain == "persist"]
            self.assertEqual(len(persist), 1)
            self.assertIn(target, persist[0].scope)
            self.assertIn("bytes=4096", persist[0].scope)
            self.assertIn("deadline_ms=2000", persist[0].scope)

    def test_dynamic_or_relative_persistence_authority_is_rejected(self) -> None:
        dynamic = parse(
            "fn main(caps: SystemCaps) { "
            'let path = "/tmp/state.txt" '
            "let state = caps.persist.allow(path, 4096, 2000) "
            "}"
        )
        with self.assertRaisesRegex(SemanticError, "KS2420"):
            check(dynamic)

        relative = parse(
            "fn main(caps: SystemCaps) { "
            'let state = caps.persist.allow("state.txt", 4096, 2000) '
            "}"
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
                'let loaded = state.load() or return '
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
        family = next(item for item in CATALOG if item.name == "persist")
        self.assertEqual(family.status, "partial")
        by_name = {operation.name: operation for operation in family.operations}
        self.assertEqual(set(by_name), {"allow", "load", "commit"})
        self.assertTrue(all(operation.status == "reserved" for operation in by_name.values()))
        self.assertTrue(all(not operation.interpreter for operation in by_name.values()))
        self.assertTrue(all(not operation.native_go for operation in by_name.values()))
        self.assertEqual(by_name["commit"].enforced_budgets, ("bytes",))


if __name__ == "__main__":
    unittest.main()

"""Strange v1 makes native *symbols* deployment-specific, not authority."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from koschei.mir import require_mir
from koschei.mir_go_native import generate_go_mir_native, inspect_mir_go_support
from koschei.modules import check_graph, load_graph
from koschei.strange_build_representation_v1 import (
    StrangeBuildRepresentationError,
    derive_strange_symbol,
)


ROOT = Path(__file__).resolve().parents[1]
GO = shutil.which("go")


class StrangeBuildRepresentationV1Tests(unittest.TestCase):
    def test_seeded_names_are_go_safe_stable_and_domain_separated(self) -> None:
        seed = b"a" * 32
        first = derive_strange_symbol(seed=seed, role="function", identity="m\x00f")
        self.assertEqual(first, derive_strange_symbol(seed=seed, role="function", identity="m\x00f"))
        self.assertRegex(first, r"^_k_[a-z2-7]{32}$")
        self.assertNotEqual(first, derive_strange_symbol(seed=b"b" * 32, role="function", identity="m\x00f"))
        self.assertNotEqual(first, derive_strange_symbol(seed=seed, role="parameter", identity="m\x00f"))
        self.assertNotEqual(first, derive_strange_symbol(seed=seed, role="function", identity="m\x00g"))

    def test_invalid_seed_role_and_identity_fail_closed(self) -> None:
        for seed in (b"short", b"", "not-bytes"):
            with self.subTest(seed=seed):
                with self.assertRaises(StrangeBuildRepresentationError):
                    derive_strange_symbol(seed=seed, role="function", identity="m")
        with self.assertRaises(StrangeBuildRepresentationError):
            derive_strange_symbol(seed=b"a" * 32, role="unknown", identity="m")
        with self.assertRaises(StrangeBuildRepresentationError):
            derive_strange_symbol(seed=b"a" * 32, role="function", identity="")

    def checked_mir(self):
        graph = load_graph(ROOT / "examples" / "hello.ks")
        check_graph(graph)
        mir = require_mir(graph)
        self.assertTrue(inspect_mir_go_support(mir).supported)
        return mir

    def test_seeded_projection_changes_names_not_canonical_mir(self) -> None:
        mir = self.checked_mir()
        fingerprint = mir.fingerprint
        plain_before = generate_go_mir_native(mir)
        seeded_a = generate_go_mir_native(mir, representation_seed=b"a" * 32)
        seeded_a_again = generate_go_mir_native(mir, representation_seed=b"a" * 32)
        seeded_b = generate_go_mir_native(mir, representation_seed=b"b" * 32)
        self.assertEqual(plain_before, generate_go_mir_native(mir))
        self.assertEqual(seeded_a, seeded_a_again)
        self.assertNotEqual(seeded_a, seeded_b)
        self.assertNotEqual(seeded_a, plain_before)
        self.assertIn("func _k_", seeded_a)
        self.assertNotIn("func _ks_fn_", seeded_a)
        self.assertEqual(mir.fingerprint, fingerprint)
        self.assertNotIn((b"a" * 32).hex(), seeded_a)
        with self.assertRaises(StrangeBuildRepresentationError):
            generate_go_mir_native(mir, representation_seed=b"short")

    @unittest.skipUnless(GO, "Go is required for native execution parity")
    def test_two_seeded_native_builds_run_like_unseeded(self) -> None:
        mir = self.checked_mir()
        with tempfile.TemporaryDirectory() as temporary:
            outputs = []
            for index, seed in enumerate((None, b"a" * 32, b"b" * 32)):
                go_file = Path(temporary) / f"program-{index}.go"
                binary = Path(temporary) / f"program-{index}"
                go_file.write_text(
                    generate_go_mir_native(mir, representation_seed=seed),
                    encoding="utf-8",
                )
                built = subprocess.run(
                    [GO, "build", "-trimpath", "-buildvcs=false",
                     "-ldflags=-buildid=", "-o", str(binary), str(go_file)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(built.returncode, 0, built.stderr)
                run = subprocess.run([str(binary)], capture_output=True, check=False)
                self.assertEqual(run.returncode, 0, run.stderr)
                outputs.append(run.stdout)
            self.assertEqual(outputs, [b"Koschei\n1\n"] * 3)


if __name__ == "__main__":
    unittest.main()

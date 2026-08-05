from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main


class NativeBuildManifestTests(unittest.TestCase):
    def _project(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        source = root / "main.ks"
        helper = root / "helper.ks"
        lockfile = root / "koschei.lock.json"
        source.write_text(
            "import helper\n\nfn main() {\n    return\n}\n",
            encoding="utf-8",
        )
        helper.write_text("fn value() {\n    return\n}\n", encoding="utf-8")
        self.assertEqual(
            main(["lock", "create", str(source), "--output", str(lockfile)]),
            0,
        )
        return source, helper, lockfile

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_locked_build_manifest_binds_lock_mir_toolchain_and_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile = self._project(directory)
            binary = Path(directory) / "app"
            manifest_path = Path(directory) / "app.build.json"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--locked",
                        "--lockfile",
                        str(lockfile),
                        "--output",
                        str(binary),
                        "--build-manifest",
                        str(manifest_path),
                    ]
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            locked = json.loads(lockfile.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(manifest["schema_version"], "koschei.native-build-manifest.v1")
            self.assertEqual(manifest["module_lock_digest"], locked["lock_digest"])
            self.assertEqual(
                manifest["artifact_sha256"],
                hashlib.sha256(binary.read_bytes()).hexdigest(),
            )
            self.assertEqual(manifest["artifact_size"], binary.stat().st_size)
            self.assertEqual(manifest["backend"], "go-native")
            self.assertIn("go version", manifest["backend_toolchain"])
            self.assertTrue(manifest["mir_fingerprint"])
            self.assertEqual(len(manifest["manifest_digest"]), 64)
            self.assertIn("KOSCHEI BUILD MANIFEST", output.getvalue())

    def test_build_manifest_requires_locked_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "main.ks"
            source.write_text("fn main() {\n    return\n}\n", encoding="utf-8")
            error = io.StringIO()

            with redirect_stderr(error):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--build-manifest",
                        str(Path(directory) / "app.build.json"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("--build-manifest requires --locked", error.getvalue())

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_existing_manifest_blocks_before_native_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile = self._project(directory)
            binary = Path(directory) / "app"
            manifest_path = Path(directory) / "app.build.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            error = io.StringIO()

            with redirect_stderr(error):
                exit_code = main(
                    [
                        "build",
                        str(source),
                        "--locked",
                        "--lockfile",
                        str(lockfile),
                        "--output",
                        str(binary),
                        "--build-manifest",
                        str(manifest_path),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse(binary.exists())
            self.assertIn("KS1911", error.getvalue())

    @unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
    def test_source_drift_produces_neither_binary_nor_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, helper, lockfile = self._project(directory)
            binary = Path(directory) / "app"
            manifest_path = Path(directory) / "app.build.json"
            helper.write_text(helper.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            exit_code = main(
                [
                    "build",
                    str(source),
                    "--locked",
                    "--lockfile",
                    str(lockfile),
                    "--output",
                    str(binary),
                    "--build-manifest",
                    str(manifest_path),
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(binary.exists())
            self.assertFalse(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()

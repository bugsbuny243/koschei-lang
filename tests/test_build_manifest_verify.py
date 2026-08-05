from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main


@unittest.skipUnless(shutil.which("go"), "Go is required for native build tests")
class NativeBuildManifestVerifyTests(unittest.TestCase):
    def _built_project(self, directory: str) -> tuple[Path, Path, Path, Path, Path]:
        root = Path(directory)
        source = root / "main.ks"
        helper = root / "helper.ks"
        lockfile = root / "koschei.lock.json"
        binary = root / "app"
        manifest = root / "app.build.json"
        source.write_text(
            "import helper\n\nfn main() {\n    return\n}\n",
            encoding="utf-8",
        )
        helper.write_text("fn value() {\n    return\n}\n", encoding="utf-8")
        self.assertEqual(
            main(["lock", "create", str(source), "--output", str(lockfile)]),
            0,
        )
        self.assertEqual(
            main(
                [
                    "build",
                    str(source),
                    "--locked",
                    "--lockfile",
                    str(lockfile),
                    "--output",
                    str(binary),
                    "--build-manifest",
                    str(manifest),
                ]
            ),
            0,
        )
        return source, helper, lockfile, binary, manifest

    def _verify(
        self,
        source: Path,
        lockfile: Path,
        binary: Path,
        manifest: Path,
    ) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            exit_code = main(
                [
                    "build-verify",
                    str(source),
                    "--artifact",
                    str(binary),
                    "--manifest",
                    str(manifest),
                    "--lockfile",
                    str(lockfile),
                ]
            )
        return exit_code, output.getvalue(), error.getvalue()

    def test_build_verify_rechecks_artifact_lock_and_mir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile, binary, manifest = self._built_project(directory)

            exit_code, output, error = self._verify(
                source,
                lockfile,
                binary,
                manifest,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(error, "")
            self.assertIn("KOSCHEI BUILD VERIFY: PASS", output)
            self.assertIn("ARTIFACT SHA256", output)
            self.assertIn("MANIFEST DIGEST", output)

    def test_artifact_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile, binary, manifest = self._built_project(directory)
            binary.write_bytes(binary.read_bytes() + b"tampered")

            exit_code, _, error = self._verify(source, lockfile, binary, manifest)

            self.assertEqual(exit_code, 1)
            self.assertIn("KS1913", error)
            self.assertIn("artifact", error.lower())

    def test_source_drift_is_rejected_by_the_original_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, helper, lockfile, binary, manifest = self._built_project(directory)
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )

            exit_code, _, error = self._verify(source, lockfile, binary, manifest)

            self.assertEqual(exit_code, 1)
            self.assertIn("KS1903", error)
            self.assertIn("helper.ks", error)

    def test_unknown_manifest_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, lockfile, binary, manifest = self._built_project(directory)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["production_approved"] = True
            manifest.write_text(json.dumps(payload), encoding="utf-8")

            exit_code, _, error = self._verify(source, lockfile, binary, manifest)

            self.assertEqual(exit_code, 1)
            self.assertIn("KS1912", error)
            self.assertIn("unsupported fields", error)


if __name__ == "__main__":
    unittest.main()

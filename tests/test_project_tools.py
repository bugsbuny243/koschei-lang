from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli import main
from koschei.project import ProjectError, create_project, load_project

REPO_ROOT = Path(__file__).resolve().parent.parent


class ProjectManifestTests(unittest.TestCase):
    def test_create_project_and_resolve_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = create_project("demo_app", Path(directory) / "demo")
            self.assertEqual(project.name, "demo_app")
            self.assertEqual(project.version, "0.1.0")
            self.assertEqual(project.entry.name, "main.ks")
            self.assertTrue(project.manifest.is_file())
            self.assertIn("Hello from demo_app", project.entry.read_text(encoding="utf-8"))

    def test_manifest_entry_cannot_escape_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            root.mkdir()
            (root / "koschei.toml").write_text(
                '[package]\nname = "demo"\nversion = "0.1.0"\nentry = "../outside.ks"\n',
                encoding="utf-8",
            )
            (Path(directory) / "outside.ks").write_text("fn main() {}\n", encoding="utf-8")
            with self.assertRaises(ProjectError):
                load_project(root)

    def test_manifest_requires_semver_and_package_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "main.ks").write_text("fn main() {}\n", encoding="utf-8")
            (root / "koschei.toml").write_text(
                '[package]\nname = "Bad Name"\nversion = "latest"\nentry = "src/main.ks"\n',
                encoding="utf-8",
            )
            with self.assertRaises(ProjectError):
                load_project(root)


class ProjectCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            exit_code = main(argv)
        return exit_code, output.getvalue(), error.getvalue()

    def test_new_check_run_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo"
            code, output, error = self.run_cli(
                ["new", "demo", "--path", str(target)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(error, "")
            self.assertIn("KOSCHEI NEW", output)

            code, output, error = self.run_cli(["check", str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(error, "")
            self.assertIn("KOSCHEI CHECK: PASS", output)

            code, output, error = self.run_cli(["run", str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(error, "")
            self.assertIn("Hello from demo", output)

        code, output, error = self.run_cli(["version", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(error, "")
        payload = json.loads(output)
        self.assertEqual(payload["version"], "0.9.0")

    def test_new_rejects_non_empty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            code, _, error = self.run_cli(
                ["new", "demo", "--path", str(target)]
            )
            self.assertEqual(code, 1)
            self.assertIn("Destination is not empty", error)


class VsCodeExtensionTests(unittest.TestCase):
    def test_extension_metadata_is_valid_json(self) -> None:
        paths = (
            REPO_ROOT / "editors" / "vscode" / "package.json",
            REPO_ROOT / "editors" / "vscode" / "language-configuration.json",
            REPO_ROOT
            / "editors"
            / "vscode"
            / "syntaxes"
            / "koschei.tmLanguage.json",
        )
        for path in paths:
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))

        package = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(package["contributes"]["languages"][0]["extensions"], [".ks"])
        self.assertEqual(package["version"], "0.9.0")

    def test_extension_uses_machine_readable_check_contract(self) -> None:
        extension = (
            REPO_ROOT / "editors" / "vscode" / "extension.js"
        ).read_text(encoding="utf-8")
        self.assertIn("check", extension)
        self.assertIn("--json", extension)
        self.assertIn("onDidSaveTextDocument", extension)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_extension_javascript_parses(self) -> None:
        completed = subprocess.run(
            ["node", "--check", "extension.js"],
            cwd=REPO_ROOT / "editors" / "vscode",
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()

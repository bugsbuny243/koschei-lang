from pathlib import Path
import tempfile
import unittest

from koschei.lang_project_boundary_v1 import (
    LangProjectBoundaryError,
    audit_lang_project_boundary_v1,
    require_lang_project_boundary_v1,
)


class LangProjectBoundaryV1Tests(unittest.TestCase):
    def _repo(self, root: Path, source: str = "import json\n", *, pyproject: str | None = None) -> Path:
        package = root / "koschei"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "sample.py").write_text(source, encoding="utf-8")
        if pyproject is None:
            pyproject = (
                '[build-system]\nrequires = []\n'
                '[project]\nname = "koschei-lang-test"\nversion = "0.0.0"\n'
                'dependencies = []\n'
            )
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        return root

    @staticmethod
    def _write(root: Path, relative: str, source: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def test_clean_lang_repository_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory), "import json\nfrom pathlib import Path\n")
            self._write(root, "tools/check.py", "import hashlib\n")
            self._write(root, "scripts/release.py", "import json\n")
            self._write(root, "bench/timing.py", "import time\n")
            self.assertEqual(audit_lang_project_boundary_v1(root), ())
            require_lang_project_boundary_v1(root)

    def test_direct_sentinel_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory), "import koschei_sentinel.runtime\n")
            violations = audit_lang_project_boundary_v1(root)
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0].kind, "import")
            with self.assertRaisesRegex(LangProjectBoundaryError, "independent from frozen Sentinel"):
                require_lang_project_boundary_v1(root)

    def test_from_sentinel_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory), "from koschei_sentinel import model\n")
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "import-from" for item in violations))

    def test_repository_wide_python_surfaces_are_scanned(self):
        for relative in ("tools/probe.py", "scripts/probe.py", "bench/probe.py", "probe.py"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = self._repo(Path(directory))
                self._write(root, relative, "import koschei_sentinel.runtime\n")
                violations = audit_lang_project_boundary_v1(root)
                self.assertTrue(any(item.path == relative for item in violations))

    def test_importlib_module_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                'import importlib as il\nplugin = il.import_module("koschei_sentinel.runtime")\n',
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dynamic-import" for item in violations))

    def test_import_module_function_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                'from importlib import import_module as load\nplugin = load("koschei_sentinel.runtime")\n',
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dynamic-import" for item in violations))

    def test_builtin_dynamic_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                'plugin = __import__("koschei_sentinel.runtime")\n',
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dynamic-import" for item in violations))

    def test_unrelated_import_module_method_is_not_false_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                'class Loader:\n    def import_module(self, name):\n        return name\nloader = Loader()\nvalue = loader.import_module("koschei_sentinel.runtime")\n',
            )
            self.assertEqual(audit_lang_project_boundary_v1(root), ())

    def test_excluded_generated_directories_do_not_define_repository_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory))
            self._write(root, "build/generated.py", "import koschei_sentinel.runtime\n")
            self._write(root, ".venv/lib/generated.py", "import koschei_sentinel.runtime\n")
            self.assertEqual(audit_lang_project_boundary_v1(root), ())

    def test_multiline_optional_sentinel_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                pyproject=(
                    '[build-system]\nrequires = []\n'
                    '[project]\nname = "koschei-lang-test"\nversion = "0.0.0"\n'
                    'dependencies = []\n'
                    '[project.optional-dependencies]\n'
                    'dev = [\n  "pytest",\n  "koschei-sentinel>=1",\n]\n'
                ),
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dependency" for item in violations))

    def test_build_system_sentinel_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                pyproject=(
                    '[build-system]\nrequires = ["koschei-sentinel-build>=1"]\n'
                    '[project]\nname = "koschei-lang-test"\nversion = "0.0.0"\n'
                    'dependencies = []\n'
                ),
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dependency" for item in violations))

    def test_unrelated_dependency_name_containing_letters_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                pyproject=(
                    '[build-system]\nrequires = []\n'
                    '[project]\nname = "koschei-lang-test"\nversion = "0.0.0"\n'
                    'dependencies = ["nonsentinel>=1"]\n'
                ),
            )
            self.assertEqual(audit_lang_project_boundary_v1(root), ())

    def test_current_repository_passes_boundary_check(self):
        repo_root = Path(__file__).resolve().parents[1]
        require_lang_project_boundary_v1(repo_root)


if __name__ == "__main__":
    unittest.main()

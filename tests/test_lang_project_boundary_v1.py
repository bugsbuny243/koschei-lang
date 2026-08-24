from pathlib import Path
import tempfile
import unittest

from koschei.lang_project_boundary_v1 import (
    LangProjectBoundaryError,
    audit_lang_project_boundary_v1,
    require_lang_project_boundary_v1,
)


class LangProjectBoundaryV1Tests(unittest.TestCase):
    def _repo(self, root: Path, source: str, *, dependencies: str = "") -> Path:
        package = root / "koschei"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "sample.py").write_text(source, encoding="utf-8")
        deps = f'\ndependencies = [{dependencies}]' if dependencies else "\ndependencies = []"
        (root / "pyproject.toml").write_text(
            '[project]\nname = "koschei-lang-test"\nversion = "0.0.0"' + deps + "\n",
            encoding="utf-8",
        )
        return root

    def test_clean_lang_package_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(Path(directory), "import json\nfrom pathlib import Path\n")
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

    def test_dynamic_sentinel_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                'import importlib\nplugin = importlib.import_module("koschei_sentinel.runtime")\n',
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dynamic-import" for item in violations))

    def test_sentinel_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(
                Path(directory),
                "import json\n",
                dependencies='"koschei-sentinel>=1"',
            )
            violations = audit_lang_project_boundary_v1(root)
            self.assertTrue(any(item.kind == "dependency" for item in violations))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import patch

import koschei
from koschei import data_native_source_v1 as native_source


class _Distribution:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    def locate_file(self, resource: pathlib.Path) -> pathlib.Path:
        return self.root / resource


class DataNativeSourceV1Tests(unittest.TestCase):
    def test_installed_distribution_source_is_used_without_checkout(self) -> None:
        checkout_source = native_source._source_path().read_text(encoding="utf-8")
        original_file = native_source.__file__
        with tempfile.TemporaryDirectory(prefix="koschei-wheel-source-") as workspace:
            root = pathlib.Path(workspace)
            installed = root / native_source._RESOURCE
            installed.parent.mkdir(parents=True)
            installed.write_text(checkout_source, encoding="utf-8")
            fake_module = root / "site-packages" / "koschei" / "data_native_source_v1.py"
            fake_module.parent.mkdir(parents=True)
            fake_module.write_text("", encoding="utf-8")
            try:
                native_source.__file__ = str(fake_module)
                with patch.object(
                    native_source,
                    "distribution",
                    return_value=_Distribution(root),
                ):
                    self.assertEqual(native_source._source_path(), installed)
                    self.assertIn("func ksDataParse", native_source._go_data_runtime())
            finally:
                native_source.__file__ = original_file

    def test_missing_installed_source_fails_closed(self) -> None:
        original_file = native_source.__file__
        with tempfile.TemporaryDirectory(prefix="koschei-wheel-missing-") as workspace:
            root = pathlib.Path(workspace)
            fake_module = root / "site-packages" / "koschei" / "data_native_source_v1.py"
            fake_module.parent.mkdir(parents=True)
            fake_module.write_text("", encoding="utf-8")
            try:
                native_source.__file__ = str(fake_module)
                with patch.object(
                    native_source,
                    "distribution",
                    return_value=_Distribution(root),
                ):
                    with self.assertRaisesRegex(RuntimeError, "missing the audited"):
                        native_source._source_path()
            finally:
                native_source.__file__ = original_file


if __name__ == "__main__":
    unittest.main()

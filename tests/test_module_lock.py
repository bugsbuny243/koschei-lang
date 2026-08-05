from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main
from koschei.module_lock import build_module_lock


class ModuleLockTests(unittest.TestCase):
    def _project(self, directory: str) -> tuple[Path, Path]:
        root = Path(directory)
        source = root / "main.ks"
        helper = root / "helper.ks"
        source.write_text(
            "import helper\n\nfn main() {\n    return\n}\n",
            encoding="utf-8",
        )
        helper.write_text("fn value() {\n    return\n}\n", encoding="utf-8")
        return source, helper

    def test_lock_create_and_verify_multifile_program(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _ = self._project(directory)
            lock_path = Path(directory) / "koschei.lock.json"
            output = io.StringIO()
            with redirect_stdout(output):
                create_code = main(
                    [
                        "lock",
                        "create",
                        str(source),
                        "--output",
                        str(lock_path),
                        "--json",
                    ]
                )
                verify_code = main(
                    [
                        "lock",
                        "verify",
                        str(source),
                        "--lock",
                        str(lock_path),
                        "--json",
                    ]
                )

            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(create_code, 0)
            self.assertEqual(verify_code, 0)
            self.assertEqual(rows[0]["modules"], 2)
            self.assertEqual(rows[0]["lock_digest"], rows[1]["lock_digest"])

    def test_module_change_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, helper = self._project(directory)
            lock_path = Path(directory) / "koschei.lock.json"
            self.assertEqual(
                main(["lock", "create", str(source), "--output", str(lock_path)]),
                0,
            )
            helper.write_text(
                helper.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )

            error = io.StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    ["lock", "verify", str(source), "--lock", str(lock_path)]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("KS1903", error.getvalue())
            self.assertIn("helper.ks", error.getvalue())

    def test_lock_generation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _ = self._project(directory)

            first = build_module_lock(source)
            second = build_module_lock(source)

            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(
                [module.path for module in first.modules],
                ["helper.ks", "main.ks"],
            )

    def test_unknown_lockfile_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _ = self._project(directory)
            lock_path = Path(directory) / "koschei.lock.json"
            self.assertEqual(
                main(["lock", "create", str(source), "--output", str(lock_path)]),
                0,
            )
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            payload["allow_network"] = True
            lock_path.write_text(json.dumps(payload), encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "lock",
                        "verify",
                        str(source),
                        "--lock",
                        str(lock_path),
                        "--json",
                    ]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(result["code"], "KS1901")

    def test_existing_lockfile_requires_explicit_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _ = self._project(directory)
            lock_path = Path(directory) / "koschei.lock.json"
            self.assertEqual(
                main(["lock", "create", str(source), "--output", str(lock_path)]),
                0,
            )

            error = io.StringIO()
            with redirect_stderr(error):
                exit_code = main(
                    ["lock", "create", str(source), "--output", str(lock_path)]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("--force", error.getvalue())


if __name__ == "__main__":
    unittest.main()

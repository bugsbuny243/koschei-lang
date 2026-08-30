from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "smoke_paddle_binary_v1.py"

spec = importlib.util.spec_from_file_location("smoke_paddle_binary_v1", TOOL)
assert spec and spec.loader
smoke_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke_tool)


class PaddleBinarySmokeContractTests(unittest.TestCase):
    def test_smoke_uses_real_ks_new_contract_and_records_required_checks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="koschei-paddle-smoke-test-") as tmp:
            root = Path(tmp)
            binary = root / "ks"
            binary.write_bytes(b"fake-sealed-binary")
            hello = root / "hello.ks"
            hello.write_text('fn main() { println("hello") }\n', encoding="utf-8")
            supply_chain = root / "supply.ks"
            supply_chain.write_text('fn main() { disk.read("/etc/passwd") }\n', encoding="utf-8")
            calls: list[tuple[str, list[str]]] = []

            def fake_success(_binary: Path, label: str, args: list[str], **_kwargs):
                calls.append((label, list(args)))
                if label == "ks new":
                    self.assertEqual(args[0], "new")
                    self.assertEqual(args[2:], ["--name", "demo"])
                    destination = Path(args[1])
                    (destination / "src").mkdir(parents=True)
                    (destination / "src" / "main.ks").write_text(
                        'fn main() { println("demo") }\n', encoding="utf-8"
                    )
                return subprocess.CompletedProcess([str(_binary), *args], 0, stdout="", stderr="")

            denied = subprocess.CompletedProcess(
                [str(binary), "check", str(supply_chain)],
                1,
                stdout="",
                stderr="KS2401: Required capability is unavailable in this scope",
            )

            with (
                patch.object(smoke_tool, "HELLO", hello),
                patch.object(smoke_tool, "SUPPLY_CHAIN", supply_chain),
                patch.object(smoke_tool, "_version", return_value="0.10.0"),
                patch.object(smoke_tool, "_success", side_effect=fake_success),
                patch.object(smoke_tool, "_run", return_value=denied),
            ):
                receipt = smoke_tool.smoke(binary)

            self.assertEqual(receipt["version"], "0.10.0")
            checks = receipt["checks"]
            for required in (
                "version_json",
                "check",
                "run",
                "new",
                "caps",
                "fmt",
                "lsp_command",
                "caps_c_ascii_locale",
                "ks2401_supply_chain_denial",
            ):
                self.assertIs(checks[required], True)
            self.assertTrue(any(label == "ks new" for label, _ in calls))
            self.assertTrue(any(label == "ks check generated project" for label, _ in calls))


if __name__ == "__main__":
    unittest.main()

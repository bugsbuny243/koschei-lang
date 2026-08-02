from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from koschei.cli_entry import main as cli_main
from koschei.foreign_contract import ForeignContractError, load_foreign_contract


class ForeignContractTests(unittest.TestCase):
    def write_contract(self, root: Path, **overrides):
        artifact = root / "worker.bin"
        artifact.write_bytes(b"safe foreign artifact\n")
        payload = {
            "schema": "koschei.foreign/v1",
            "module": "text.tools",
            "adapter": {
                "language": "rust",
                "isolation": "process",
                "protocol": "koschei-json/v1",
            },
            "artifact": {
                "path": "worker.bin",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            },
            "limits": {
                "max_request_bytes": 65536,
                "max_response_bytes": 65536,
                "max_millis": 1000,
                "max_memory_bytes": 67108864,
                "max_calls": 1000,
            },
            "functions": [
                {
                    "name": "normalize",
                    "parameters": [{"name": "value", "type": "String"}],
                    "returns": "String",
                    "effects": [],
                }
            ],
        }
        payload.update(overrides)
        path = root / "contract.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_valid_contract_verifies_artifact_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _ = self.write_contract(root)
            first = load_foreign_contract(path)
            second = load_foreign_contract(path)
            self.assertEqual(first.fingerprint, second.fingerprint)
            self.assertEqual(first.language, "rust")
            self.assertEqual(first.functions, 1)
            self.assertEqual(first.artifact_sha256, first.canonical["artifact"]["sha256"])

    def test_function_order_does_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["functions"] = [
                {
                    "name": "zeta",
                    "parameters": [],
                    "returns": "Void",
                    "effects": [],
                },
                {
                    "name": "alpha",
                    "parameters": [{"name": "items", "type": "List<Map<String,Int>>"}],
                    "returns": "Result<Int,String>",
                    "effects": [],
                },
            ]
            path.write_text(json.dumps(payload), encoding="utf-8")
            first = load_foreign_contract(path)
            payload["functions"].reverse()
            path.write_text(json.dumps(payload), encoding="utf-8")
            second = load_foreign_contract(path)
            self.assertEqual(first.fingerprint, second.fingerprint)
            self.assertEqual([f["name"] for f in first.canonical["functions"]], ["alpha", "zeta"])

    def test_capability_type_and_effects_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["functions"][0]["parameters"][0]["type"] = "NetCaps"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3803"):
                load_foreign_contract(path)

            payload["functions"][0]["parameters"][0]["type"] = "String"
            payload["functions"][0]["effects"] = ["net"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3802"):
                load_foreign_contract(path)

    def test_hash_mismatch_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["artifact"]["sha256"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3806"):
                load_foreign_contract(path)

            payload["artifact"]["path"] = "../worker.bin"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3806"):
                load_foreign_contract(path)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "worker.bin"
            artifact.write_bytes(b"x")
            digest = hashlib.sha256(b"x").hexdigest()
            path = root / "contract.json"
            path.write_text(
                '{"schema":"koschei.foreign/v1","schema":"koschei.foreign/v1",'
                '"module":"x","adapter":{"language":"c","isolation":"process",'
                '"protocol":"koschei-json/v1"},"artifact":{"path":"worker.bin",'
                f'"sha256":"{digest}"}},"limits":{{"max_request_bytes":1,'
                '"max_response_bytes":1,"max_millis":1,"max_memory_bytes":1048576,'
                '"max_calls":1},"functions":[{"name":"call","parameters":[],"returns":'
                '"Void","effects":[]}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ForeignContractError, "KS3801"):
                load_foreign_contract(path)

    def test_wasm_requires_wasm_isolation_and_process_languages_require_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["adapter"]["language"] = "wasm"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3802"):
                load_foreign_contract(path)

            payload["adapter"]["isolation"] = "wasm"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(load_foreign_contract(path).isolation, "wasm")

    def test_limits_reject_bool_and_out_of_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["limits"]["max_calls"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3804"):
                load_foreign_contract(path)

            payload["limits"]["max_calls"] = 100001
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ForeignContractError, "KS3804"):
                load_foreign_contract(path)

    def test_public_cli_validate_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _ = self.write_contract(root)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(["foreign", "validate", str(path), "--json"])
            self.assertEqual(code, 0, stderr.getvalue())
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["language"], "rust")
            fingerprint = payload["fingerprint"]

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli_main(["foreign", "fingerprint", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue().strip(), fingerprint)

    def test_public_cli_returns_coded_json_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, payload = self.write_contract(root)
            payload["artifact"]["sha256"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(["foreign", "validate", str(path), "--json"])
            self.assertEqual(code, 1)
            result = json.loads(stdout.getvalue())
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "KS3806")
            self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

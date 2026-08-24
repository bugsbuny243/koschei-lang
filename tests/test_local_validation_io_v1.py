from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from koschei.local_validation_io_v1 import (
    load_local_validation_receipt_v1,
    parse_local_validation_receipt_v1,
)
from koschei.local_validation_v1 import (
    LocalValidationError,
    seal_local_validation_receipt_v1,
    seal_local_validation_step_v1,
)


def receipt():
    step = seal_local_validation_step_v1(
        step_id="full-validation",
        command=("ks-local-validate", "--profile", "full"),
        returncode=0,
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
    )
    return seal_local_validation_receipt_v1(
        source_commit="c" * 40,
        checkout_clean=True,
        profile="full",
        python_version="Python 3.12.0",
        go_version="go version go1.21 linux/amd64",
        platform="Linux-test",
        steps=(step,),
    )


class LocalValidationIOV1Tests(unittest.TestCase):
    def test_cli_style_asdict_round_trip_loads_and_verifies(self):
        original = receipt()
        raw = asdict(original)
        parsed = parse_local_validation_receipt_v1(raw)
        self.assertEqual(parsed, original)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            loaded = load_local_validation_receipt_v1(path)
        self.assertEqual(loaded, original)
        loaded.require_for_release("c" * 40)

    def test_unknown_or_missing_fields_fail_closed(self):
        raw = asdict(receipt())
        raw["unexpected"] = True
        with self.assertRaisesRegex(LocalValidationError, "unknown=unexpected"):
            parse_local_validation_receipt_v1(raw)

        raw = asdict(receipt())
        del raw["profile"]
        with self.assertRaisesRegex(LocalValidationError, "missing=profile"):
            parse_local_validation_receipt_v1(raw)

    def test_step_tamper_fails_closed_after_drive_handoff(self):
        raw = asdict(receipt())
        raw["steps"][0]["stdout_sha256"] = "d" * 64
        with self.assertRaisesRegex(LocalValidationError, "validation step seal mismatch"):
            parse_local_validation_receipt_v1(raw)

    def test_bool_as_returncode_is_rejected(self):
        raw = asdict(receipt())
        raw["steps"][0]["returncode"] = True
        with self.assertRaisesRegex(LocalValidationError, "returncode must be an integer"):
            parse_local_validation_receipt_v1(raw)

    def test_malformed_json_and_stale_commit_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(LocalValidationError, "cannot load"):
                load_local_validation_receipt_v1(path)

        loaded = parse_local_validation_receipt_v1(asdict(receipt()))
        with self.assertRaisesRegex(LocalValidationError, "different source commit"):
            loaded.require_for_release("e" * 40)


if __name__ == "__main__":
    unittest.main()

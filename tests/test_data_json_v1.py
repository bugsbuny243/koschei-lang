from __future__ import annotations

import json
import unittest
from pathlib import Path

from koschei.data_json_v1 import DataError, Limits, Number, decode, encode


CASES = json.loads(
    (Path(__file__).parents[1] / "spec" / "data-json-v1-cases.json").read_text(
        encoding="utf-8"
    )
)


class DataJsonV1Tests(unittest.TestCase):
    def test_shared_canonical_cases(self) -> None:
        for case in CASES["canonical"]:
            with self.subTest(source=case["source"]):
                self.assertEqual(encode(decode(case["source"])), case["encoded"])

    def test_shared_error_cases(self) -> None:
        for case in CASES["errors"]:
            with self.subTest(source=case["source"]):
                with self.assertRaises(DataError) as raised:
                    decode(case["source"])
                self.assertEqual(raised.exception.code, case["code"])

    def test_input_byte_budget_is_checked_before_parse(self) -> None:
        with self.assertRaises(DataError) as raised:
            decode('"é"', Limits(max_input_bytes=3))
        self.assertEqual(raised.exception.code, "KS3601")

    def test_depth_and_node_budgets(self) -> None:
        with self.assertRaises(DataError) as depth:
            decode("[[[0]]]", Limits(max_depth=3))
        self.assertEqual(depth.exception.code, "KS3602")
        with self.assertRaises(DataError) as nodes:
            decode("[0,1,2]", Limits(max_nodes=3))
        self.assertEqual(nodes.exception.code, "KS3603")

    def test_output_budget_fails_before_returning_partial_text(self) -> None:
        with self.assertRaises(DataError) as raised:
            encode({"x": "12345"}, Limits(max_output_bytes=8))
        self.assertEqual(raised.exception.code, "KS3607")

    def test_host_numbers_and_arbitrary_objects_are_not_silently_encoded(self) -> None:
        for value in (1, 1.5, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(DataError) as raised:
                    encode(value)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "KS3608")
        self.assertEqual(encode(Number("42")), "42")

    def test_encode_rechecks_depth_and_nodes(self) -> None:
        with self.assertRaises(DataError) as depth:
            encode([[[Number("0")]]], Limits(max_depth=3))
        self.assertEqual(depth.exception.code, "KS3602")
        with self.assertRaises(DataError) as nodes:
            encode([Number("0"), Number("1"), Number("2")], Limits(max_nodes=3))
        self.assertEqual(nodes.exception.code, "KS3603")

    def test_error_offsets_are_utf8_byte_offsets(self) -> None:
        with self.assertRaises(DataError) as raised:
            decode('["😀",]')
        self.assertEqual(raised.exception.offset, 8)


if __name__ == "__main__":
    unittest.main()

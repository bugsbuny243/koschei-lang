from __future__ import annotations

import unittest

import koschei  # installs the Data ABI
from koschei.parser import parse
from koschei.semantic import SemanticError, check


class DataOutputBoundaryV1Tests(unittest.TestCase):
    def test_data_cannot_bypass_encoding_through_interpolation(self) -> None:
        source = r'''
fn main() {
    let value = parse_json("null") or return Error("parse failed")
    println("payload={value}")
}
'''
        with self.assertRaises(SemanticError) as context:
            check(parse(source))
        self.assertEqual(context.exception.code, "KS3708")


if __name__ == "__main__":
    unittest.main()

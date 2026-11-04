"""Negative UART transcript fixtures for isolated CPU #PF evidence."""
from pathlib import Path
import tempfile
import unittest

from verify_serial import EXPECTED
from verify_cpu_pf_serial import EXPECTED_PF, verify


class RealPfSerialEvidenceTests(unittest.TestCase):
    def assert_receipt(self, data: bytes, accepted: bool) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "uart.log"
            path.write_bytes(data)
            if accepted:
                verify(path)
            else:
                with self.assertRaises(ValueError):
                    verify(path)

    def test_single_exact_synthetic_fixture(self) -> None:
        self.assert_receipt(
            b"OVMF UART prefix\r\n" +
            b"".join(EXPECTED[:-1]) + EXPECTED_PF + EXPECTED[-1],
            True,
        )

    def test_no_pf_record(self) -> None:
        self.assert_receipt(b"".join(EXPECTED), False)

    def test_cpu_error_mismatch(self) -> None:
        original = b"".join(EXPECTED[:-1]) + EXPECTED_PF + EXPECTED[-1]
        self.assert_receipt(original.replace(b"ERROR=0000000000000000",
                                             b"ERROR=0000000000000001"), False)

    def test_cpu_cr2_mismatch(self) -> None:
        original = b"".join(EXPECTED[:-1]) + EXPECTED_PF + EXPECTED[-1]
        self.assert_receipt(original.replace(b"CR2=0000400000000000",
                                             b"CR2=0000400000001000"), False)

    def test_duplicate_receipt(self) -> None:
        expected = b"".join(EXPECTED[:-1]) + EXPECTED_PF + EXPECTED[-1]
        self.assert_receipt(EXPECTED_PF + expected, False)

    def test_reject_or_truncated(self) -> None:
        expected = b"".join(EXPECTED[:-1]) + EXPECTED_PF + EXPECTED[-1]
        self.assert_receipt(b"KOSCHEI-KERNEL REJECT/1 CPU-PF\r\n" + expected, False)
        self.assert_receipt(expected[:-2], False)


if __name__ == "__main__":
    unittest.main()

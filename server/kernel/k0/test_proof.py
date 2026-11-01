"""Negative evidence checks, no QEMU/OS dependency for these unit tests."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import unittest


ROOT = Path(__file__).resolve().parent


def load(filename: str):
    spec = importlib.util.spec_from_file_location("k0_" + filename, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


pe = load("verify_pe.py")
serial = load("verify_serial.py")


class K0ProofFailClosedTests(unittest.TestCase):
    def test_reject_cr3_probe_marker_in_release(self):
        marker = pe.QEMU_CR3_PF_MARKER
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(marker, marker)
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(b"SAFE_RELEASE", b"NO_CR3_MARKER")
        pe.verify_qemu_only_cr3_probe(b"SAFE_RELEASE", marker)
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(b"SAFE_RELEASE", marker, b"MISSING_RO")
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                pe.QEMU_CR3_RO_MARKER, marker, pe.QEMU_CR3_RO_MARKER)
        pe.verify_qemu_only_cr3_probe(
            b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER)
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER, b"BAD_NX")
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                pe.QEMU_CR3_NX_MARKER, marker, pe.QEMU_CR3_RO_MARKER,
                pe.QEMU_CR3_NX_MARKER)
        pe.verify_qemu_only_cr3_probe(
            b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER, pe.QEMU_CR3_NX_MARKER)

    def test_strict_readonly_fault_uart_not_confused_with_missing_page(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "uart.log"
            file.write_bytes(b"".join(serial.EXPECTED_READONLY))
            serial.verify(file, "ro")
            with self.assertRaises(ValueError):
                serial.verify(file, "missing")
            file.write_bytes(b"".join(serial.EXPECTED))
            with self.assertRaises(ValueError):
                serial.verify(file, "ro")
            file.write_bytes(b"".join(serial.EXPECTED_NX))
            serial.verify(file, "nx")
            with self.assertRaises(ValueError):
                serial.verify(file, "missing")
            with self.assertRaises(ValueError):
                serial.verify(file, "ro")

    def test_mapped_test_binary_and_transcript_fail_closed(self):
        marker = pe.QEMU_CR3_PF_MARKER
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER,
                pe.QEMU_CR3_NX_MARKER, b"NOT_THE_MAPPED_PROBE")
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                pe.QEMU_CR3_MAPPED_MARKER, marker, pe.QEMU_CR3_RO_MARKER,
                pe.QEMU_CR3_NX_MARKER, pe.QEMU_CR3_MAPPED_MARKER)
        pe.verify_qemu_only_cr3_probe(
            b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER,
            pe.QEMU_CR3_NX_MARKER, pe.QEMU_CR3_MAPPED_MARKER)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "serial.log"
            path.write_bytes(b"".join(serial.EXPECTED_MAPPED))
            serial.verify(path, "mapped")
            with self.assertRaises(ValueError):
                serial.verify(path, "missing")
            with self.assertRaises(ValueError):
                serial.verify(path, "nx")

    def test_code_write_denial_binary_isolation_and_uart(self):
        marker = pe.QEMU_CR3_PF_MARKER
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                pe.QEMU_CR3_WX_MARKER, marker, pe.QEMU_CR3_RO_MARKER,
                pe.QEMU_CR3_NX_MARKER, pe.QEMU_CR3_MAPPED_MARKER,
                pe.QEMU_CR3_WX_MARKER)
        with self.assertRaises(ValueError):
            pe.verify_qemu_only_cr3_probe(
                b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER,
                pe.QEMU_CR3_NX_MARKER, pe.QEMU_CR3_MAPPED_MARKER, b"BAD")
        pe.verify_qemu_only_cr3_probe(
            b"SAFE_RELEASE", marker, pe.QEMU_CR3_RO_MARKER,
            pe.QEMU_CR3_NX_MARKER, pe.QEMU_CR3_MAPPED_MARKER,
            pe.QEMU_CR3_WX_MARKER)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "uart.log"
            path.write_bytes(b"".join(serial.EXPECTED_WX))
            serial.verify(path, "wx")
            with self.assertRaises(ValueError):
                serial.verify(path, "ro")

    def test_refuse_random_binary_with_no_pe(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "invalid.efi"
            file.write_bytes(b"NOT_A_KERNEL" * 32)
            with self.assertRaises(ValueError):
                pe.verify_uefi_pe(file)

    def test_refuse_truncated_dos_and_bad_pe_offset(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "invalid.efi"
            file.write_bytes(b"MZ")
            with self.assertRaises(ValueError):
                pe.verify_uefi_pe(file)
            file.write_bytes(b"MZ" + b"\x00" * 510)
            with self.assertRaises(ValueError):
                pe.verify_uefi_pe(file)

    def test_refuse_missing_or_extra_uart_line(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "uart.log"
            for data in (
                b"",
                serial.EXPECTED[0],
                b"".join(serial.EXPECTED) + b"FORGED\r\n",
                b"KOSCHEI-KERNEL REJECT/1 INVALID-UEFI\r\n" + b"".join(serial.EXPECTED),
            ):
                file.write_bytes(data)
                with self.subTest(data=data), self.assertRaises(ValueError):
                    serial.verify(file)

    def test_accept_only_three_exact_expected_uart_lines(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "uart.log"
            file.write_bytes(b"".join(serial.EXPECTED))
            serial.verify(file)
            # Real OVMF emits a non-Koschei firmware preface on COM1.
            file.write_bytes(
                b"OVMF UEFI BOOT PREFIX" + b"".join(serial.EXPECTED)
            )
            serial.verify(file)

    def test_reject_forged_or_repeated_koschei_prefix(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "uart.log"
            for prefix in (
                serial.EXPECTED[0],
                b"KOSCHEI-KERNEL REJECT/1 INVALID-UEFI\\r\\n",
            ):
                file.write_bytes(prefix + b"".join(serial.EXPECTED))
                with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                    serial.verify(file)


if __name__ == "__main__":
    unittest.main()

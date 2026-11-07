"""Adversarial CPU state + #PF serial receipt fixtures for QEMU-only probe."""
from pathlib import Path
import tempfile
import unittest

from verify_cpu_pf_serial import (
    EXPECTED_PF,
    EXPECTED_PREFIX,
    EXPECTED_TAIL,
    VALID_LIVE_FIXTURE,
    VALID_IMAGE_FIXTURE,
    VALID_WALK_FIXTURE,
    OWNED_TABLES_RECEIPT,
    MULTI_PT_RECEIPT,
    validate_live_register_record,
    verify,
)


class LiveCpuAndRealPfEvidenceTests(unittest.TestCase):
    def assert_receipt(self, data: bytes, accepted: bool) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "uart.log"
            path.write_bytes(data)
            if accepted:
                verify(path)
            else:
                with self.assertRaises(ValueError):
                    verify(path)

    def valid(self) -> bytes:
        return (b"OVMF UART prefix\r\n" + EXPECTED_PREFIX +
                VALID_IMAGE_FIXTURE + VALID_WALK_FIXTURE +
                OWNED_TABLES_RECEIPT + MULTI_PT_RECEIPT +
                VALID_LIVE_FIXTURE + EXPECTED_TAIL)

    def test_valid_synthetic_fixture_only_for_verifier(self):
        self.assert_receipt(self.valid(), True)
        values = validate_live_register_record(VALID_LIVE_FIXTURE)
        self.assertEqual(values["CR3"], 0x800000)
        self.assertEqual(values["EFER"], 0xD00)

    def test_missing_live_or_fault(self):
        self.assert_receipt(EXPECTED_PREFIX + EXPECTED_TAIL, False)
        self.assert_receipt(EXPECTED_PREFIX + VALID_LIVE_FIXTURE + EXPECTED_TAIL, False)
        self.assert_receipt(EXPECTED_PREFIX + VALID_IMAGE_FIXTURE + EXPECTED_TAIL, False)
        self.assert_receipt(self.valid().replace(EXPECTED_PF, b""), False)

    def test_fault_error_and_cr2_mismatch(self):
        self.assert_receipt(self.valid().replace(
            b"ERROR=0000000000000000", b"ERROR=0000000000000001"), False)
        self.assert_receipt(self.valid().replace(
            b"CR2=0000400000000000", b"CR2=0000400000001000"), False)

    def test_missing_or_forged_cpu_registers(self):
        original = self.valid()
        substitutions = (
            (b"CR0=0000000080010001", b"CR0=0000000080000001"), # missing WP
            (b"CR0=0000000080010001", b"CR0=0000000000010001"), # missing PG
            (b"CR4=0000000000000020", b"CR4=0000000000000000"), # missing PAE
            (b"CR4=0000000000000020", b"CR4=0000000000001020"), # LA57
            (b"CR4=0000000000000020", b"CR4=0000000000020020"), # PCIDE
            (b"EFER=0000000000000d00", b"EFER=0000000000000500"), # missing NXE
            (b"RFLAGS=0000000000000002", b"RFLAGS=0000000000000202"), # IF set
            (b"CS=0000000000000008", b"CS=000000000000001b"), # ring 3
            (b"CR3=0000000000800000", b"CR3=0000000000800001"), # unaligned
            (b"RIP=0000000000400200", b"RIP=0000800000000000"), # noncanonical
            (b"RSP=0000000000600ff0", b"RSP=0000000000000000"), # zero
            (b"GDTR=0000000000100000", b"GDTR=0000000000000000"),
            (b"GDTLIMIT=0000000000000040", b"GDTLIMIT=0000000000000010"),
            (b"IDTLIMIT=0000000000000fff", b"IDTLIMIT=0000000000000000"),
        )
        for prior, after in substitutions:
            with self.subTest(after=after):
                self.assertIn(prior, original)
                self.assert_receipt(original.replace(prior, after), False)

    def test_multi_pt_physical_readback_receipt_fail_closed(self):
        valid = self.valid()
        self.assert_receipt(valid.replace(MULTI_PT_RECEIPT, b""), False)
        self.assert_receipt(valid.replace(
            b"MULTI-PT/1", b"MULTI-PT/2"), False)
        self.assert_receipt(valid.replace(
            b"PHYSICAL-READBACK", b"LOGICAL-MODEL", 1), False)
        self.assert_receipt(valid.replace(
            b"MULTI-PT/1 PHYSICAL-READBACK CR3-UNCHANGED",
            b"MULTI-PT/1 PHYSICAL-READBACK CR3-SWITCHED"), False)
        self.assert_receipt(valid.replace(
            MULTI_PT_RECEIPT, MULTI_PT_RECEIPT + MULTI_PT_RECEIPT), False)
        self.assert_receipt(MULTI_PT_RECEIPT + valid, False)

    def test_koschei_owned_table_materialization_receipt_fail_closed(self):
        valid = self.valid()
        self.assert_receipt(valid.replace(OWNED_TABLES_RECEIPT, b""), False)
        self.assert_receipt(valid.replace(
            b"PHYSICAL-READBACK", b"MODEL-ONLY"), False)
        self.assert_receipt(valid.replace(
            b"CR3-UNCHANGED", b"CR3-SWITCHED"), False)
        self.assert_receipt(OWNED_TABLES_RECEIPT + valid, False)
        self.assert_receipt(valid.replace(
            OWNED_TABLES_RECEIPT,
            OWNED_TABLES_RECEIPT + OWNED_TABLES_RECEIPT), False)
        self.assert_receipt(valid.replace(
            OWNED_TABLES_RECEIPT, OWNED_TABLES_RECEIPT[:-2]), False)

    def test_real_cr3_table_bytes_must_match_cpu_observation(self):
        valid = self.valid()
        substitutions = (
            (b"RIPPA=0000000000400200", b"RIPPA=0000000000401200"),
            (b"RSPPA=0000000000600fef", b"RSPPA=0000000000600ff0"),
            (b"CR3=0000000000800000", b"CR3=0000000000810000"),
            (b"RIPPA=0000000000400200", b"RIPPA=0000000000000000"),
            (b"RSPPA=0000000000600fef", b"RSPPA=0000000010600fef"),
            (b"KOSCHEI-KERNEL K0 CR3-WALK/1",
             b"KOSCHEI-KERNEL K0 CR3-WALK/2"),
        )
        for old, new in substitutions:
            with self.subTest(changed=new):
                self.assertIn(old, valid)
                self.assert_receipt(valid.replace(old, new, 1), False)
        self.assert_receipt(valid.replace(VALID_WALK_FIXTURE, b""), False)
        self.assert_receipt(VALID_WALK_FIXTURE + valid, False)

    def test_uefi_loaded_image_bounds_are_exact_and_bind_real_rip(self):
        valid = self.valid()
        pairs = (
            (b"BASE=0000000000400000", b"BASE=0000000000600000"),
            (b"BASE=0000000000400000", b"BASE=0000000000400001"),
            (b"BASE=0000000000400000", b"BASE=0000000000000000"),
            (b"SIZE=0000000000010000", b"SIZE=0000000000000000"),
            (b"SIZE=0000000000010000", b"SIZE=0000000000000100"),
            (b"SIZE=0000000000010000", b"SIZE=0000000002010000"),
            (b"RSP=0000000000600ff0", b"RSP=0000000000400ff0"),
            (b"KOSCHEI-KERNEL K0 IMAGE-LIVE/1",
             b"KOSCHEI-KERNEL K0 IMAGE-LIVE/2"),
        )
        for old, new in pairs:
            with self.subTest(changed=new):
                self.assertIn(old, valid)
                self.assert_receipt(valid.replace(old, new), False)
        self.assert_receipt(valid.replace(VALID_IMAGE_FIXTURE, b""), False)
        self.assert_receipt(VALID_IMAGE_FIXTURE + valid, False)

    def test_duplicate_noncanonical_or_truncated_receipt(self):
        valid = self.valid()
        self.assert_receipt(VALID_LIVE_FIXTURE + valid, False)
        self.assert_receipt(EXPECTED_PF + valid, False)
        self.assert_receipt(valid[:-2], False)
        self.assert_receipt(valid + b"EXTRA", False)
        self.assert_receipt(valid.replace(
            b"CS=0000000000000008", b"CS=000000000000000G"), False)
        self.assert_receipt(b"KOSCHEI-KERNEL REJECT/1 CPU-LIVE\r\n" + valid, False)


if __name__ == "__main__":
    unittest.main()

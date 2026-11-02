"""Real QEMU/OVMF evidence for the Koschei UEFI boot prototype (uefi_boot_v1).

The emulator in ``uefi_boot_v1`` is a model; this boots the very ESP image
``build_fat16_esp_image_v1`` writes in QEMU with OVMF firmware, talks to the
image's COM1 shell over a socket, and reads QEMU's own interrupt log. It is
skipped where QEMU or OVMF is not installed; the dedicated workflow
``.github/workflows/koschei-uefi-prototype-qemu.yml`` installs both.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

from koschei import cli as _cli
from koschei.mir import require_mir
from koschei.modules import check_graph
from koschei.uefi_boot_v1 import (
    EXPERIMENTAL_CR3_BANNER,
    EXPERIMENTAL_PMM_BANNER,
    MEMORY_MAP_BUFFER_BYTES,
    MORTH_TRAP_BANNER,
    SHELL_READY_BANNER,
    build_fat16_esp_image_v1,
    build_uefi_pe32plus_v1,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "uefi_boot" / "boot.ks"
QEMU = shutil.which("qemu-system-x86_64")
OVMF_CODE = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
OVMF_VARS = Path("/usr/share/OVMF/OVMF_VARS_4M.fd")
HEX = "[0-9a-f]{16}"
AVAILABLE = bool(QEMU) and OVMF_CODE.is_file() and OVMF_VARS.is_file()


def _artifact(**options):
    graph = _cli.open_graph(str(EXAMPLE))
    check_graph(graph)
    return build_uefi_pe32plus_v1(require_mir(graph), **options)


class _Machine:
    """One QEMU q35 guest booting an ESP image, COM1 on a Unix socket."""

    def __init__(self, directory: Path, image: bytes) -> None:
        (directory / "esp.img").write_bytes(image)
        shutil.copy(OVMF_VARS, directory / "vars.fd")
        self.log = directory / "qemu.log"
        socket_path = directory / "com1.sock"
        self.process = subprocess.Popen(
            [
                QEMU, "-machine", "q35", "-m", "256",
                "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
                "-drive", f"if=pflash,format=raw,file={directory / 'vars.fd'}",
                "-drive", f"format=raw,file={directory / 'esp.img'}",
                "-net", "none", "-display", "none", "-no-reboot",
                "-chardev", f"socket,id=com1,path={socket_path},server=on,wait=on",
                "-serial", "chardev:com1",
                "-d", "cpu_reset,int", "-D", str(self.log),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while not socket_path.exists():
            if time.monotonic() > deadline:
                self.close()
                raise AssertionError("QEMU did not open the COM1 socket")
            time.sleep(0.05)
        self.com1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.com1.connect(str(socket_path))
        self.com1.settimeout(0.2)
        self.output = bytearray()

    def wait_for(self, marker: bytes, timeout: float = 120) -> bool:
        deadline = time.monotonic() + timeout
        while marker not in self.output:
            if time.monotonic() > deadline or self.process.poll() is not None:
                self._drain()
                return marker in self.output
            self._drain()
        return True

    def _drain(self) -> None:
        try:
            chunk = self.com1.recv(65536)
        except socket.timeout:
            return
        except OSError:
            return
        self.output += chunk

    def send(self, line: str) -> None:
        self.com1.sendall(line.encode("ascii") + b"\r")

    def exited(self, timeout: float) -> bool:
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return True

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    def text(self) -> str:
        return self.output.decode("utf-8", "replace").replace("\r", "")


class UefiPrototypeRealQemuTests(unittest.TestCase):
    def setUp(self) -> None:
        if AVAILABLE:
            return
        if os.environ.get("KOSCHEI_REQUIRE_QEMU"):
            self.fail("KOSCHEI_REQUIRE_QEMU is set but QEMU or OVMF is not installed")
        self.skipTest("QEMU and OVMF are not installed")

    def test_the_esp_image_boots_exits_the_firmware_and_serves_the_shell(self) -> None:
        artifact = _artifact()
        with tempfile.TemporaryDirectory(prefix="koschei-uefi-qemu-") as workspace:
            machine = _Machine(Path(workspace), build_fat16_esp_image_v1(artifact))
            try:
                self.assertTrue(machine.wait_for(SHELL_READY_BANNER), machine.text()[-2000:])
                text = machine.text()
                for line in artifact.serial_payload.decode("utf-8").splitlines():
                    self.assertIn(line, text)
                v2 = re.search(
                    rf"\[KOSCHEI-KERNEL-V2\] ExitBootServices=OK attempt=0x000000000000000([12]) "
                    rf"memory_map_bytes=0x({HEX}) descriptor_bytes=0x({HEX})\n",
                    text,
                )
                self.assertIsNotNone(v2, text[-2000:])
                map_bytes = int(v2.group(2), 16)
                self.assertGreater(map_bytes, 0)
                self.assertLessEqual(map_bytes, MEMORY_MAP_BUFFER_BYTES)
                self.assertRegex(
                    text,
                    rf"\[KOSCHEI-KERNEL-V3\] gdt=loaded cs=0x08 ds=es=fs=gs=ss=0x10 "
                    rf"idt=32_gates\(0-31 -> fail-closed trap\) image_text=0x{HEX}\n",
                )
                self.assertIn("[KOSCHEI-KERNEL-V4] paging=firmware_identity own_page_tables=none\n", text)
                self.assertRegex(
                    text,
                    rf"\[KOSCHEI-KERNEL-V5\] pic_8259=remapped_0x20_0x28_all_masked "
                    rf"pit_8254=programmed_divisor_1193 interrupts=disabled tsc=0x{HEX} epoch=2\n",
                )

                exchanges = (
                    ("STATUS", b"paging=firmware_identity epoch=0x0000000000000002\r\n"),
                    ("MEM", b"descriptor_bytes=0x%s own_page_tables=none allocator=none\r\n" % v2.group(3).encode()),
                    ("EPOCH", b"[KOSCHEI-SHELL] epoch=0x0000000000000003 tsc=0x"),
                    ("MIR", f"sealed_mir_sha256={artifact.mir_fingerprint}\r\n".encode()),
                    ("NOPE", b"[KOSCHEI-SHELL] unknown command"),
                    ("TRAP", MORTH_TRAP_BANNER),
                )
                for line, reply in exchanges:
                    with self.subTest(command=line):
                        machine.send(line)
                        self.assertTrue(machine.wait_for(reply, timeout=30), machine.text()[-1500:])
                mem = re.search(rf"memory_map_bytes=0x({HEX}) descriptor_bytes", machine.text().split("recv=MEM")[1])
                self.assertEqual(int(mem.group(1), 16), map_bytes)
            finally:
                machine.close()
            # QEMU's own log: #UD (vector 6) was delivered at CPL 0 with the
            # Koschei code and stack selectors loaded, so the CPU used our GDT
            # and IDT rather than the firmware's.
            log = Path(workspace, "qemu.log").read_text(errors="replace")
            self.assertRegex(log, r"v=06 e=0000 i=0 cpl=0 IP=0008:[0-9a-f]+ pc=[0-9a-f]+ SP=0010:")
            self.assertNotIn("Triple fault", log)

    def test_the_experimental_page_tables_triple_fault_and_never_claim_success(self) -> None:
        artifact = _artifact(experimental_page_tables=True)
        with tempfile.TemporaryDirectory(prefix="koschei-uefi-qemu-") as workspace:
            machine = _Machine(Path(workspace), build_fat16_esp_image_v1(artifact))
            try:
                self.assertTrue(machine.wait_for(EXPERIMENTAL_PMM_BANNER), machine.text()[-2000:])
                # -no-reboot turns the triple fault's reset into QEMU exiting.
                self.assertTrue(machine.exited(timeout=60))
                machine._drain()
            finally:
                machine.close()
            self.assertNotIn(EXPERIMENTAL_CR3_BANNER, machine.output)
            self.assertNotIn(b"[KOSCHEI-KERNEL-V5]", machine.output)
            self.assertIn("Triple fault", Path(workspace, "qemu.log").read_text(errors="replace"))


if __name__ == "__main__":
    unittest.main()

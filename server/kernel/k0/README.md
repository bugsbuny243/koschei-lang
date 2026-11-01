# Koschei Server K0.3 staging — bounded post-UEFI page probe

Status: DEVELOPMENT BOOT PROTOTYPE, NOT A COMPLETE OPERATING SYSTEM.

## Customer target
Koschei Server must ultimately boot on x86-64 hardware and run Koschei
runtime/Library workloads without Windows, Linux, BSD or another hosted OS.
The present entry point uses UEFI GetMemoryMap, validates all memory descriptors,
rejects zero/unaligned/overflow/overlapping ranges, and plans a 16-page
64 KiB candidate solely from conventional memory above 1 MiB.
The candidate plan is validated while firmware owns memory. K0.2 then calls
ExitBootServices with a fresh memory-map key, retries boundedly on stale-key
rejection and fails closed on any other result. In the K0.3 staging branch, a 16-page metadata ledger can claim only pages
from that validated candidate after successful firmware exit. Two distinct
claimed pages are written, read, checked for aliasing, zeroed and released in
the QEMU diagnostic. This depends on the firmware's existing identity mapping,
which is NOT evidence of an independent address space or physical isolation.
The entry point uses the UEFI firmware's standard boot protocol and
writes directly to COM1 UART hardware ports without libc or host syscalls.

## Evidence and commands
- Build: bash server/kernel/k0/build.sh OUTPUT_DIRECTORY
- Negative Python evidence tests: python3 -m unittest discover -s server/kernel/k0 -p 'test_*.py' -v
- Native memory-map tests: clang -std=c11 -O2 -Wall -Wextra -Werror server/kernel/k0/test_memory_map.c -o /tmp/k0-memory-test && /tmp/k0-memory-test
- Native ledger tests: clang -std=c11 -O2 -Wall -Wextra -Werror server/kernel/k0/test_page_pool.c -o /tmp/k0-pool-test && /tmp/k0-pool-test
- Real UEFI boot: bash server/kernel/k0/qemu_smoke.sh OUTPUT_DIRECTORY
- GitHub workflow: .github/workflows/koschei-k0-boot.yml

The compiler and QEMU emulator run on a temporary CI build machine; they are
NOT embedded into the UEFI guest. The produced x86-64 release binary has no
imported Windows/Linux/Go/Python libraries and halts after printing serial
diagnostics. QEMU uses a **separate test binary** with a special device
exit code; that device operation is absent in the release image.

Acceptance requires:
1. A valid, import-free EFI PE32+ x86-64 artifact and SHA256 record.
2. Actual QEMU OVMF cold-boot from EFI/BOOT/BOOTX64.EFI on a FAT USB image.
3. Exact serial transcript, nine Koschei records (QEMU test binary) after OVMF firmware prefix:
   KOSCHEI-KERNEL BOOT/1 X86_64-UEFI
   KOSCHEI-KERNEL K0 SERIAL-OWNED
   KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED
   KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED
   KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED
   KOSCHEI-KERNEL K0 PAGE-POOL-PROBED
   KOSCHEI-KERNEL K0 PAGE-TABLE-FRAMES-ROUNDTRIP
   KOSCHEI-KERNEL K0 OWN-CR3-PF-DENIED
   KOSCHEI-KERNEL K0 HALT-NO-POLICY
4. QEMU debug-exit code 33; a timeout or fabricated file is not a pass.
5. CI artifact binds transcript hash, source revision and toolchain versions.

## Honest limits
ExitBootServices handoff is attempted and must succeed in the QEMU boot
probe. The 16-page ledger is a bounded diagnostic allocator, NOT a general-purpose
physical memory manager. K0.4 staging also writes and reads back four *inactive*
physical page-table frames after CPU NX/EFER.NXE checks, then wipes and releases
them. No own CR3 is installed, so no Koschei-owned **active** page tables or
hardware memory isolation exists. There are no fault handlers, interrupt
controller, scheduler, storage, network, domain/process isolation or
sealed-MIR runner. UEFI firmware remains an external physical trust input.
The prototype is x86-64/QEMU-focused, not proof of booting physical devices,
and cannot yet host customer applications or claim zero attack risk.

Next: secure kernel/boot/ACPI/MMIO reservations, prove non-identity mapping
and Koschei-owned page tables, add a controlled page-fault rejection test; K1 owns domain/IPC/handle enforcement using canonical Koschei Library decisions.
Issue #331 tracks these requirements.

## QEMU-only CR3 / page-fault experiment
The PE verifier also rejects release images containing the CR3/#PF test marker,
or QEMU images missing it. This is a binary separation regression, not a
general proof that arbitrary dangerous instructions are absent.

The QEMU test image (NOT the release image) creates its own three physical
page-table frames and loads CR3. To preserve the UEFI-loaded code and current
stack under the test, it temporarily maps the entire lower 1 GiB identity
with writable/executable 2 MiB huge pages. This blanket mapping is
**insecure and explicitly forbidden in a production Koschei kernel**.
It installs a minimal, single-vector #PF IDT, masks interrupts, and triggers
an unmapped high-half read. The handler records CR2, predicted error code
zero, and the active CR3; a genuine vector-14 path is required to emit the
UART OWN-CR3-PF-DENIED marker and QEMU exit 33. All other faults/timeout paths
fail the test. This establishes **only a controlled emulator CR3/#PF probe**,
NOT constrained kernel/user domains, W^X execution isolation, protection of
firmware regions, supported hardware boot, or production memory safety.

## Staging / acceptance gate
K0.3 has already merged. K0.4 remains staging until an independently owned
CR3 transition and real CPU #PF denial are reproduced. The current table-frame
roundtrip only proves that the guest could write, read and zero physical frames
under the **firmware-provided mappings**, not that the CPU used them.
Full canonical Lang CI and dedicated QEMU CI must both pass on the final exact
head before any follow-on PR merge.

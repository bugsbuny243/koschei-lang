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
- Native K0.4 GDT/IDT and exception-context preflight (synthetic only):
  clang -std=c11 -O2 -Wall -Wextra -Werror server/kernel/k0/test_idt_fault_model.c -o /tmp/k0-idt-test && /tmp/k0-idt-test
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
3. Exact serial transcript, eight Koschei records after OVMF firmware prefix:
   KOSCHEI-KERNEL BOOT/1 X86_64-UEFI
   KOSCHEI-KERNEL K0 SERIAL-OWNED
   KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED
   KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED
   KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED
   KOSCHEI-KERNEL K0 PAGE-POOL-PROBED
   KOSCHEI-KERNEL K0 PAGE-TABLE-FRAMES-ROUNDTRIP
   KOSCHEI-KERNEL K0 HALT-NO-POLICY
4. QEMU debug-exit code 33; a timeout or fabricated file is not a pass.
5. CI artifact binds transcript hash, source revision and toolchain versions.

## Optional real CPU #PF diagnostic (test binary only)

The separate `BOOTX64-PF.EFI` image installs a temporary #PF IDT under the
firmware-owned CR3 and records an actual CPU-supplied CR2/error code after
attempting a deliberately unmapped canonical read. It proves **CPU exception
entry in QEMU**, not an independent Koschei address space.

To reproduce both independent boots after `build.sh`:

```sh
bash server/kernel/k0/qemu_smoke.sh /tmp/k0-evidence
mkdir -p /tmp/k0-evidence/cpu-pf
KOSCHEI_K0_GUEST_BINARY=/tmp/k0-evidence/BOOTX64-PF.EFI \
KOSCHEI_K0_SERIAL_VERIFIER="$PWD/server/kernel/k0/verify_cpu_pf_serial.py" \
  bash server/kernel/k0/qemu_smoke.sh /tmp/k0-evidence/cpu-pf
```

The second test requires a real QEMU debug-exit code and the exact
fourteen-record UART transcript. It now contains a firmware
`EFI_LOADED_IMAGE_PROTOCOL` image-base/image-size record, captured CPU
CR0/CR3/CR4/EFER/GDTR/IDTR/RFLAGS/CS/RIP/RSP values, a read-only active firmware CR3 PTE-byte walk receipt for
CPU-observed RIP/RSP physical addresses, a Koschei-owned **physical**
table-frame byte readback/scrub receipt (CR3 unchanged), a three-PT
physical table-page sample readback receipt (CR3 unchanged), and the hardware
CR2/error-code record. The diagnostic checks observed RIP and stack
residency against the final UEFI memory map. The verifier rejects
missing, altered or duplicated records. No owned CR3 is activated. Failed, absent or
unhandled faults are rejected; the release image never enables this probe.

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

## Staging / acceptance gate
K0.3 has already merged. K0.4 remains staging until an independently owned
CR3 transition and real CPU #PF denial are reproduced. The current table-frame
roundtrip only proves that the guest could write, read and zero physical frames
under the **firmware-provided mappings**, not that the CPU used them.
Full canonical Lang CI and dedicated QEMU CI must both pass on the final exact
head before any follow-on PR merge.

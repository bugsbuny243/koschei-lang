# Koschei Server K0.2 — UEFI ExitBootServices handoff probe

Status: DEVELOPMENT BOOT PROTOTYPE, NOT A COMPLETE OPERATING SYSTEM.

## Customer target
Koschei Server must ultimately boot on x86-64 hardware and run Koschei
runtime/Library workloads without Windows, Linux, BSD or another hosted OS.
The present entry point uses UEFI GetMemoryMap, validates all memory descriptors,
rejects zero/unaligned/overflow/overlapping ranges, and plans a 16-page
64 KiB candidate solely from conventional memory above 1 MiB.
The candidate plan is validated while firmware owns memory. K0.2 then calls
ExitBootServices with a fresh memory-map key, retries boundedly on stale-key
rejection and fails closed on any other result. Physical candidate pages are
NOT yet written or isolated; an independent page ledger is still experimental.
The entry point uses the UEFI firmware's standard boot protocol and
writes directly to COM1 UART hardware ports without libc or host syscalls.

## Evidence and commands
- Build: bash server/kernel/k0/build.sh OUTPUT_DIRECTORY
- Negative Python evidence tests: python3 -m unittest discover -s server/kernel/k0 -p 'test_*.py' -v
- Native memory-map tests: clang -std=c11 -O2 -Wall -Wextra -Werror server/kernel/k0/test_memory_map.c -o /tmp/k0-memory-test && /tmp/k0-memory-test
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
3. Exact serial transcript, six Koschei records after OVMF firmware prefix:
   KOSCHEI-KERNEL BOOT/1 X86_64-UEFI
   KOSCHEI-KERNEL K0 SERIAL-OWNED
   KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED
   KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED
   KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED
   KOSCHEI-KERNEL K0 HALT-NO-POLICY
4. QEMU debug-exit code 33; a timeout or fabricated file is not a pass.
5. CI artifact binds transcript hash, source revision and toolchain versions.

## Honest limits
ExitBootServices handoff is attempted and must succeed in the QEMU boot
probe. There is NO owned physical memory allocator, page tables, interrupts,
scheduler, storage, network, isolated processes or Koschei sealed-MIR runner
exist here. UEFI firmware remains an external physical trust input.
The prototype is x86-64/QEMU-focused, not proof of booting physical devices,
and cannot yet host customer applications or claim zero attack risk.

Next: independently verify owned physical pages after the firmware exit,
reserve protected kernel ranges, build own page tables and page-fault
isolation; K1 own
domain/IPC/handle enforcement using canonical Koschei Library decisions.
Issue #331 tracks these requirements.

# Koschei Server K0.2 — UEFI ExitBootServices and small physical-page pool

Status: DEVELOPMENT BOOT PROTOTYPE, NOT A COMPLETE OPERATING SYSTEM.

## Customer target
Koschei Server must ultimately boot on x86-64 hardware and run Koschei
runtime/Library workloads without Windows, Linux, BSD or another hosted OS.
The present entry point uses UEFI GetMemoryMap, validates all memory descriptors,
rejects zero/unaligned/overflow/overlapping ranges, and plans a 16-page
64 KiB candidate solely from conventional memory above 1 MiB.
The plan does not allocate/write those pages while firmware owns memory. K0.2
then calls ExitBootServices using the exact firmware memory-map key, with
up to three bounded retries on EFI_INVALID_PARAMETER. Only AFTER confirmed
success, the kernel activates its own 16-page physical memory bitmap and
writes/reads two distinct 4KiB pages in QEMU's current identity mapping.
It then releases both pages; no BootServices call occurs after handoff.
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
   KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED
   KOSCHEI-KERNEL K0 PAGE-POOL-OWNED
   KOSCHEI-KERNEL K0 HALT-NO-POLICY
4. QEMU debug-exit code 33; a timeout or fabricated file is not a pass.
5. CI artifact binds transcript hash, source revision and toolchain versions.

## Honest limits
No Koschei-owned page tables/MMU, page-fault handler, interrupts,
scheduler, storage, network, isolated processes or Koschei sealed-MIR runner
exist here. UEFI firmware remains an external physical trust input.
The prototype is x86-64/QEMU-focused, not proof of booting physical devices,
and cannot yet host customer applications or claim zero attack risk.

Next: K0.3 replace firmware-provided identity mappings with Koschei-owned
page tables; add page-fault/privilege isolation and page ownership discipline
beyond a limited 16-page demonstration. K1 own
domain/IPC/handle enforcement using canonical Koschei Library decisions.
Issue #331 tracks these requirements.

## Security and platform limitations of K0.2

This is still NOT a production OS or hardened kernel. In particular:

- UEFI firmware is still required for startup. On QEMU OVMF, the observed
  identity mapping permits safe access to the chosen ConventionalMemory
  pages after ExitBootServices, but this cannot be assumed on every x86-64
  machine. K0.3 must build, activate, and verify its own page tables.
- The pool stores an in-process bitmap and supports only 16 pages on one
  core; it does not protect one tenant from another or prevent malicious
  kernel code accessing raw physical memory.
- UEFI runtime services and firmware/CPU trust are not independently
  verified. No Koschei Library/Khar policy gate or MIR executor is present.
- A successful QEMU test proves the actual ExitBootServices call and
  bounded post-exit RAM write/read **only on that emulated machine**.

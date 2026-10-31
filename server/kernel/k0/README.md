# Koschei Server K0.0 — freestanding UEFI boot probe

Status: DEVELOPMENT BOOT PROTOTYPE, NOT A COMPLETE OPERATING SYSTEM.

## Customer target
Koschei Server must ultimately boot on x86-64 hardware and run Koschei
runtime/Library workloads without Windows, Linux, BSD or another hosted OS.
The present entry point uses the UEFI firmware's standard boot protocol and
writes directly to COM1 UART hardware ports without libc or host syscalls.

## Evidence and commands
- Build: bash server/kernel/k0/build.sh OUTPUT_DIRECTORY
- Negative tests: python3 -m unittest discover -s server/kernel/k0 -p 'test_*.py' -v
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
3. Exact serial transcript, three records:
   KOSCHEI-KERNEL BOOT/1 X86_64-UEFI
   KOSCHEI-KERNEL K0 SERIAL-OWNED
   KOSCHEI-KERNEL K0 HALT-NO-POLICY
4. QEMU debug-exit code 33; a timeout or fabricated file is not a pass.
5. CI artifact binds transcript hash, source revision and toolchain versions.

## Honest limits
No ExitBootServices, owned physical memory allocator, page tables, interrupts,
scheduler, storage, network, isolated processes or Koschei sealed-MIR runner
exist here. UEFI firmware remains an external physical trust input.
The prototype is x86-64/QEMU-focused, not proof of booting physical devices,
and cannot yet host customer applications or claim zero attack risk.

Next: K0.1 own validated firmware memory map + page allocator; K0.2 exit
firmware boot services and implement virtual memory/fault isolation; K1 own
domain/IPC/handle enforcement using canonical Koschei Library decisions.
Issue #331 tracks these requirements.

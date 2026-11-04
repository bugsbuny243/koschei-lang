# Koschei Server K0.4 — Own paging and denied-access isolation gate

**Status: DESIGN + DATA-ONLY PTE CONTRACT STAGING. NOT AN IMPLEMENTED MMU OR ISOLATION PROOF.**

K0.3 validates one 16 x 4 KiB conventional-memory candidate after successful
UEFI `ExitBootServices`, claims two distinct pages, probes read/write/zero and
releases them. K0.3 uses the mapping left by firmware, NOT a Koschei-owned CR3.

## Delivered here (staging only)
- `paging_contract.h`: bounded in-memory manifest of up to 16 proposed x86-64
  4 KiB leaf entries for **claimed** K0.3 pool pages.
- Denies unclaimed physical pages, misaligned / non-canonical / low virtual
  pages, the final 64 KiB of canonical virtual space (reserved top guard),
  duplicate physical or virtual aliases, exhaustion and W+X. The guard is a
  proposed layout policy; no live unmapped guard is installed yet.
- Proposed PTEs are supervisor-only. NX use requires explicit independent
  evidence of CPU NX support and EFER.NXE already being enabled. This staging
  implementation takes these as input, **does not verify or activate them**.
- `test_paging_contract.c`: native adversarial checks for leaf policy.
- `paging_model.h` and `test_paging_model.c`: host-tested, bounded
  **logical** PML4/PDPT/PD/PT arrays for one 2 MiB virtual window. A
  transactional preflight demands four separately claimed page-table frame
  addresses, no aliases with data pages, and claimed leaf ownership. The
  arrays are never written into the claimed physical frames; no CPU sees them.
- A 64-bit nonwrapping pool mutation epoch is snapshotted with the first
  leaf. Any subsequent claim or release invalidates that staging plan,
  including release/reclaim to an identical physical address (ABA). Tests
  assert epoch-overflow failure is closed. This is **single-threaded metadata
  preflight only**, not a physical pin, a per-page generation capability,
  atomic concurrency guarantee or safe live page-table reclamation.
- The post-firmware `paging_frame_probe.h` now requires actual CPUID NX
  support and EFER.NXE already enabled, claims four different conventional
  physical frames plus two data frames, serializes the logical hierarchy to
  each physical 4 KiB frame through the firmware's current identity mapping,
  reads back every 64-bit entry, then erases and releases all frames. This is
  a real QEMU guest *physical table-frame roundtrip*, not just a host model.
- No new CPU tables are activated by CR3, and these frames are NOT pinned or
  kept installed after the diagnostic. No IDT/#PF handler exists. Populating
  table bytes while running on firmware mappings is NOT a live MMU mapping.

- `paging_walk.h` and `test_paging_walk.c` evaluate a model-only,
  four-level access walk, predicting absent-page faults, supervisor denial,
  read-only write rejection and NX instruction rejection. Noncanonical VA
  predicts `#GP(0)`, **not** `#PF`. Each result is an expected/software
  decision; there is **no real CPU `CR2` or fault handler receipt**.
  The model checks the snapshot pool mutation epoch, so stale table models
  are rejected even following same-address release/reclaim (ABA).

## K0.4 interrupt preflight added (model only)

- `idt_fault_model.h` and `test_idt_fault_model.c` validate canonical,
  16-byte-aligned kernel ISR addresses, supervisor-only present 64-bit IDT
  interrupt gates and the required #DF (8), #GP (13), and #PF (14) slots.
- The **modeled** ring-0 GDT pair requires a 64-bit code descriptor and
  separate kernel data descriptor with ring-0 privilege. An explicit
  normalized software exception snapshot checks code selector, canonical
  RIP/RSP, 8-byte stack alignment, RFLAGS invariant and vector-specific
  #DF/#GP/#PF error-code contracts.
- The #PF decoder records the **supplied/synthetic** CR2 and P/W/U/RSVD/I
  bits. Reserved-bit violations, unsupported error encodings, unknown
  privilege faults and noncanonical addresses are rejected. Tests compare
  known #PF causes with **actual** `paging_walk.h` model outputs.
- The native test is compiled with C11 `-Wall -Wextra -Werror` and is
  included in `build.sh` and dedicated CI. Passing it proves only host
  safety-model correctness: there is still **no installed kernel IDT,
  actual CPU exception entry, live CR2 capture, owned CR3 transition or
  protected address-space isolation**.

## Next executable acceptance requirements
1. Capture exact page ownership and reserve the loaded PE image, executing
   stack, firmware runtime ranges, ACPI, MMIO/framebuffer and page-table
   frames. Do not reclaim uncertain BootServices pages just because
   `ExitBootServices` returned success.
2. Verify CPUID NX and EFER.NXE; install CR0.WP policy and reject unsupported
   combinations. Never set NX on unsupported hardware.
3. Allocate actual aligned, pinned paging-structure frames from proved
   free pages; construct full four-level x86-64 tables with valid physical
   addresses and non-overlapping, supervisor-only mappings. Explicitly
   preserve instruction pointer, stack, serial I/O and transition trampoline.
4. Install a known-valid GDT/IDT and a page-fault handler **before** switching
   to the new CR3. Mask interrupts during the transition where required.
5. Transition CR3 only after a full preflight of table reachability,
   execute/write permissions, canonical addresses, and reserved ranges.
   Fail-closed on unexpected faults, timeouts or lost UART evidence.
6. Real QEMU/OVMF run must prove a successful owned-mapping write/read, a
   refused unmapped or supervisor-protected access with recorded CR2/error
   code, and a distinct success receipt from the fault handler. Never treat
   triple fault, watchdog timeout or emulator exit failure as success.
7. Add negative tests for overlapping mappings, null mappings, out-of-range
   physical frames, table exhaustion, missing NX/EFER, W+X and duplicate
   ownership. Bind exact source SHA, build/artifact hashes and UART log.
8. Require **both** exact-head dedicated QEMU/OVMF boot CI and full canonical
   Koschei Lang CI SUCCESS; no merge with pending/failed checks. Physical
   x86-64 hardware is a later independent acceptance gate.

## Security boundaries / non-claims
- CPUID, firmware, CPU microcode and real hardware remain external trust roots.
- The current K0.4 staged encoding helper is **not hardware memory isolation**,
  a complete physical memory manager, scheduler, process sandbox, native .ks
  executor, or Khar/Galaxy/Library authorization system.
- The physical frame roundtrip is gated by an actual QEMU UART transcript
  and test-only debug-exit code, but it does NOT establish isolation.
- No security guarantee follows from host-only page entry unit tests.
- Issue #331 remains authoritative for K0 through K4 acceptance.

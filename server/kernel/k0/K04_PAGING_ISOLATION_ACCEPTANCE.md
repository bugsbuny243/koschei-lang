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

## Experimental QEMU-only CPU fault probe (not production isolation)
- `paging_cr3_fault_probe.h` is compiled **exclusively** with
  `KOSCHEI_QEMU_TEST`. It builds a disposable low-1GiB identity-mapped
  PML4/PDPT/PD in three conventional physical frames, installs a minimal
  vector-14 interrupt gate and switches CR3 before deliberately reading a
  high-half unmapped address. Only a real #PF handler with expected CR2,
  hardware error code zero and matching CR3 can emit its distinct marker.
- The identity-mapped lower GiB uses **RWX 2MiB huge pages** to preserve
  firmware-loaded code and stack. This mapping intentionally violates the
  final kernel's W^X and least-privilege requirements. It is an emulator-only
  diagnostic, **never a shipping kernel policy**. Other vectors are absent,
  interrupts are disabled and no general fault recovery is provided.
- A successful test validates only test-environment CR3 activation and a
  single real #PF. It does NOT establish safely reserved protected regions,
  domain-level memory isolation, complete production page tables or
  hardware-platform portability. No production test image contains this
  intentionally permissive transition.

## Promotion gate for the clean experimental branch

The QEMU-only CR3 fault probe has been transferred onto the merged K0.4
preflight baseline with no duplicated squashed-merge commits. It is still
**research staging**, not a candidate production kernel:

- Run all four *real* QEMU/OVMF test modes (unmapped, read-only, NX,
  high-half 4KiB mapping) on the exact staging head and verify strict UART
  transcripts, debug-exit code 33, and release/test PE separation.
- Also require successful exact-head canonical full Koschei Lang CI.
- Do not merge any test-only RWX 0..1GiB identity map or this minimal
  single-vector fault handler into customer production policy. Promotion
  requires tight image/stack/data/firmware/ACPI/MMIO frame reservations and
  active RX/RW+NX separation with robust exception handling.
- A PASS from the previous experimental branch is historical evidence, not
  proof of the current clean staging commit; revalidate after every change.
- Until the above production restrictions are implemented, keep the
  experimental branch unmerged even when both CIs report SUCCESS.

## Transitional QEMU execute-NX tightening (still not W^X)

The separate staging experiment now defaults all 512 lower-1GiB 2MiB
identity PDEs to **RW+NX** and leaves executable only up to eight 2MiB
windows containing the actually executing guest test functions, as checked
transactionally against code addresses. The last 2MiB fault probe slot is
never executable. Host negative tests reject out-of-range addresses,
excessive executable windows, and incomplete configurations before writing
any entries. All four actual QEMU modes must be rerun after this change.

**Residual critical risk:** Each whitelisted executable 2MiB huge-page
window remains **RWX**, possibly containing global data or the stack.
This is a bounded *emulator hardening step*, NOT true kernel W^X and
not least-privilege CPU address-space isolation. No production merge is
permitted until 4KiB PE section-aware mappings distinguish code RX from
data/stack RW+NX, and firmware/runtime/ACPI/MMIO memory is reserved.

## PE32+ 4KiB section W^X metadata preflight (not installed)

The new `paging_pe_section_wx.h` parses a **bounded mapped-image** PE32+
header and section table, without firmware calls, to prepare 4KiB page
classes: executable+read-only RX, read-only NX, writable+NX and header NX.
It rejects malformed PE offsets and section spans, page-level overlap,
unreadable sections and W+X section permissions, without modifying output
on failure. The native adversarial fixture suite exercises boundary and
overlap cases; the existing host PE verifier also fails closed on actual
linked release and emulator EFI artifacts with unsafe section tables.

**Not installed:** This does not yet fetch LoadedImageProtocol in the guest,
pin the image and stack, split active 2MiB identity mappings into 4KiB PTs
or apply section permissions to a CPU-active CR3. The helper is a metadata
contract rather than W^X execution evidence. In particular, it does not
prevent aliases through currently writable executable huge pages.

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

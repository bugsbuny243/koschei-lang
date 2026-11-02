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
  kept installed after the diagnostic. No production IDT/#PF handler exists. Populating
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

## Dedicated real CPU #PF diagnostic, *still under firmware CR3*

- `cpu_pf_guest_probe.h` is included **only** in the third
  `BOOTX64-PF.EFI` QEMU diagnostic image. Neither the release EFI nor
  standard eight-record QEMU EFI contains this path.
- After `ExitBootServices` and the existing physical-table roundtrip,
  the diagnostic disables maskable interrupts and loads a separate minimal
  IDT whose #PF vector is a real x86-64 exception entry. It leaves the
  firmware-installed GDT and CR3 in place.
- The CPU attempts to read canonical address `0x0000400000000000`.
  The handler captures **hardware** `CR2`, the CPU-pushed error code,
  faulting RIP and CS, and returns to a fixed recovery instruction.
  Only a single exact non-present supervisor read fault (error code 0) with
  unchanged CR3 can emit the positive UART record.
- An independent second OVMF boot verifies the exact serialized CR2/error
  receipt and QEMU debug-exit status 33. An absent fault, wrong error,
  unexpected exception, fabricated transcript, triple fault or timeout
  **never counts as success**. The UART and toolchain/artifact digests are
  preserved in CI evidence.
- **Security limitation:** this is a real CPU #PF, **not** an owned-CR3
  transition. The sentinel is assumed unmapped in the supported QEMU/OVMF
  profile, and the live address space is still firmware-provided. This
  does not establish memory isolation or safe production exception handling.

## Proposed owned-CR3 transition manifest preflight (software-only)

- `cr3_transition_preflight.h` and `test_cr3_transition_preflight.c`
  introduce a **read-only, freestanding C11** model of the prerequisites
  for writing a new CR3. The validator never executes `mov %cr3` and
  does not construct, pin or install actual paging structures.
- The candidate includes four distinct, claimed and identity-reachable
  table frames; a frozen allocator mutation epoch; and a bounded mapping
  manifest with supervisor-only permissions, W^X, no physical/virtual
  aliases and per-page physical provenance checks.
- The manifest must cover the **whole declared live code region** (RIP,
  transition trampoline, #PF/#GP/#DF entries), the **whole stack**, IDT
  and GDT ranges. All critical firmware regions must have identity
  translations and explicit non-pool reservation declarations.
- A software CPU-state snapshot requires ring-0 CS, CR0.PE/PG/WP,
  CR4.PAE without LA57/PCIDE, EFER.LME/LMA/NXE, CPUID NX support and
  interrupts disabled. Missing pages, forged reservations, W+X,
  user mappings, CR3 aliasing, stale pool claims and overflow fail closed.
- A successful synthetic test proves **only logical consistency of
  caller-supplied inputs**. Reservation declarations are not verified
  against the final UEFI memory map. No physical pin, CPU-state
  attestation or on-chip mapping safety proof is implied. The current
  sparse high-half `paging_model.h` tables still cannot serve as a live
  replacement CR3 because they do not map the executing EFI code,
  stack, IDT/GDT or trampoline.
- **Remaining before any CR3 write:** bind exact loaded-image/stack/GDT/
  IDT/trampoline ranges to a fresh validated firmware map, reserve
  runtime/ACPI/MMIO ranges and the identity-to-high-half transition,
  materialize the complete four-level hierarchy in pinned frames,
  compare live register readings and loaded table bytes against the
  manifest, prove no W^X or unexpected aliases, then run an independently
  checked QEMU transition and denied-access receipt. No change to
  `uefi_main.c` or its boot-path CR3 instruction is made by this stage.

## Final UEFI descriptor provenance correlation (model-only)

- `cr3_firmware_map_provenance.h` validates a *caller-supplied* final
  `GetMemoryMap` snapshot with the existing strict memory-map validator
  and an explicit `ExitBootServices` success argument. The candidate
  allocator's entire 16-page range must match the planner's **same**
  conventional-memory descriptor selection.
- The 4 claimed CR3 structure frames must each fall within conventional
  memory. Critical IMAGE reservations must lie wholly inside a single
  `EfiLoaderCode` or `EfiBootServicesCode` descriptor; STACK, IDT and
  GDT reservations must lie inside `EfiLoaderData` or
  `EfiBootServicesData` descriptors. Runtime-marked descriptors, ACPI,
  MMIO, missing pages, split reservations, overlaps and unknown types
  fail closed. This is additionally conditioned on the existing synthetic
  CR3 manifest preflight.
- `test_cr3_firmware_map_provenance.c` exercises legal descriptor
  types and hostile type substitutions, relocation, truncation, runtime
  flags, spoofed code addresses, stale allocator epochs and overlapping
  global maps; the dedicated K0 CI compiles and executes the test under
  C11 strict warnings.
- **Limit:** a matching descriptor type does *not* attest that a
  caller-declared physical address actually contains the loaded PE image,
  current stack or active IDT/GDT. The `exit_boot_services_succeeded`
  flag and snapshot are inputs; independent live CPU reads, loaded-image
  protocol provenance, buffer integrity and ownership pinning are still
  required. This stage neither writes CR3 nor exercises new mappings.

## Actual guest CPU register snapshot (isolated QEMU image only)

- Before the real #PF diagnostic installs its temporary IDT, the guest
  disables maskable interrupts and **reads** CR0, CR3, CR4, IA32_EFER,
  RFLAGS, CS, GDTR, IDTR, RIP and RSP, and verifies CPUID NX support.
  This is implemented in \`live_cpu_observation.h\`, included **only**
  in \`BOOTX64-PF.EFI\`, never the release or ordinary QEMU binary.
- A fail-closed predicate checks CR0.PE/PG/WP, CR4.PAE, no LA57/PCIDE,
  EFER.LME/LMA/NXE, ring 0, IF clear, aligned existing CR3, canonical
  captured addresses and descriptor-table presence.
- The guest emits the **observed 64-bit values** as one UART record before
  its hardware CR2/#PF record. The serial verifier parses each exact-width
  field and rechecks register invariants; adversarial fixtures reject
  missing/duplicate records, tampered bits, malformed values and mismatch.
  A real OVMF exit code 33 and both UART receipts are required.
- **Limits:** these are QEMU CPU observations, not cryptographic
  attestations or independently trusted inputs. A valid register mode
  cannot prove that live RIP/RSP/GDTR/IDTR virtual addresses map to the
  physical pages proposed by the new-CR3 manifest. No owned CR3 is
  installed, no firmware mapping provenance is proven by register reads,
  and no memory isolation guarantee follows.

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

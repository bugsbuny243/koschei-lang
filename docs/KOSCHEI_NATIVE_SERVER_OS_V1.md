# KOSCHEI NATIVE SERVER OS V1 — No Host Operating System

**Status: architecture acceptance contract / NOT IMPLEMENTED.**
**Product constraint:** a customer production Koschei Server MUST NOT need, boot,
host, embed or depend at runtime on Windows, Linux, BSD, macOS, a Linux
container, a Windows service, a Go runtime, or a Python runtime.

Koschei Lang semantics and all security policy authority remain with
Koschei's own compiler, sealed MIR, runtime transition contract,
Khar/Galaxy and Library/Universe. This document introduces no second
language constitution or parallel source of authorization.

## Precise terminology

- **Koschei Lang:** source language, sealed semantic authority and toolchain.
- **Koschei Library / Universe:** capabilities, memory/resource policy,
  Khar, Galaxy, Matrix, Hara, Aevra/Veyra, Shi/Vor/Thal/Nur, Sathra,
  Continuity and Strange; policy is owned here, not outsourced.
- **Koschei Kernel:** **NEW, currently missing** freestanding, privileged
  hardware execution core. Must initialize interrupts/MMU, manage memory
  isolation and page tables, scheduler, device access and isolated domains.
  It must *enforce* Library-created authority at unbypassable trap/IPC
  boundaries without inventing a second policy.
- **Koschei Native Runtime:** **NEW production target** consuming canonical
  sealed MIR/state transitions without delegated Python/Go/Linux semantics.
- **Koschei Server:** **NEW product**: bootable, standalone server
  distribution containing only the above runtime, kernel, own drivers and
  separately signed release payloads.

The existing `KOSCHEI_PHYSICS_KERNEL_V1.md` is a **semantic law registry**,
NOT a CPU kernel. Existing Go MIR backend, Linux seccomp capability broker,
Linux sealed memfd runner, Docker and Python bootstrap are **non-authoritative
host compatibility / development surfaces**. They DO NOT satisfy this target.

## Proposed execution boundary

```text
. ks customer projects
          |
          v
Koschei Library / Universe   (one canonical Khar/Galaxy authority)
          |
          v
sealed MIR -> native Koschei execution/state-transition engine
          |
          v
Kernel-enforced capability handles and isolated IPC
          |
          v
Koschei Kernel: address spaces / IRQ / scheduler / MMU / device controls
          |
          v
physical x86_64 server -> CPU / RAM / network adapter / storage
```

The kernel has a small auditable trusted computing base and **no ambient
application authority**. Userspace receives only narrowly scoped,
non-forgeable kernel handles whose meaning is bound to canonical
Library-issued policy. Hardware operations require explicit kernel
capability checks; no fallback path is allowed to call raw host OS APIs.
No hosted libc/syscalls may be necessary for the production image.

## Independent boot acceptance gate (P0)

1. **Freestanding build artifact:** produced `koschei-server.efi` or a
   Koschei-owned alternative boot format. The target explicitly disables
   hosted OS ABI and accidental libc/Go/Python linkage.
2. **Cold boot:** boot a test physical x86_64 machine (or an emulator for
   initial reproducibility) DIRECTLY into a Koschei-controlled boot path;
   there must be no Linux/Windows/other OS as a prerequisite.
3. **Serial proof:** print a stable `KOSCHEI-KERNEL BOOT/1` diagnostic
   through an explicitly implemented own console driver, with CPU/boot
   information; halted kernels return a bounded error code. Boot text
   alone is **not** proof of security or product maturity.
4. **Memory isolation:** kernel-only memory is inaccessible to customer
   application domains (mandatory MMU page-table and fault tests).
5. **Capability isolation:** a customer domain with no file/network/device
   capability cannot access the resource even through raw IPC/trap calls.
6. **Sealed MIR:** the target refuses source/AST/unsigned or stale MIR
   bypassing canonical compiler admission. No legacy Python/Go semantic
   fallback in the production image.
7. **Epoch-bound authority:** privileged effect checks use one
   Library/Continuity decision and are checked AT hardware/device effect
   boundary, not only by periodically polling a process.
8. **Provenance:** verify signed release, measured kernel/runtime and
   hardware-supported monotonic/rollback-resistant trust as *separate*
   gates. Do not treat a signature in the same replaced file as a trust root.

## Minimal platform cut — what to implement first

**K0: independent boot and trusted hardware boundary**
- Kernel entry, bounded memory map, physical/virtual memory manager, page
  fault handler, serial logging and panic/fault shutdown.
- First freestanding test `BOOT -> memory allocation -> serial proof ->
  deny invalid memory access`.
- No customer app, network, file storage or project sales claim in K0.

**K1: Koschei domains, IPC and capability handle table**
- Address-space isolation, one scheduler, kernel handle generation/check,
  typed IPC, fail-closed invalid/expired/cross-tenant capability tests.
- Canonical Library may define authority; kernel checks hardware access.

**K2: Koschei Native Runtime**
- Execute a small, statically specified subset of sealed Koschei MIR
  without Python/Go/Linux/host syscalls; independently verify deterministic
  results and adversarial denial against existing reference fixtures.

**K3: server I/O and persistence**
- Own network adapter drivers, bounded protocol stack, storage driver,
  crash-consistent journal and secure update/rollback policy. Until
  hardware and protocols are validated, deny unsupported devices.

**K4: complete multi-tenant Koschei Server**
- Quotas, deployment isolation, migration, application launch/termination,
  Library/Khar gate as the sole effect owner, measured boot, update signing,
  recovery tooling, audit/evidence and hardware red-team review.

## Engineering constraints

- Production target semantics should be authored in `.ks` as the language's
  freestanding backend becomes capable; unavoidable CPU reset, trap,
  firmware handoff and early hardware assembly must be minimal, separately
  reviewed **mechanisms**, not independent policy authority.
- Test and bootstrap toolchains may temporarily run on developer machines;
  those hosts are **not** customers' Koschei Server runtime and must be
  removed from production artifact dependencies.
- Hardware/firmware and CPU microcode remain third-party physical trust
  inputs on commodity servers. Removing another operating system does NOT
  prove that attacks or dependency risk are zero.
- Never label an implementation production-ready merely because it boots in
  an emulator. Independent real-hardware testing, isolation proof and
  sustained recovery evidence are separate release gates.

## Current repo evidence and missing work

**Existing:** Koschei language tooling, sealed MIR, Khar/Galaxy/Continuity
and Library partial invariants; Go-native compatibility backend;
Linux-local native broker/seccomp and sealed worker. Those parts are useful
as *reference behavioral tests* but not as the final operating system.

**Not in the repo at this checkpoint:** a bootable Koschei-owned kernel,
freestanding Koschei target compiler, memory manager, own NIC/storage
drivers, hardware scheduler, independent measured secure boot integration,
and proved device-level privileged-effect gating.

**Immediate next engineering deliverable:** K0 real boot proof with a
freestanding artifact and reproducible emulator/real-hardware evidence.
Do not attempt K2/K4 marketing claims before K0/K1 work. Keep runtime
and Library canonical semantic ownership intact throughout migration.

## Acceptance rule

Koschei Server may be described as `NO_HOST_OS` **only** when the binary
boots and executes required own runtime services without another OS at
runtime; the release manifest inventories dependencies and the test lab
retains an exact-hash boot transcript. Claiming `ZERO_RISK` or
`ZERO_ATTACK_SURFACE` remains prohibited: neither is a technically
demonstrable absolute guarantee.

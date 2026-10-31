# Koschei Server K0.2 — Firmware handoff and physical-page ownership

**Status: design gate. NOT implemented or tested.**

## Binding requirements

- The final Koschei Server boots its own kernel/runtime. Windows, Linux,
  BSD, containers, Python and Go are NOT part of the customer system.
- Khar/Galaxy and Koschei Library remain the one source of security
  authority. CPU and firmware transition machinery must not define an
  alternate authorizer.
- K0.1 verifies a bounded UEFI memory-map and selects a 16-page candidate
  **without accessing or allocating it** while firmware owns the map.
- Only after a successful UEFI ExitBootServices handoff may a Koschei
  physical-page ledger mark eligible pages as owned.

## K0.2 acceptance sequence

1. Validate firmware system-table and BootServices ABI layout.
2. Obtain a complete memory map into a bounded pre-reserved buffer, including
   its MapKey, DescriptorVersion and DescriptorSize.
3. Reject malformed, overlapping, wrapped, or unavailable/reserved ranges.
   Never treat BootServices/RuntimeServices/MMIO/ACPI/reserved/unknown
   descriptors as conventional free memory.
4. Obtain a fresh MapKey immediately before ExitBootServices. Perform no
   intervening firmware operation that may mutate the map.
5. Call ExitBootServices with the loaded image handle and fresh MapKey;
   handle the firmware-specified retry case by obtaining a fresh map/key.
   Any other failure denies the handoff. Do not claim ownership unless the
   firmware reports success.
6. Preserve kernel image, boot stack, persistent firmware runtime regions,
   framebuffer/ACPI ranges and required page tables. Never reassign
   resources still needed for boot or critical interrupt handling.
7. Initialize a bounded own physical-page ledger only for ranges proved
   available; track page ownership and reject duplicate/exhausted allocation.
8. Demonstrate isolated memory read/write/zero probes **only on owned pages**
   in a QEMU guest; capture exact-hash UART evidence and emulator outcome.
9. Establish an explicitly owned page table and page-fault handler before
   declaring virtual-memory isolation. Firmware's mapping alone is not
   evidence of Koschei address-space isolation.
10. Run negative tests (stale MapKey, missing BootServices, malformed/short
    descriptor, overlapping memory, no conventional pages, exhaustion,
    repeat allocation, interrupted transition). The test harness must fail
    closed and must not convert a timeout into success.

## Test evidence

- Same-head canonical full CI and dedicated QEMU/OVMF cold boot both pass.
- Binary and serial output hashes, firmware/toolchain identity, transition
  receipt and source SHA all bound to the exact candidate commit.
- Physical hardware is a later separate acceptance requirement, not claimed
  from an emulator.

## Non-claims

A successful ExitBootServices handoff does NOT prove a protected kernel, own
memory manager, independent secure boot, no firmware vulnerabilities, own
device drivers, canonical .ks execution, or zero attack risk. Those remain
separate acceptance gates under issue #331.

## Relationship to K0.1

K0.1 on PR #333 is map validation and **planning only**, with firmware
BootServices still active. Do not merge or advertise this K0.2 gate as
implemented before a reproducible executable handoff and memory evidence
exist.

# Strange Verified Native Build V1

Status: **builder-side pinned-Go offline compilation prototype; NOT production trust proof**

Earlier Strange native attestation can MAC arbitrary native bytes supplied by
its caller. That low-level issuer is not by itself an authenticated
source-to-binary build chain. This module narrows the **trusted producer path**:

1. Verify the absolute Go executable path against an explicit 64-character,
   lowercase SHA-256 supplied by the trusted builder policy.
2. Project sealed canonical `MirGraph` into epoch-scoped MIR-Go using a
   Trust Plane-supplied seed, Veyra digest, deployment and Continuity window.
3. Compare source bytes against their exact builder receipt.
4. Compile inside a fresh ephemeral Go module, without module network access,
   ambient Go flags/workspaces, cgo, or externally supplied Go build flags.
5. Refuse failed, empty, missing or timed-out native output. Reject if the
   120-second Continuity window expires or changes during compilation.
6. Only **after those checks** issue the existing scoped native HMAC
   attestation for the actual compiled binary bytes.
7. MAC a second builder-only provenance receipt binding the pinned Go executable
   digest, canonical source digest, native-byte digest, scope binding and native
   attestation MAC. `assert_authenticated` checks the receipt and exact native
   bytes; it **does not** elevate this record to execution authority.

The function returns a **trusted-builder-only** binary and an authority-free
attestation. No public `ks build` path is modified. The binary is deliberately
excluded from the result's Python `repr`, but remains present in memory.

## Trust boundaries and missing controls

- The pinned Go launcher SHA-256 **does not pin its internal compiler/linker,
  standard library, plugins, kernel, firmware, or build host**. A real supply
  chain requires full hermetic toolchain/container provenance, reproducible
  builds and independent verification of artifacts.
- A compromised builder can replace the executable path after hashing it;
  filesystem/OS confinement, immutable files, signing and controlled builder
  lifecycle are still external prerequisites.
- The Trust Plane seed, Veyra digest, attestation key, epoch source and clock
  are supplied to Python by the trusted caller. This is **not proof** that
  they came from independent physical trust roots. The root seed must never
  come from public CLI flags, source, environment or observable metadata.
- Existing low-level `issue_strange_native_attestation_v1` remains available
  and can attest arbitrary bytes if a caller supplies the key. Production
  architecture must make the key non-exportable and expose only the verified
  producer to authorized issuers; Python import discipline is not security.
- No running process measurement is performed. A checked binary on disk does
  not prove the bytes currently executing inside a process.
- No automatic 120-second deployment swapping, safe in-flight migration,
  durable external anti-rollback anchor, HSM wallet custody or Khar/Sathra
  privileged-effect authorization is implemented.
- All returned evidence is `authority=False`: not a signing credential.

## Tests

`python -m unittest discover -s tests -p 'test_strange_verified_native_build_v1.py' -v`

Includes a real offline Go compilation and native output parity where Go is
available; rejects wrong compiler hash, malformed timeouts, modified native
bytes, compiler failure, compile timeout and epoch expiry mid-build.

Related: `STRANGE_NATIVE_ADMISSION_V1.md`,
`STRANGE_REPRESENTATION_EPOCH_V1.md`, issue #317.

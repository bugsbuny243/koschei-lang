# Strange Sealed Linux Native Launch V1

**Status: Linux-local, opt-in, prelaunch integrity prototype. NOT protected execution.**

Koschei's Strange builder and native admission modules verify a source/binary
hash, epoch and deployment identity. That doesn't by itself prevent the
executable *path* from changing between validation and a subsequent
`subprocess.run(path)`.

This module narrows that gap on supported Linux kernels:

1. Verify the supplied native bytes, exact deployment/Veyra/MIR, attestation
   and locally durable current 120-second Continuity epoch.
2. Copy the exact supplied bytes to a fresh anonymous Linux
   `memfd_create(MFD_CLOEXEC|MFD_ALLOW_SEALING)` descriptor.
3. Apply and read back `F_SEAL_WRITE|F_SEAL_SHRINK|F_SEAL_GROW|F_SEAL_SEAL`.
   Rehash the sealed descriptor to prove bytes match the original.
4. Re-verify native attestation and the current epoch immediately before
   launching `/proc/self/fd/<fd>` with `pass_fds`.
5. Spawn with no extra argument/environment forwarding, a private temporary
   working directory, stdin closed and an execution timeout.
6. Return a non-authoritative, read-only *local observation* containing exit
   code and output; output is hidden from Python `repr`.

This mechanism was independently exercised using a local Go binary executed
from a sealed memfd on Linux. The CI test builds and runs a Koschei-generated
Go binary from a sealed MIR to exercise the actual path.

## Critical safety boundaries

- The kernel's seal helps protect the **staged inode** against writes during
  launch. It is **not** proof of a trustworthy kernel, container, firmware or
  user-space process. Other code on the host can bypass this Python entry
  point or obtain privileges by other routes.
- A process that starts in a current 120-second window may continue **after
  expiry**. This module does **not** implement process kill, automatic binary
  swapping, in-flight request handoff or at-effect epoch fencing.
- An already-executing process can retain data in memory, emit outputs,
  perform network activity, invoke dangerous operations or load other code.
  The launch path is **not** a sandbox or signer policy. No hot wallet or
  secret store must be entrusted to this component alone.
- Attestation keys and the time reader are still caller-supplied. They are
  **not independent hardware trust roots**; the native verifier cannot
  authenticate a caller who already controls those bytes.
- The isolated execution context, mandatory signer controls, source-to-binary
  provenance, trusted monotonic time, rollback fencing and production audit
  remain separate obligations tracked in issue #317.
- This module is Linux-only. On unsupported hosts the correct behavior is to
  refuse or not use the optional feature; public `ks build` is unchanged.

## Tests

`python -m unittest discover -s tests -p 'test_strange_sealed_native_launch_v1.py' -v`

Covers real Go execution, kernel file seals, exact native bytes, tenant/Veyra
mismatch, T=120 expiry, stale epoch, invalid run bounds and copy-time expiry.

`StrangeSealedNativeRunV1.authority=False` always; this is **never**
execution authorization for Khar, Sathra, a Library secret or a private key.

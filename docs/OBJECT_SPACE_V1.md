# Koschei Object Space v1

Status: **foundation / experimental; stacked on Native Reality graph v1**

Object Space v1 replaces semantic project paths with a two-name canonical storage surface:

```text
<ProjectRoot>/
  k0
  k1/
    <256-bit opaque locator>
    <256-bit opaque locator>
    ...
```

There is no canonical `src/`, `main`, `module`, `package`, `tests`, `config`, `build`, `dist`, `target`, `vendor`, `lib`, source filename or source extension.

`k0` is not a renamed manifest or entry file. It is a sealed authority aperture. `k1` is not a renamed source directory. It is a semantic-free physical cell field.

## Three identities are deliberately separated

### Canonical object identity

A random object id is the stable semantic identity across storage epochs. It is not a filename and is not visible in the canonical filesystem listing.

### Physical locator

Each stored object has a random 256-bit lowercase-hex locator under `k1`. Locators carry no role. A storage epoch rotation assigns every authoritative object a fresh locator while preserving canonical object identity and source bytes.

### Developer meaning

Human labels such as `Order Intake`, `Settlement` or `Identity Gate` are not canonical filenames. A future authorized workspace/session may render such labels, but physical storage does not use them as authority.

The invariant is:

> filesystem listing != architecture listing

## Sealed root aperture

`k0` contains externally sealed bytes. The plaintext root capsule contains project id, reality epoch, canonical root object id, the object-id -> locator/digest authority table, crypto-profile binding and secret graph/topology bytes. None of these fields are written as plaintext project metadata by Object Space v1.

`k1` object payloads are also externally sealed. Their associated-data binding includes project id, epoch, object id and physical locator, so ciphertext copied into another slot/context is not accepted by a conforming provider.

Object Space v1 ships no default encryption implementation. The runtime must supply an audited provider implementing the crypto-provider contract. There is no home-grown crypto fallback.

## Crypto agility and post-quantum profile

The initial high-assurance profile identifier is `koschei-pq1`:

- at-rest AEAD: AES-256-GCM
- key establishment: ML-KEM-1024
- primary signature: ML-DSA-87
- backup signature family: SLH-DSA
- digest family: SHA3-512

These identifiers describe requirements for an external audited provider; the compiler does not implement these algorithms itself.

The design intentionally treats algorithm choice as a profile rather than a permanent language primitive. NIST has standardized ML-KEM in FIPS 203, ML-DSA in FIPS 204 and SLH-DSA in FIPS 205, and its current migration guidance emphasizes crypto agility. AES remains standardized by FIPS 197; authenticated-encryption use is delegated to the provider rather than reimplemented in Koschei.

No claim is made that a system is "quantum proof" merely because these identifiers exist. Real assurance requires a correct provider, key custody, parameter/profile review, migration capability and executed interoperability/security tests.

## Authenticator-style temporal access

Object Space uses a separate machine temporal-access handle. The default slot is 30 seconds.

The handle is bound to:

- external temporal key;
- project id;
- reality epoch;
- exact time slot;
- access-policy period.

A handle from another project, another epoch or the next time slot fails closed.

This is intentionally **not** TOTP and not a human OTP. It is a short-lived project-access binding.

Crucially, source bytes are not rewritten every 30 seconds. Rewriting a million-line project on every Authenticator tick would destroy scalability and deterministic build behavior. Instead:

- temporal access handles rotate every slot;
- physical locators rotate on reality/storage epoch transitions;
- canonical object identity remains stable.

## "Event-horizon / void" meaning

The project uses "void" only as a defensive architectural term. It does not mean hack-back, deletion of an attacker's machine or destructive retaliation.

Without the trusted external crypto provider/key custody and a valid temporal context, a canonical filesystem listing should provide no semantic role map. The attacker may see `k0`, `k1`, opaque cell count and ciphertext sizes, but not authoritative source names, root role, module names, test roles, dependency labels or plaintext graph topology from the canonical storage format.

Unreferenced 256-bit cells are inert: only cells referenced by the sealed `k0` authority table participate in the loaded project. A non-opaque filename under `k1` fails closed.

## Epoch rotation

`rotate_object_space_epoch()`:

1. verifies the current project/epoch and temporal handle;
2. opens all authoritative objects through sealed `k0`;
3. assigns fresh 256-bit locators to every object;
4. reseals every object with next-epoch associated data;
5. writes and fsyncs the complete next physical set;
6. seals the next `k0` root capsule;
7. atomically switches `k0` from a temporary opaque `k1` cell;
8. fsyncs the project root;
9. cleans previous object cells best effort;
10. issues a handle bound to the new epoch.

The previous temporal handle cannot authorize the next epoch.

If cleanup is interrupted after the root switch, old opaque cells may remain physically present but are non-authoritative. They are reported as unreferenced cells, not silently admitted into the program graph.

## Current leakage / non-claims

Object Space v1 reduces semantic filesystem reconnaissance but does not claim perfect concealment. An observer can still infer:

- that a directory appears to use the `k0/k1` format;
- approximate sealed object count;
- ciphertext sizes;
- filesystem timing and mutation patterns;
- stale/unreferenced physical cells that remain after interrupted cleanup.

Padding, fixed-size cell chunking, cover traffic/decoys and stronger traffic-analysis resistance are later contracts.

This slice also does not yet:

- wire the compiler/parser directly to Object Space;
- replace legacy Koschei grammar;
- provide the production ML-KEM/ML-DSA/SLH-DSA/AES-GCM provider;
- provide hardware-backed key custody;
- prove side-channel resistance;
- protect a compromised authorized process that already holds provider authority;
- claim an unbreakable system.

## Acceptance gates in this slice

Tests require:

- canonical root listing is exactly `k0`, `k1`;
- every `k1` authoritative filename is 256-bit lowercase hex with no extension;
- semantic source/topology markers and canonical object ids are absent from raw project bytes under the test provider;
- current temporal handle works only in its exact time slot/project/epoch;
- storage epoch rotation changes every authoritative physical locator;
- old epoch/handle cannot reopen the new reality;
- non-authoritative opaque cells remain inert;
- semantic/non-opaque names injected under `k1` fail closed;
- provider profile mismatch fails closed;
- `k0`/`k1` pass the Koschei originality gate only with explicit design provenance.

## Next slices

1. adapt authenticated Native Reality graph bytes into the sealed `graph_secret` field and stop persisting the old plaintext/HMAC graph capsule;
2. connect `ks check/run/mir/caps/build` to Object Space through a trusted session broker;
3. add an audited provider binding for the `koschei-pq1` profile without adding a home-grown cryptographic implementation;
4. add length-hiding fixed-size object cells/padding and optional inert cover cells;
5. migrate the source grammar itself away from the legacy Rust/Go-shaped surface;
6. make Object Space the default project reality only after real CI/security gates execute.

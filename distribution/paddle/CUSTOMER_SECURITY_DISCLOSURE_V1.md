# Koschei Lang — Customer Security Disclosure v1

## Evidence-backed product statement

Koschei's compiler rejects code paths that request disk, network, environment, or process effects when the required capability is unavailable in that scope. The Paddle release smoke gate requires the known unauthorized supply-chain fixture to remain rejected with `KS2401`.

This is a **compiler authority guarantee for covered language paths**, not a claim that the current runtime is physically isolated from the host.

## PROTECTS AGAINST

- Accidental or dependency-originated requests for covered effects that are absent from the admitted capability scope.
- Silent capability expansion that would otherwise pass ordinary syntax/type checks.
- Distribution of a modified production binary when the buyer verifies it against the independently published release key/fingerprint.

## DOES NOT PROTECT

- Host/kernel compromise.
- A malicious compiler/build process.
- Arbitrary native/foreign code outside the Koschei capability model.
- Runtime ambient authority that remains reachable through compatibility execution paths.
- Theft of credentials already exposed to another process.
- Every possible software vulnerability, side channel, or supply-chain attack.

## ASSUMPTIONS

- Source passes the Koschei compiler checks actually used by the distributed version.
- No unverified native/foreign escape path is treated as capability-safe.
- The buyer verifies the production artifact before use.
- Runtime/platform requirements are satisfied.

## FAILURE MODE

If a requested effect cannot be represented and proven under the strict supported execution path, production tooling must fail closed rather than silently route through a backend with broader ambient host authority.

## Current boundary

Koschei remains pre-1.0. Compile-time capability enforcement is real and testable. Full P0 physical runtime custody — a separately confined execution capsule with narrowly scoped capability brokerage — is **not yet claimed as complete**.

# Koschei Launcher Enforcement v1

**Status:** active Trust Plane sub-contract. Planning/readiness only; no process execution authority yet.

A signed deployment authorization and a trusted launch permit are still not a
sandbox. Koschei must not claim that an application is confined until a concrete
platform implementation has actually applied and evidenced the required OS
boundaries.

This contract defines the boundary between **authority eligibility** and **real
runtime enforcement**.

## 1. Inputs

The enforcement planner consumes:

- a valid `koschei.trusted-launch-permit.v1`;
- the exact `koschei.static-capability-request.v1` produced from compiler
  capability analysis.

Both objects are independently revalidated from their contents. A Python object,
constructor path or valid-looking SHA string is not trusted by itself.

The planner recomputes:

- the launch permit digest;
- static grant canonicalization;
- launcher capabilities derived from grants;
- the static capability-request digest.

If these identities differ, no enforcement plan is produced.

## 2. Exact scopes survive into enforcement

The launcher does not collapse source authority into only broad flags such as
`net.io` or `disk.read`.

The enforcement plan retains exact compiler grants:

`(domain, scope, read_only)`

Examples:

- `net / https://api.example`
- `disk / /srv/koschei/data / read_only`
- `env / KOSCHEI_PUBLIC_`
- `process / /usr/bin/approved-worker`

A platform adapter that can block generic network access but cannot restrict the
actual allowed destination does **not** satisfy `exact_scope_enforcement`.

## 3. Default-deny process boundary

Every enforcement plan requires these invariants:

1. unrequested authority domains are denied;
2. ambient parent-process environment is not inherited;
3. inherited file descriptors are closed except an explicit launcher contract;
4. shell execution is disabled;
5. executable SHA-256 is rechecked immediately before spawn;
6. every requested capability domain and exact scope is enforced.

The plan explicitly records unrequested domains in `denied_domains`.

## 4. Sandbox adapter descriptor

`koschei.sandbox-adapter-descriptor.v1` describes one concrete future platform
adapter and its immutable configuration identity.

It binds:

- adapter ID/version;
- platform;
- configuration digest;
- supported authority domains;
- exact-scope enforcement support;
- default-deny support;
- empty-environment default;
- inherited-FD closure;
- shell disablement;
- executable digest verification at spawn.

A descriptor whose content and descriptor digest disagree is rejected.

## 5. Readiness is NOT runtime enforcement

`evaluate_sandbox_readiness()` can return:

- `KS1960` — descriptor satisfies the declared plan requirements;
- `KS1961` — malformed or tampered plan/descriptor;
- `KS1962` — requested authority domain is unsupported;
- `KS1963` — at least one mandatory launcher boundary is missing.

**`KS1960` is not permission to spawn a process.**

The descriptor is currently a deterministic declaration, not a cryptographic
attestation from a running OS sandbox. Therefore this module deliberately exposes
no `spawn`, `exec`, `run`, or process-creation function.

A future real platform adapter must:

1. construct the platform isolation configuration from the exact plan;
2. independently attest/configure the concrete enforcement boundary;
3. verify executable bytes again at the final spawn boundary;
4. create the process without a shell or ambient authority;
5. return enforcement evidence that can be bound into an execution receipt.

Until such an adapter exists for the target platform, Koschei must fail closed
rather than execute with weaker isolation.

## 6. Why ordinary subprocess isolation is insufficient

Launching a program with a cleaned environment or `shell=False` alone is not a
Trust Plane sandbox. It does not necessarily constrain:

- filesystem paths;
- network destinations;
- child process execution;
- inherited kernel resources;
- platform-specific escape surfaces.

Koschei must not call an ordinary Python subprocess wrapper a sandbox.

## 7. Platform strategy

The first production platform should be chosen explicitly from the actual Koschei
deployment environment. The adapter contract must be mapped to real OS primitives
for that platform and adversarially tested.

If the platform cannot enforce one requested capability scope, the compliant
behavior is to reject the launch or redesign that capability boundary — not to
silently widen authority.

## 8. Required adversarial invariants

Tests preserve at least these properties:

1. exact permit + exact static request builds a scope-preserving plan;
2. unrequested domains are explicit denies;
3. forged permit content is rejected even with a valid-looking digest string;
4. static capability-request substitution is rejected;
5. capabilities inconsistent with grants are rejected;
6. an adapter missing a requested domain is not ready;
7. an adapter missing any mandatory boundary is not ready;
8. descriptor tampering is rejected;
9. plan tampering is rejected;
10. identical readiness inputs produce identical readiness identity;
11. readiness exposes no process-execution method or authority.

## 9. Next step

Before implementing process creation, choose the actual production OS/runtime and
build one concrete adapter against real isolation primitives. That adapter must be
tested with denied filesystem, network, environment, process and inherited-FD
attempts before the project can claim launcher enforcement.

Secret handles, signing brokers and deployment brokers remain separate authority
layers. They must not be smuggled through ordinary source capabilities or sandbox
configuration.

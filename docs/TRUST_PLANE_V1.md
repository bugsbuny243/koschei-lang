# Koschei Trust Plane v1

**Status:** active target contract for the first policy-bound launcher kernel.

Koschei Trust Plane exists to make a compromised developer workstation, CI runner,
dependency, artifact store, or application process insufficient by itself to gain
production authority.

It does not claim that compromise is impossible. It makes authority explicit,
bounded, independently checkable, and fail-closed.

## 1. Authority model

The v1 authority model is deliberately asymmetric:

- an artifact may **request** capabilities;
- a trust artifact manifest binds that request to one exact `policy_hash`;
- the artifact manifest does **not** contain authoritative granted capabilities;
- the authoritative grants come from the trusted launcher's **local policy**;
- the launcher permits execution only when the requested capability set is a
  subset of the locally approved set represented by the bound `policy_hash`.

Changing the local policy changes its hash. An artifact bound to an older or
different policy does not silently inherit the new grants.

This lets the same reproducible build be approved under different environment
policies only by producing an explicitly policy-bound trust manifest for each
approved deployment context.

## 2. Evidence is not deployment authority

Koschei already has:

1. a native build manifest that binds artifact bytes, module lock, MIR,
   compiler and backend toolchain;
2. a reproducibility report;
3. a release proof that proves a byte-identical release candidate.

The release proof intentionally says:

- `authority=release_candidate_evidence_only`
- `owner_approval_required=true`
- `production_integration_allowed=false`

Trust Plane preserves this boundary. A release proof is necessary provenance
evidence; it is not an ambient permission to deploy or execute.

## 3. Artifact identity

A Trust Plane artifact manifest binds:

- `artifact_sha256`
- native `build_manifest_digest`
- `release_proof_digest`
- exact `policy_hash`
- canonical `requested_capabilities`
- its own canonical `manifest_digest`

An artifact byte swap, build-manifest swap, release-proof swap, policy swap, or
request mutation invalidates the launch decision.

## 4. Closed-world capabilities

Trust Plane v1 recognises only a reviewed capability vocabulary:

- `disk.read`
- `disk.write`
- `net.io`
- `env.read`
- `process.exec`
- `secret.use`
- `signing.request`
- `deploy.execute`

Unknown capability names are rejected. There is no wildcard and no implicit
`root`, `all`, or ambient authority.

The vocabulary is intentionally broader than the current language-level
`SystemCaps` domains because the trusted launcher must eventually gate secrets,
signing and deployment authorities that application code must not manufacture.

Adding a capability is a Trust Plane contract change, not a configuration typo.

## 5. Deterministic launch decision

For the same:

- artifact identity,
- build manifest,
- release proof,
- local policy,
- requested capability set,

the v1 evaluator produces the same decision payload and `decision_digest`.

No clock, network call, environment lookup, secret read, subprocess execution or
remote signer is consulted by this kernel.

The kernel currently decides eligibility only. It does not launch a process.

## 6. Fail-closed rules

Launch is denied when any of the following is true:

- a manifest/proof/policy digest is malformed or does not match its contents;
- the release proof does not bind the supplied build manifest and artifact;
- the trust artifact manifest references another build or release proof;
- the policy hash differs from the authoritative local policy;
- a requested capability is outside the local grant set;
- a capability name is unknown;
- supplied launch artifact bytes do not match the authorized artifact digest.

A denial grants **zero effective capabilities**.

## 7. Artifact lifetime vs deployment authorization lifetime

Artifact identity and deployment authorization are different objects.

A reproducible artifact, its build manifest, and its release proof may be
long-lived or non-expiring in v1. They describe **what the artifact is**.

A later deployment-authorization object will describe **whether this artifact may
be deployed now/in this environment/for this operation**. If that authorization
uses `expires_at`, the time limit applies only to the deployment authorization,
not to the artifact itself.

Time-bounded deployment authorization also makes correct clocks an explicit
operational dependency and threat-model assumption. The v1 kernel intentionally
contains no wall-clock dependency yet.

## 8. What v1 does not do

This first slice does not:

- execute the artifact;
- read or inject secrets;
- contact a signer;
- submit a deployment;
- open network or disk access;
- use a remote policy server;
- create short-lived deployment authorization;
- claim OS sandbox enforcement;
- claim hardware-backed key isolation.

Those powers must be added as separate, reviewable authority layers. The kernel
must remain usable as the deterministic decision core underneath them.

## 9. Required adversarial invariants

The test suite must preserve at least these properties:

1. exact artifact + exact policy + subset request can be eligible;
2. artifact byte replacement is denied;
3. policy replacement/tampering is denied;
4. requested capability escalation is denied;
5. release-proof replacement is denied;
6. unknown capabilities are denied;
7. capability ordering cannot change policy/manifest identity;
8. identical inputs produce identical decision identity;
9. a release proof never creates ambient capabilities.

## 10. Next slices

After this kernel is proven, the intended sequence is:

1. **Deployment Authorization v1** — separately signed/bound authorization with
   replay resistance; time bounds only if clock assumptions are accepted.
2. **Trusted Launcher v1** — enforce the decision at process creation with an
   explicit zero-authority default.
3. **Secret handles** — code receives use-authority, not raw secret values where
   avoidable.
4. **Signing/deploy brokers** — application code cannot hold raw deployment or
   signing authority.
5. **Execution receipt** — bind artifact, policy, authorization, effective
   capabilities, launcher identity, and result into an auditable receipt.
6. **Compromise laboratory** — CI runner swap, artifact swap, dependency
   compromise, developer-machine compromise, exfiltration attempts, replay and
   policy substitution.

The Trust Plane is successful only when compromising one layer does not silently
collapse all other authority boundaries.

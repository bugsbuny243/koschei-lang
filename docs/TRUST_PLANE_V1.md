# Koschei Trust Plane v1

**Status:** active target contract for the first policy-bound launcher kernel.

Koschei Trust Plane exists to make a compromised developer workstation, CI runner,
dependency, artifact store, or application process insufficient by itself to gain
production authority.

It does not claim that compromise is impossible. It makes authority explicit,
bounded, independently checkable, and fail-closed.

## 1. Authority model

The v1 authority model is deliberately asymmetric:

- the compiler's static capability analysis determines what ordinary source code
  can request;
- a canonical static-capability evidence digest binds the exact narrowed scopes
  and resulting launcher capabilities;
- a trust artifact manifest binds that request to one exact `policy_hash`;
- the artifact manifest does **not** contain authoritative granted capabilities;
- the authoritative grants come from the trusted launcher's **local policy**;
- the launcher permits execution only when the statically proven requested
  capability set is a subset of the locally approved set represented by the
  bound `policy_hash`.

Changing the local policy changes its hash. An artifact bound to an older or
different policy does not silently inherit the new grants.

The source request is not a hand-written permission list. A developer or attacker
cannot turn `net.io` into `net.io + process.exec` merely by rebuilding the trust
manifest; the launch decision also requires the exact static-capability request
digest and checks the manifest capability list against it.

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

The Trust Plane validates these invariants itself. It does not assume a Python
dataclass was created by a trusted parser. A self-consistent but forged object
that changes release authority, owner approval, automatic publication, registry
write or production-integration flags is rejected.

## 3. Artifact identity

A Trust Plane artifact manifest binds:

- `artifact_sha256`
- native `build_manifest_digest`
- `release_proof_digest`
- exact `policy_hash`
- exact `capability_request_digest`
- canonical `requested_capabilities`
- its own canonical `manifest_digest`

The capability request itself binds canonical `(domain, scope, read_only)` grants
from compiler analysis. Source locations are excluded from that digest; authority
semantics, not formatting or line numbers, define the capability identity.

An artifact byte swap, build-manifest swap, release-proof swap, policy swap,
static-capability swap, or request mutation invalidates the launch decision.

## 4. Closed-world capabilities

Trust Plane v1 recognises only a reviewed launcher vocabulary:

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

Ordinary Koschei source can currently prove only:

- `disk.read`
- `disk.write`
- `net.io`
- `env.read`
- `process.exec`

`secret.use`, `signing.request`, and `deploy.execute` are reserved launcher/broker
authorities. A forged static source request containing one of them is rejected.
Future secret, signing and deploy brokers must receive those authorities through
their own explicit authorization layer rather than application source pretending
to manufacture them.

A writable disk grant requests both `disk.read` and `disk.write`; a read-only disk
grant requests only `disk.read`. Dynamic or caller-supplied capability scopes make
the static manifest non-exact and are rejected by this v1 launch kernel.

Adding a capability is a Trust Plane contract change, not a configuration typo.

## 5. Deterministic launch decision

For the same:

- artifact identity,
- build manifest,
- release proof,
- static capability request,
- local policy,

the v1 evaluator produces the same decision payload and `decision_digest`.

No clock, network call, environment lookup, secret read, subprocess execution or
remote signer is consulted by this kernel.

The kernel currently decides eligibility only. It does not launch a process.

## 6. Fail-closed rules

Launch is denied when any of the following is true:

- a manifest/proof/policy/capability digest is malformed or does not match its
  contents;
- release-proof authority invariants differ from the reproducible-candidate
  contract;
- the release proof does not bind the supplied build manifest and artifact;
- build and release proof disagree on module lock, MIR, compiler or backend
  identity;
- the trust artifact manifest references another build or release proof;
- the policy hash differs from the authoritative local policy;
- the static capability evidence is non-exact or substituted;
- trust-manifest capabilities differ from static source analysis;
- a requested capability is outside the local grant set;
- ordinary source attempts to manufacture secret/sign/deploy authority;
- a capability name is unknown;
- supplied launch artifact bytes do not match the authorized artifact digest.

A denial grants **zero effective capabilities**.

## 7. Artifact lifetime vs deployment authorization lifetime

Artifact identity and deployment authorization are different objects.

A reproducible artifact, its build manifest, its static capability evidence and
its release proof may be long-lived or non-expiring in v1. They describe **what
the artifact is and what ordinary authority it needs**.

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

1. exact artifact + exact static request + exact policy can be eligible;
2. artifact byte replacement is denied;
3. policy replacement/tampering is denied;
4. local-policy capability escalation is denied;
5. trust-manifest capabilities cannot exceed static source analysis;
6. dynamic source capability scope is denied;
7. ordinary source cannot manufacture secret/sign/deploy authority;
8. release-proof replacement is denied;
9. forged release-proof production authority is denied;
10. unknown capabilities are denied;
11. capability/grant ordering cannot change request or policy identity;
12. identical inputs produce identical decision identity;
13. a release proof never creates ambient capabilities.

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

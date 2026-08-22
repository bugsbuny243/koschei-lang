# Koschei Custody Day-One Product Report v1

Status: product contract / operational wedge

This document answers one question: what does a custody or treasury team actually install and do on Monday morning?

Koschei is not sold first as a programming language. The first product is an independent execution-authority boundary placed immediately before a privileged effect such as signing, withdrawal approval, key use, deployment, recovery or policy-changing administration.

## 1. What the customer receives

The first deployable product consists of four surfaces.

### A. Koschei Gate

A self-hostable sidecar/service or local daemon placed in the privileged request path. It receives a canonical intent request and returns one of:

- `ALLOW + proof envelope`
- `DENY + machine-readable reason`
- `HOLD + evidence requirements`

The Gate is not a signer and does not custody keys. It must remain independently deployable from the application and from the signer/HSM/MPC system.

### B. Koschei Adapter SDK

A deliberately small adapter surface for existing systems. The adapter does not translate source code into Koschei. It converts an existing privileged request into a Canonical Intent Envelope.

Initial adapter targets:

- HTTP/gRPC service call
- transaction/signing request
- HSM/MPC pre-sign hook
- Safe/multisig pre-execution hook
- CI/CD privileged deployment action

### C. Koschei Policy Bundle

A small human-reviewable policy artifact describing the authority/evidence/recovery boundary for one critical flow. Early customers should not need to write an application in native Koschei Lang.

The policy bundle is compiled into canonical Koschei obligations and a sealed policy digest.

### D. Koschei Verifier

A CLI/API/report surface that independently verifies the proof envelope produced by the Gate. Security, audit and incident-response teams must be able to verify decisions without trusting the application that requested the action.

## 2. Monday morning integration

The first integration target is one high-value action, not the customer's entire estate.

Recommended custody wedge:

`withdrawal/signing request -> Koschei Gate -> HSM/MPC/signer`

The customer changes one boundary: the signer accepts requests only when a valid Koschei proof envelope accompanies the exact payload being signed.

No application rewrite is required.

## 3. The first file the customer writes

The customer starts from a generated policy bundle similar in meaning to:

```text
flow treasury-withdrawal

ka request
  bind actor
  bind payload
  bind destination
  bind amount
  bind chain
  bind epoch

vor signing
  require treasury.withdraw
  exact payload
  exact destination
  exact amount
  one effect

shi execution
  require independent payload digest
  require signer-visible digest
  require policy digest
  require approval evidence

thal failure
  replay -> reject
  stale epoch -> reject
  payload conflict -> contain
  partial approval -> abort

nur visibility
  operator sees decision
  auditor sees proof
  requester does not receive hidden topology
```

This is the product-facing policy surface. The full Koschei Library and Universe machinery remains behind it.

## 4. Canonical Intent Envelope

The adapter sends a deterministic envelope containing only the facts required to judge the privileged effect.

Minimum withdrawal/signing envelope:

- request id
- actor identity / service identity
- exact serialized payload hash
- chain/domain
- destination
- value/amount
- requested authority
- approval set / approval references
- policy digest
- epoch
- freshness/replay material
- optional independent simulation or state digest

The Gate must never infer missing security-critical fields from display text.

## 5. What the signer must verify

Koschei does not solve a Bybit-style compromise merely by protecting Koschei-written code. A compromised third-party frontend, build pipeline or CDN can still present false information.

Therefore the core product requirement is independent signer binding:

1. The exact bytes to be signed are hashed independently of the requesting UI.
2. Koschei evaluates those exact bytes, not a human-readable approximation.
3. The proof envelope binds the exact payload digest, policy digest, epoch and evidence digest.
4. The signer/HSM/MPC integration refuses signing when the proof does not bind the exact payload presented for signature.
5. A display layer may show the decoded intent, but display text is never the security root.

This closes the design gap where the application is secure but the foreign signing path is compromised.

## 6. First-day modes

### Shadow mode

No blocking. Koschei observes copies of real requests and produces decisions/proofs. Goal: compare against current policy without production risk.

### Explain mode

Operators receive human-readable and machine-readable reasons for every would-allow/would-deny decision.

### Gate mode

Only one selected high-value flow requires a valid Koschei proof before the downstream signer accepts the request.

Customers should not be asked to move to native Koschei Lang before Gate mode has produced measurable value.

## 7. What the customer sees as output

Every evaluated request produces a Proof Envelope containing at minimum:

- intent digest
- exact payload digest
- policy digest
- authority decision
- evidence set digest
- epoch
- freshness/replay result
- runtime/library version digest
- decision timestamp/sequence
- final decision
- proof envelope digest

The verifier can answer:

- Was this exact payload evaluated?
- Under which policy?
- Under which epoch?
- Which evidence was required and present?
- Was authority narrower than or equal to the requested effect?
- Was the request replayed or stale?
- Did any required evidence conflict?

## 8. What the CISO/auditor receives

Koschei must produce externally reviewable evidence, not only internal module counts.

Required evidence package for pilots:

- deterministic proof-verification transcript
- attack/replay test corpus
- red-team report from an independent party when available
- reproducible adversarial test harness
- signed release/build provenance
- documented threat model
- integration boundary diagram
- policy and proof schemas
- explicit unsupported/unknown conditions

A pilot is successful when another team can verify the proof without trusting the Koschei application process.

## 9. Competitive answer

Koschei does not position itself as a replacement for every control already sold by custody/security vendors.

The target differentiation is:

- policy is bound to exact execution payload, not only account/role metadata;
- authority, evidence, recovery and visibility are separate semantic domains;
- execution is denied when required proof is missing or conflicting;
- epoch-bound authority expires across containment/rebirth;
- the verifier can independently check the decision envelope;
- the Gate can sit between existing infrastructure and the signer without application rewrite.

The product must be benchmarked directly against existing policy engines, transaction simulation/clear-signing products, Safe-style guards and MPC/HSM policy controls before claiming superiority.

## 10. Initial GTM wedge versus long-term ICP

Pain severity and sales accessibility are different rankings.

Recommended startup order:

1. AI-agent infrastructure with real external permissions — fastest likely pilot motion and closest fit for bounded, epoch/evidence-bound capabilities.
2. Developer/security teams operating high-value Web3 treasury flows — design-partner custody wedge, not assumed fast enterprise sale.
3. Fintech/payment infrastructure after external evidence and operational maturity improve.

Custody remains an important product proof because the threat model is unforgiving, but should not be confused with the easiest first sale.

## 11. Demo correction

The flagship security demo should match the wedge.

Primary demos:

- AI agent: email/file/deploy/payment action with explicit authority, evidence and containment.
- Treasury/multisig: exact payload -> independent proof -> signer gate -> replay/conflict/recovery.

Marketplace examples remain a language expressiveness demo, not the first commercial proof.

## 12. Pricing hypothesis

Pricing is not yet validated. The first testable packaging should be simple:

- Developer/Design Partner: free or low-cost non-production/shadow evaluation.
- Production Gate: annual platform fee plus protected-flow or protected-signer tiering.
- Enterprise: self-hosting, support, audit evidence, policy governance and custom signer/HSM integrations.

Do not price by source-code line count or number of Koschei language files. The customer buys protected privileged execution, not syntax volume.

## 13. Product existence test

Koschei is a product when a customer can:

1. install the Gate;
2. connect one adapter;
3. generate or edit one policy bundle;
4. run in shadow mode;
5. see decisions and proof envelopes;
6. independently verify those proofs;
7. place the Gate before one real privileged effect;
8. measure blocked/replayed/conflicting or policy-violating actions;
9. do all of this without rewriting the application in Koschei Lang.

Until this loop works end-to-end, Koschei has an architecture and a language direction, but not a complete deployable product.

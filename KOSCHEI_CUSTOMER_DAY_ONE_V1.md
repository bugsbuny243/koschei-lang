# Koschei Customer Day One v1

Status: product integration contract

This document answers the operational question the architecture reports did not: **what does a real customer do on Monday morning?**

The first commercial wedge is not "rewrite your application in Koschei Lang." It is "place Koschei in front of one privileged effect, observe first, then enforce when evidence is sufficient."

## Initial wedge

Primary early-adopter wedge: **AI-agent and privileged-automation infrastructure**, because integration tolerance is higher, procurement is lighter than institutional custody, and epoch-bound/evidence-bound authority is directly valuable.

Secondary design target: **treasury / custody / signing infrastructure**, but not as the first assumed buyer until external assurance, red-team evidence and integration maturity exist.

The demo must match the wedge. The first flagship demo should therefore be a privileged agent or signer flow, not a marketplace.

## What the customer receives

Day-one delivery is four concrete artifacts, not a vague "language":

1. **Koschei Gate** — a small deployable service or sidecar that receives a privileged intent before the target effect is executed.
2. **Koschei Adapter SDK** — minimal adapters for the customer's existing stack to submit canonical intent and receive `ALLOW / DENY / REVIEW` plus proof references.
3. **Koschei Policy Surface** — a small Koschei policy file describing the identity, authority, evidence, containment and visibility constraints for that one effect.
4. **Koschei Proof Envelope** — machine-verifiable output binding the input intent, policy version, evidence, decision, epoch and effect digest.

The customer does not need to migrate application source code on day one.

## Monday morning workflow

### 09:00 — pick one dangerous effect

Choose exactly one boundary whose failure can cause material damage. Examples:

- AI agent executes shell/deployment action;
- treasury requests a blockchain signature;
- privileged backend changes payout destination;
- production system rotates a secret;
- admin workflow issues a destructive cloud action.

Do not start with the whole application.

### 09:30 — connect the boundary

The existing application sends a canonical intent envelope to Koschei Gate before performing the effect.

Example conceptual envelope:

```text
subject = agent:invoice-bot
operation = payment.submit
target = account:merchant-412
amount = 1840.00
currency = TRY
payload_digest = ...
evidence_refs = [...]
request_epoch = 42
```

The adapter does not translate the customer's source language into Koschei. It only reports the requested privileged effect in a canonical form.

### 10:30 — write one small Koschei policy

The first integration should fit in one reviewable file. Conceptually:

```text
ka payment_request
vor payment_request
shi payment_request
thal payment_request
nur payment_request
```

The visible source remains compact. The Library expands this into concrete internal obligations.

### 11:00 — run in SHADOW mode

Koschei evaluates every requested effect but does not block it.

The customer receives for each request:

- decision Koschei would have made;
- exact reason codes;
- evidence used;
- missing evidence;
- authority derivation;
- epoch and stale-authority status;
- policy digest;
- proof-envelope digest.

The customer compares Koschei decisions to the production system for several days.

### Day 2-5 — disagreement review

Every disagreement is classified:

- Koschei false positive;
- Koschei caught a real policy gap;
- integration evidence missing;
- existing system has undocumented exception;
- policy is ambiguous and must be rewritten.

No enforcement until the disagreement set is understood.

### Week 2 — REVIEW mode

For selected high-risk operations, Koschei can require human review when proof is incomplete rather than immediately denying all uncertainty.

The review interface displays the canonical intent and proof state, not a vague green/red badge.

### Week 3+ — GATE mode

Only after shadow evidence is satisfactory does the customer enforce:

`NO VALID PROOF = NO EFFECT`

For a signer flow this becomes:

`NO VALID PROOF = NO SIGNATURE`

For an agent flow:

`NO VALID PROOF = NO TOOL EXECUTION`

## What the customer writes

The intended initial adoption surface is deliberately small:

- one adapter call before the dangerous effect;
- one policy file;
- evidence providers for facts Koschei cannot infer itself;
- optional CI validation of policy changes.

The customer does **not** rewrite business services, adopt a new web framework, convert databases, or retrain the whole engineering organization.

## What Koschei outputs

The primary product output is not console text. It is a **Proof Envelope** suitable for engineering review, audit and incident response.

Minimum envelope fields:

```text
intent_digest
subject_identity_digest
policy_digest
library_plan_digest
universe_plan_digest
authority_digest
evidence_digest
epoch
decision
reason_codes
effect_digest
proof_digest
```

A customer should be able to archive this envelope and later prove why an effect was allowed, denied or escalated for review.

## What the customer shows internally

### Developer / platform team

They see integration health, missing evidence and decision explanations.

### Security team

They see authority derivation, stale-token rejection, policy drift and proof integrity.

### CISO / risk owner

They see measurable outcomes:

- percentage of privileged effects covered;
- number of undocumented authority paths discovered;
- stale/replayed requests blocked in test;
- policy/evidence gaps found during shadow mode;
- independent adversarial test results;
- proof coverage for enforced effects.

### Auditor / external assessor

They receive a stable proof format, versioned policy artifacts, test vectors and reproducible verification tooling.

## External proof requirement

Internal tests are not sufficient product evidence.

Before institutional custody is treated as a primary sales target, Koschei should obtain at least three of the following:

- independent security review;
- public or private red-team report from an external party;
- reproducible adversarial test suite runnable by the customer;
- bug bounty with published scope and remediation record;
- design-partner deployment evidence;
- signed reference architecture from a credible integration partner;
- formal/verifiable proof for selected critical invariants where practical.

The product roadmap must therefore include **external evidence**, not only internal CI.

## Competitive answer the product must support

The sales question is not "why use a new language?" It is:

**Why use Koschei in addition to or instead of an existing policy engine, signer control, simulation tool or wallet-defense product?**

The target answer is:

Koschei binds **identity + authority + evidence + epoch + effect + recovery state** into one deterministic proof boundary before execution. Existing tools may own one or several of these pieces; Koschei must prove that its value comes from their composition and from preventing disagreement between them.

This claim must be demonstrated with comparative test cases, not marketing language alone.

## Bybit-class limitation acknowledged

Koschei does not solve a compromised third-party build/CDN or misleading hardware-wallet display merely because a customer writes policy in `.ks`.

To address a Bybit-class signing failure, Koschei must sit **outside the compromised presentation path** and independently reconstruct or verify the actual payload/effect that reaches the signer.

Therefore a signing integration requires:

`independent payload acquisition -> deterministic reconstruction/simulation -> policy/evidence evaluation -> proof envelope -> signer gate`

If Koschei consumes only the same compromised UI representation as the signer, it has not created an independent trust boundary.

## Pricing hypothesis

Do not price the first product like a programming language.

Initial commercial model should be infrastructure pricing tied to protected privileged effects:

- free/community local evaluator for development;
- design-partner tier for early integrations;
- team/platform tier based on protected environments or monthly verified effects;
- enterprise tier for HA deployment, private verification, support, audit exports and policy governance.

Exact prices require customer discovery. Do not invent enterprise price points before design-partner evidence.

## Stop rules

Until this day-one workflow is proven end to end:

- do not expand into six new verticals;
- do not make marketplace the flagship demo;
- do not add large new sigil families merely for breadth;
- do not lead sales with "new programming language";
- do not claim custody readiness without external assurance;
- do not claim Bybit-class protection unless the signing path is independently verified outside the compromised UI/build path.

## Product milestone that proves Koschei exists

Koschei becomes a product, not merely architecture, when a fresh customer can complete this sequence without the core team rewriting their application:

1. install Koschei Gate;
2. add one adapter call;
3. define one privileged effect policy;
4. run in shadow mode;
5. inspect proof envelopes;
6. reproduce adversarial test cases;
7. switch one effect to gate mode;
8. demonstrate that an invalid/stale/conflicting request is blocked and independently explain why.

That is the first commercial finish line.

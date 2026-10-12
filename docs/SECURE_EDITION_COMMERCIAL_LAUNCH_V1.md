# Koschei Lang Secure Edition — commercial launch gate (proposal v1)

Status: **PRE-LAUNCH / NOT FOR SALE**. This document is a proposed offer and release checklist, not evidence of production security, a completed purchase flow, or legal approval.

## Product and pricing

- Product: **Koschei Lang Secure Edition**, independently licensed from Koschei Sentinel and Koschei Web3 Hub.
- Proposed list price: **USD 1,000 per named developer per year** (annual subscription; taxes, refunds, regional availability and renewal terms must be disclosed before checkout).
- Includes, subject to verified implementation: signed release artifacts, compiler/runtime, security documentation, updates during the subscription and a defined support channel.
- No automatic entitlement to Sentinel, Web3 Hub, hosting, consulting, security certification or unlimited support.
- No payment collection, license activation, or sales claim until launch gates below are passed.

## Security positioning

Say: "Capability-oriented programming language under active development, designed to reduce ambient authority and support verifiable security boundaries."

Do **not** claim "unbreakable", "100x safer than Rust", "formally verified", "production ready", or "world's most secure" without independent reproducible evidence. Security depends on compiler, runtime, dependencies, host and deployment configuration. Publish a threat model and known limitations.

## Required release gates (all mandatory)

- [ ] Canonical native check/run/build complete for the supported feature set; no silent legacy fallback; fail-closed negative tests.
- [ ] Production broker and authenticated Object Space provider independently reviewed; no test-only cryptography in production.
- [ ] Reproducible builds, signed artifacts, provenance, SBOM, pinned dependencies, release rollback and revocation documented and tested.
- [ ] Compiler/runtime fuzzing, adversarial authority tests, isolation and resource-limit tests with published results.
- [ ] Cross-backend parity, platform support matrix, benchmarks against named baselines with methodology and raw results.
- [ ] Independent security audit and remediation tracking; documented vulnerability disclosure and patch SLA.
- [ ] Installation, quickstart, examples, language reference, compatibility and migration guide validated by external testers.
- [ ] Written commercial license/EULA, IP ownership review, third-party license notices, privacy and export review by qualified counsel.
- [ ] Checkout/payment provider, invoicing/tax handling, refunds, renewal/cancellation and region support validated end-to-end.
- [ ] Entitlement issuance, offline/online activation rules, recovery, revocation, support access and customer data minimization tested.
- [ ] Support staffing and defined response times; at least one successful external paid-pilot acceptance test.

## Sales acceptance test

A new customer must be able to read the offer and limitations, accept license terms, pay exactly the disclosed amount, receive a verifiable release and entitlement, install on a supported platform, compile/check/run a supported example, contact support, and request cancellation/refund under published terms. Test with a sandbox checkout before enabling live sales.

## Milestones

1. **Secure Alpha**: close native authority migration (#240) and publish evidence.
2. **Audited Beta**: independent review, signed candidate builds, documentation and external pilots.
3. **Commercial GA**: all release gates signed off; enable the USD 1,000/year offer only then.

Owners, deadlines and evidence links should be tracked per gate; unchecked items are not launch-ready.

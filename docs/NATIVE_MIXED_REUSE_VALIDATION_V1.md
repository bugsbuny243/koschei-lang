# Native Mixed-Domain Reuse v1 — Validation Record

This file records the execution gates for the experimental mixed-domain reusable-composition slice stacked on PR #204.

## Focused execution

Railway service: `native-mixed-reuse-redteam`

Deployment: `4975ebc3-4df9-4051-bdd0-1ea99127ed0c`

Commit: `cda5a0e8b1ea96aeb9f65a4971ba76deb226a843`

Result: **4/4 OK**.

The focused gate proves Whole, Truth, and Glyphs inputs can feed one sealed reusable reality; Glyphs can cross the reusable/root boundary; the reusable output domain is sealed; and Glyphs input byte ceilings fail closed.

## Inherited full regression

Railway deployment: `f6563637-a9b8-4917-a04f-4cfa1ff0eefb`

Commit: `cbae8576eb354c76eeec1b8e0b042cb8efeb0730`

Result: **151/151 OK**.

This run combines the four mixed-domain functional gates with the complete 147-test #204 composition/projection/cell/reusable/decision/value-domain/relationship/native-kernel regression package.

## Final adversarial gate

The final package additionally includes load-time tamper checks for:

- per-binding scalar-domain substitution;
- sealed reusable output-domain substitution;
- authority-ceiling inflation.

These checks are required to execute together with the inherited regression package before this slice is considered ready for draft review.

GitHub-hosted Actions are not represented as green while repository jobs remain blocked before runner allocation by the account billing/spending-limit condition. Railway execution is targeted evidence, not a repository-wide production-readiness claim.

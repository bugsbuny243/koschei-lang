# Koschei Founding Security Pilot

Status: **paid customer pilot — limited founding offer**

## The problem we solve

Most software dependencies run with the same ambient authority as the host process. If the process can read secrets, reach the network, inspect environment variables, or start child processes, a compromised dependency may inherit those powers too.

Koschei takes a different approach: authority is explicit. A component that was not given a disk, network, environment, or process capability cannot simply reach for one. The compiler can reject unauthorized effects before the program runs.

## Founding offer — USD 299 upfront

For the first five customers, one payment covers one focused security pilot on a single high-risk dependency, module, plugin, automation worker, signing path, or other sensitive component.

### Customer provides

- the component or a representative reduced sample;
- what that component is supposed to do;
- which resources it legitimately needs;
- the security concern or attack scenario they want tested.

### Koschei delivers

1. **Ambient-authority map** — what disk/network/environment/process access exists or would exist in the current execution model.
2. **Minimum-authority design** — the smallest capability set required for the intended behavior.
3. **Koschei proof of concept** — a representative implementation or boundary model using explicit capabilities.
4. **Negative attack case** — an intentionally unauthorized operation demonstrating compile-time rejection where the Koschei model can enforce it.
5. **Capability evidence** — `ks check --json` and `ks caps --json` evidence for the proof-of-concept program.
6. **CI policy recommendation** — concrete deny rules such as “this component must never gain network access.”
7. **Short written report** — findings, limitations, remaining runtime/host risks, and the recommended production migration path.

Target delivery: within 24 hours after receiving a usable sample and scope.

## What the customer is buying

This is not a promise that Koschei is production-ready or that any software is impossible to compromise. The paid pilot buys a **concrete least-authority security analysis and working proof**, not a marketing claim.

A successful pilot should answer measurable questions such as:

- Can this component be redesigned so it has no ambient disk access?
- Can CI prove that a dependency update did not silently add network reach?
- Can an unauthorized secret read be rejected before execution in the Koschei model?
- What exact authority is genuinely required for the intended behavior?

## Good pilot candidates

- package/plugin systems;
- CI/CD workers;
- AI/agent tool runners;
- exchange or wallet support services;
- signing and deployment helpers;
- data import/export workers;
- internal automation that handles secrets;
- third-party integrations with more host authority than they need.

## Out of scope for the USD 299 founding pilot

- full-company penetration testing;
- smart-contract audits;
- malware reverse engineering;
- production certification;
- unrestricted migration of a large application;
- guarantees against kernel, hardware, compiler, credential, social-engineering, or operational compromise.

Those require a separate scope.

## Commercial next step after a successful pilot

If the proof shows useful risk reduction, the follow-on engagement is negotiated separately and may include broader migration, CI policy integration, private compiler/runtime licensing, enterprise support, or a design-partner program.

## Payment and kickoff

The founding pilot is **USD 299 upfront**. Work starts after payment and receipt of a usable component/sample plus the intended-authority description.

This price is intentionally limited to the first five pilots so Koschei can acquire real customer evidence without pretending the pre-1.0 language is already a finished enterprise product.

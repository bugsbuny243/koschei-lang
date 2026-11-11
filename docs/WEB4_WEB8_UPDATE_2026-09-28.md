# Web4–Web8 Research Update — Koschei Lang — 2026-09-28

## Priority: Capability Language Core
draft-wei-capability-language-core-00 (2026-09-27) defines an Experimental capability language with grant entailment, grant intersection, constraints, stable reason codes and allow / deny / allow_unresolved.
This directly overlaps Koschei Lang policy/proof work and is valuable for comparative design, but it is not an accepted standard.
Source: https://datatracker.ietf.org/doc/draft-wei-capability-language-core/00/

## Agent proof/event research
Agent Action Capsules and companion disclosure/evidence bundle drafts separate canonical action records, deterministic constraints, confirmed effects, selective disclosure and citation closure.
Lang implication: keep typed policy decisions separate from execution-effect receipts and keep disclosure as a separate proof layer.
Sources:
https://datatracker.ietf.org/doc/html/draft-mih-scitt-agent-action-capsule-05
https://datatracker.ietf.org/doc/html/draft-mih-agent-disclosure-envelope-00
https://datatracker.ietf.org/doc/html/draft-mih-zhang-agent-disclosure-bundle-00

JEP adds signed Judgment / Delegation / Termination / Verification event semantics and is a candidate vocabulary for policy/proof adapters.
Source: https://datatracker.ietf.org/doc/html/draft-wang-jep-judgment-event-protocol-07

## Web5 identity/data
W3C Verifiable Credentials Data Model v2.1 Working Draft was updated 2026-09-27. Credential validity must remain separate from action authorization.
Source: https://www.w3.org/TR/2026/WD-vc-data-model-2.1-20260927/

## Web6 crypto agility
draft-ietf-hpke-hpke-05 (2026-09-26) is a Standards Track HPKE revision. Lang should represent algorithms/suites as explicit versioned capabilities; HPKE must not be equated with post-quantum security by name alone.
Source: https://datatracker.ietf.org/doc/draft-ietf-hpke-hpke/05/

## Web7 / Web8
No accepted Web7/Web8 standards identified; keep as internal future-research labels.

## Additional authorization-language watch

### AAuth Protocol v11

AAuth separates agent identity, person identity, mission/governance context, resource authorization and key-bound signed requests.

Lang implication:
- keep identity types, authorization grants, mission scope and resource capabilities as separate semantic objects;
- a valid identity proof must not erase an unresolved authorization state;
- session/resource tokens should be represented as bounded capabilities rather than ambient authority.

Source:
https://datatracker.ietf.org/doc/html/draft-hardt-oauth-aauth-protocol-11

### Agent Execution Protocol (AEP)

AEP places a governing enforcement component between the agent reasoning loop and governed resources, with authorization policy and tamper-evident transition records.

Lang implication:
- useful comparison for making policy evaluation and execution authority host-independent and explicit;
- policy proof should be able to say DENY or UNRESOLVED without falling through to execution.

Source:
https://datatracker.ietf.org/doc/draft-sato-soos-aep/

### MCP proposal watch

Track proposal-stage MCP work on signed capability declarations, tamper-evident audit records, asynchronous tool-call approval and structured authorization denials.

Lang implication:
- potential future adapter vocabulary for signed capability types, denial reason codes, approval transitions and audit receipts;
- do not import proposal semantics into the core language until compatibility and ownership boundaries are proven.

Sources:
https://github.com/modelcontextprotocol/modelcontextprotocol/pulls
https://plan.modelcontextprotocol.io/seps


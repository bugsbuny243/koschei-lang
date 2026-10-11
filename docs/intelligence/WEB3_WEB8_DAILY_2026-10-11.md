# Koschei Lang Technical Intelligence — 2026-10-11

**Status:** language/type-system research proposals, not compiler/runtime changes. Documents published 2026-10-10; exact hour uncertain relative to rolling last-24h window.

## Primary evidence
1. Agent Identity Protocol -02 (individual IETF Internet-Draft): https://datatracker.ietf.org/doc/draft-prakash-aip/ . Two encodings (JWT chain, Biscuit/Datalog), common delegation semantics, missing V7 revocation in author-reported implementations.
2. Evaluation State -01 (individual IETF Internet-Draft): https://datatracker.ietf.org/doc/draft-konda-agentproto-evaluation-state/ . Per-input states: established-positive, established-negative, not-established, stale, not-applicable.
3. Agentic AI Use Cases -03 (individual IETF Internet-Draft): https://datatracker.ietf.org/doc/html/draft-agentic-ai-usecases-requirements-03 . Separates dialog correlation/lifecycle context from private task context, and describes mediation and scoped authorization checkpoints.

## Opportunity / threat / competitor hypothesis / product
### Delegation typing
Opportunity: represent identity proof separately from delegation, scope, revocation freshness and permission to execute. Threat: implicit signature->authority coercion and stale grants. Competitor hypothesis: a type/effect system that statically rejects this conversion may differentiate Koschei Lang (not a verified competitor defect). Product: compile-time authority-check experiment.
Conceptual types: `VerifiedIdentity<Proof>`, `DelegationChain<Scope,Expiry>`, `FreshRevocationEvidence<Source,Time>`, `AuthorizedEffect<Scope>`.

### Evidence-state typing
Opportunity: preserve missing/stale/negative inputs. Threat: treating `Unknown` as `false` or `true`. Competitor hypothesis: conventional Boolean APIs obscure provenance. Product: `EvaluationInput<T> = EstablishedPositive(T) | EstablishedNegative(T) | NotEstablished(Source) | Stale(T,Timestamp) | NotApplicable` with explicit handling before authorization.

### Dialog vs task context
Opportunity: model `DialogContext<CorrelationId,Epoch>` separately from `PrivateTaskContext<Secret>`. Threat: leaking prompts across mediators or reusing approval after dialog transition. Competitor hypothesis: static privacy/effect typing for agent protocol translation remains differentiating. Product: type checker fixture rejecting task-content export and action-approval reuse.

## Standards status
The three are provisional individual Internet-Drafts, not RFCs. No universal Web4–Web8 internet-generation standard verified. No production changes in this document.

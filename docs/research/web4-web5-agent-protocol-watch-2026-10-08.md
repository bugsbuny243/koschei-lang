# Web4/Web5 Agent Protocol Watch — 2026-10-08

Status: research notes; referenced documents are drafts, not adopted IETF standards. Claims below summarize the prior monitoring report and require source verification before implementation.

## Findings

1. **Local Tool Call Proof -00 (7 October):** Per-call, short-lived, single-use proof for local MCP tool invocation, with an external authorization decision and execution gate. Candidate primitives: `LocalCallDecision`, `ActionDigest`, `OneTimeProofState`, `ToolExecutionGate`. Invariant: `LOCAL_TRANSPORT != TRUSTED_INVOCATION`.
2. **Correctover CCS -10 (7 October):** Distinguishes cryptographically verified signatures from accepted/trusted signer bindings. Candidate primitives: `ReceiptIntegrityEvidence`, `IssuerTrustBinding`. Invariant: `VALID_SIGNATURE != TRUSTED_ISSUER`.
3. **Agent Permission Receipts -00 (6–7 October):** Signed human permission, agent action receipts, delegation and revocation evidence. Integrity of a record is separate from compliance with the granted permission boundary.
4. **DAWN Discovery Framework -02 (7 October):** Federated agent discovery, signed provenance and controlled disclosure of capability descriptors. Invariant: `DISCOVERY != TRUST != AUTHORITY`.

## Koschei Lang integration rule

Treat MCP/A2A, identity carriers, registries and IETF draft formats as adapters/evidence inputs, not sources of core authority semantics. No implementation change is authorized by this research entry.

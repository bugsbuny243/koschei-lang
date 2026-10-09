# Koschei Lang — 2026-10-09 Evening Research

Window: 2026-10-08 18:00 to 2026-10-09 18:00 Europe/Istanbul. Design research only; no implementation changes.

## 1. Cross-chain vault receipt semantics
On 2026-10-08 Chainlink introduced CCIP Vault Adapters for home-chain ERC-4626 vaults. Official documentation states that bridge delivery success can coexist with an adapter processing failure, which has its own recovery lifecycle.

Sources:
- https://chain.link/blog/introducing-ccip-vault-adapters
- https://docs.chain.link/solutions/cross-chain-vault-adapter

Proposed language distinctions: DeliveredMessage, AppliedVaultEffect, MintedShares, RecoveryPending, RecoveredAsset. Do not infer application completion from transport delivery alone.

Opportunity: evidence-aware effect types. Risk: incorrect state transitions when external operations are asynchronous. Competitive differentiation hypothesis: express these distinct stages in a security-oriented language. Prototype idea: a type-checking example requiring separate delivery and application receipts.

## 2. Agent identity and transaction-policy distinction
On 2026-10-08 Riskified announced Agent Identity Risk Intelligence, with a limited beta planned for December 2026 and general availability anticipated in 2027. This is a vendor product announcement, not a new internet standard.

Source: https://ir.riskified.com/news-releases/news-release-details/riskified-launches-agent-identity-risk-intelligence-know-who

Proposed distinctions: VerifiedAgentIdentity, DelegatedAuthority, PolicyApprovedEffect, ObservedEffect, RiskAssessment. Identity proof, authorization, policy decision and external outcome are distinct. Risk estimates should retain provenance and uncertainty.

Opportunity: explicit authorization and effect semantics. Risk: a valid delegation being interpreted as blanket approval. Competitive differentiation hypothesis: stronger separation of policy and observation. Prototype idea: compile-time examples with distinct authority and observed-result types.

## Standards watch
The CFRG call for adoption of Longfellow ZK ends on 2026-10-09, but the call was opened on September 25 and does not itself establish adoption or RFC status.
Source: https://mailarchive.ietf.org/arch/msg/cfrg/WIndEoOTVff7hjH-kXoi4XRqHnU/

Web4 through Web8 are not verified as universal W3C/IETF generation standards. Distinguish Recommendations, RFCs, Internet-Drafts, vendor products and speculative labels.

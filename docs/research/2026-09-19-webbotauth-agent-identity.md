# 2026-09-19 — Web Bot Auth working-group adoption

## Status

Meaningful standards signal for Koschei Lang.

On 1 September 2026, the IETF Web Bot Auth Working Group adopted `draft-ietf-webbotauth-httpsig-protocol-00`, replacing the earlier individual `draft-meunier-webbotauth-httpsig-protocol` proposal. The document is now an active WG Internet-Draft targeting the Standards Track. It uses RFC 9421 HTTP Message Signatures, introduces the `Signature-Agent` identifier, and defines JWKS-based key discovery through a well-known directory.

Primary sources:

- https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/
- https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/history/
- https://datatracker.ietf.org/wg/webbotauth/about/

## Why this matters to Koschei Lang

The important primitive is not Web Bot Auth itself, but the increasingly standardized separation between request-level cryptographic actor attribution and authorization.

A verified HTTP message signature can establish that the holder of a key associated with a declared automated client signed the covered request components. It must not be interpreted as proof that the actor is trusted, that its advertised purpose is true, that it possesses a capability, or that the concrete action is authorized.

Canonical Lang invariants:

```text
REQUEST_SIGNATURE != AUTHORITY
ACTOR_ATTRIBUTION != AUTHORIZATION
IDENTITY_PROOF != TRUST
IDENTITY_PROOF != CAPABILITY
```

This suggests keeping a provider-independent primitive such as:

```text
RequestActorProof {
    actor_identifier
    key_identifier
    signature_evidence
    covered_components
    freshness_evidence
    key_resolution_evidence
}
```

`RequestActorProof` is evidence consumed by policy evaluation. It never produces an `ExecutionPermit` by itself.

```text
RequestActorProof
      + Capability
      + DelegationChain
      + ActionDigest
      + RuntimeState
      + LocalPolicy
          -> RuntimeDecision
```

## Signature coverage is part of the proof

The WG draft also reinforces that a signature does not automatically cover the entire semantic request. For example, body integrity requires the relevant content digest to be covered, and method/path are not authenticated merely because another request component is signed.

Koschei should therefore avoid a boolean `signed=true` abstraction. The proof must retain exactly which semantic components were cryptographically bound.

```text
SIGNED_REQUEST != FULLY_BOUND_ACTION
```

Candidate verification rule:

```text
required_action_components ⊆ cryptographically_covered_components
```

Only after this condition is satisfied should request-signature evidence be usable in an action-authorization decision.

## Key rotation and identity continuity

The draft includes key-directory and rotation semantics. Koschei should keep stable actor identity separate from current signing material:

```text
ACTOR_IDENTITY != CURRENT_SIGNING_KEY
```

Rotation of a signing key must not silently widen capability, delegation scope, audience, resource scope, validity, or runtime authorization.

## Adapter boundary

Web Bot Auth belongs at the transport/evidence adapter boundary:

```text
HTTP Message Signature
        -> WebBotAuthAdapter
        -> RequestActorProof
        -> Koschei policy / capability evaluation
```

The Lang core should not depend on `Signature-Agent`, JWKS, HTTP, Cloudflare, Google, or any particular key-directory mechanism.

## Architectural consequence

Add `RequestActorProof` as a candidate evidence primitive, while preserving the existing canonical separation:

```text
IdentityEvidence
RequestActorProof
Authority
Capability
DelegationChain
ActionDigest
RuntimeDecision
ExecutionPermit
ExecutionReceipt
OutcomeEvidence
```

The new standards signal strengthens the rule that cryptographic identification of the caller is an input to authorization, never authorization itself.

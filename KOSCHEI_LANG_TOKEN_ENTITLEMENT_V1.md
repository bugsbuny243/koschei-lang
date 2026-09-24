# Koschei Lang Token-Gated Entitlement Contract v1

Status: **product admission contract / implementation gate**.

This contract controls access to the Koschei Lang service. It is NOT part of
Koschei language semantics, compiler authority, MIR authority, Khar authority,
or capability manufacture.

## Product policy

Canonical access token mint:

`Crm17unohCsVQcXeoC4RqpYUUgFXsZVXpVjHq3a8pump`

Required balance:

`50,000,000` whole tokens.

The threshold is interpreted in whole-token units using the mint's canonical
on-chain decimals. Implementations MUST NOT hard-code or guess decimals.

Holding the threshold grants only a Lang service entitlement. It grants no
compiler capability, Khar authority, filesystem/network authority, admin role,
model custody, signing authority, or privilege inside a Koschei program.

## Admission flow

`challenge -> wallet signature -> owner proof -> exact mint -> finalized balance -> entitlement -> short-lived session`

1. Server issues a unique, unpredictable, single-use challenge containing the
   intended service/domain, wallet public key, issue time and expiry.
2. Client signs that exact challenge with the wallet key.
3. Admission verifies the signature and consumes the challenge exactly once.
4. Admission reads canonical Solana state for the exact mint above at finalized
   commitment.
5. It sums only token accounts canonically owned by the authenticated wallet and
   belonging to the exact mint. Delegated authority, unrelated token accounts,
   display metadata and ticker/name matches do not count.
6. Raw token amount is normalized using on-chain mint decimals.
7. Balance >= 50,000,000 grants a short-lived Lang entitlement session.
8. Balance < 50,000,000, unverifiable ownership, stale/ambiguous chain state,
   RPC disagreement that cannot be resolved canonically, or any proof failure
   is DENY.

## Revalidation

Entitlement is not permanent.

- Revalidate on session creation and periodically for long-lived sessions.
- Revalidate before high-value Lang service operations.
- A wallet that no longer satisfies the threshold loses entitlement on the next
  required validation.
- Cached balance may never manufacture a new entitlement after its evidence TTL
  expires.

The exact TTL is deployment policy and MUST be explicit in the deployed
admission configuration.

## Chain evidence

A successful admission receipt MUST bind at minimum:

- contract version;
- authenticated wallet public key;
- exact token mint;
- required whole-token threshold;
- mint decimals observed on-chain;
- verified raw balance;
- normalized whole-token balance;
- Solana commitment level;
- observed slot/block reference;
- challenge identifier/hash;
- admission decision;
- issued-at and expiry;
- verifier/deployment identity.

Receipts are evidence of product entitlement only. They are not language
authority or a transferable capability token.

## Security rules

- Exact mint identity wins over token name, symbol, image, URL or market label.
- Never accept a client-supplied balance as evidence.
- Never accept a client-supplied decimals value as canonical.
- Never grant access from transaction intent alone; verify resulting canonical
  chain state.
- Never accept a bare wallet address as ownership proof.
- Challenges are domain-separated, expiring and one-shot to prevent replay.
- Session credentials are bound to the admitted wallet and deployment.
- Entitlement checks run outside compiler/runtime semantic authority.
- Failure or unavailability is fail-closed for new admission.

## Architecture boundary

Recommended boundary:

`Wallet -> Entitlement Admission -> Lang Service Gateway -> Koschei Lang`

The gateway may answer only: `ALLOW` or `DENY` plus evidence. It cannot
create Koschei capabilities. Koschei's constitutional execution checks remain
independent and mandatory after admission.

## Implementation gate

Before production enablement, evidence must demonstrate:

1. valid wallet signature + >= threshold -> ALLOW;
2. valid signature + below threshold -> DENY;
3. wrong mint with same/similar metadata -> DENY;
4. forged/client-reported balance -> DENY;
5. expired/replayed challenge -> DENY;
6. token balance removed after admission -> DENY at required revalidation;
7. decimal normalization uses canonical mint state;
8. RPC/chain evidence is bound into the admission receipt;
9. no path from entitlement receipt to Khar/compiler capability manufacture.

No token purchase, sale, pricing, market-value, or trading behavior is part of
this contract.

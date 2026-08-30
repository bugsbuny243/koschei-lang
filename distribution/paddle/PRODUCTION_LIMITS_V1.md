# Koschei Lang — Paddle Production Limits v1

Koschei Lang is pre-1.0 proprietary developer software. The initial Paddle channel is an **early commercial developer release**, not a claim of general-purpose language completeness.

## Known limits that must be disclosed

- Native `ks build` currently requires a compatible Go toolchain for strict MIR-Go builds.
- Not every Koschei language construct is currently representable by the strict native MIR-Go backend.
- Production behavior must fail closed rather than fall back to the legacy ambient-authority AST-Go backend.
- `ks run` still has same-process interpreter/runtime custody debt; it is not presented as physical host isolation.
- Stdlib coverage is incomplete relative to the planned operation catalog.
- Lambda/trait/concurrency/region-memory work is not implied as implemented.
- Platform support is per released artifact. A Linux x86_64 artifact does not imply macOS, Windows, ARM64, musl, or Alpine support.
- Exact libc/dynamic dependency requirements are carried by `RUNTIME-REQUIREMENTS.json` for each package.

## Support and updates

Price, update entitlement, support period, refund terms, seat/entity scope, and whether future major releases are included are commercial configuration presented at Paddle checkout. The compiler does not invent or hard-code these terms.

## Security claims

Use `CUSTOMER_SECURITY_DISCLOSURE_V1.md`. Marketing must not say “unhackable,” “code can never be seen,” or imply that compile-time capability checks equal a completed runtime sandbox.

## PROTECTS AGAINST

This disclosure protects the product boundary against accidental overclaiming and makes unsupported runtime/platform assumptions visible before purchase.

## DOES NOT PROTECT

It does not itself fix incomplete stdlib coverage, platform coverage, Go-toolchain dependency, or runtime custody.

## ASSUMPTIONS

The offer page and customer download page expose the current version of this limitation set rather than stale copy.

## FAILURE MODE

If the shipped artifact or sales copy contradicts these limits, the Paddle production release is not considered qualified for sale.

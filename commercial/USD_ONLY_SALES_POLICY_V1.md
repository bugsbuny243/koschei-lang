# Koschei Lang — USD-only sales policy v1

Status: **ACTIVE COMMERCIAL DECISION** (2026-10-12)

## Currency and channels

All new Koschei Lang offers, quotes, invoices, checkouts and customer-facing prices must be denominated in **USD**. Cryptocurrency payments are not accepted, and no cryptocurrency-to-USD conversion is implied or authorized.

The existing **USD 299 founding security pilot** is a distinct scoped service, not a compiler license. The Koschei Lang license is sold as one product: **USD 49 per developer**, one-time and perpetual, with 12 months of updates, through Polar (owner decision, 2026-11-11; see `LICENSING.md`). Do not silently convert it to a subscription.

## Engineering separation

Commercial payment/entitlement issuance remains external to compiler authority. Reuse the existing commercial entitlement and activation primitives; do not add a payment provider, signing private key or USD price to compiler/runtime code.

## Sales readiness

A live USD checkout must be backed by published terms, verified fulfillment, signed customer artifacts, independently trusted release keys, customer support and end-to-end sandbox tests. The 49 USD checkout is live on Polar; signed release artifacts and independently trusted release keys are still open (`KOSCHEI_SAHIP_EYLEM_LISTESI_V1.md`, S3).

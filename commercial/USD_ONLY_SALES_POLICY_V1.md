# Koschei Lang — USD-only sales policy v1

Status: **ACTIVE COMMERCIAL DECISION** (2026-10-12)

## Currency and channels

All new Koschei Lang offers, quotes, invoices, checkouts and customer-facing prices must be denominated in **USD**. Cryptocurrency payments are not accepted, and no cryptocurrency-to-USD conversion is implied or authorized.

The existing **USD 299 founding security pilot** is a distinct scoped service, not a compiler license. The owner's requested **USD 1,000 Koschei Lang license** is the target product list price; the exact license duration, seats, upgrades, refunds, tax handling and checkout provider remain to be explicitly approved before taking payment. Do not silently convert it to a subscription.

## Engineering separation

Commercial payment/entitlement issuance remains external to compiler authority. Reuse the existing commercial entitlement and activation primitives; do not add a payment provider, signing private key or USD price to compiler/runtime code.

## Sales readiness

A live USD checkout must be backed by published terms, verified fulfillment, signed customer artifacts, independently trusted release keys, customer support and end-to-end sandbox tests. Until then, USD 1,000 is a **proposed license price**, not an enabled checkout or representation of general availability.

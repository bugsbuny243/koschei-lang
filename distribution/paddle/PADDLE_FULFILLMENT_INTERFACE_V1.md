# Paddle Fulfillment Interface v1

This document defines the interface between Paddle commerce and Koschei Lang artifact delivery. It does **not** move billing into the compiler.

## Production flow

1. Marketing site opens Paddle Checkout with the configured live `price_id`.
2. Checkout may attach non-secret `customData`, e.g. `product=koschei-lang` and `release_channel=paddle-production`.
3. External webhook endpoint receives `transaction.completed`.
4. Endpoint verifies the raw request body using the `Paddle-Signature` header and the secret for that notification destination **before acting on the payload**.
5. Endpoint deduplicates by Paddle event ID.
6. Endpoint confirms transaction status is `completed`, expected product/price is present, and custom data is consistent.
7. Endpoint creates or retrieves a durable entitlement record outside this repository.
8. Entitlement grants access to the already-built, signed production artifact.
9. Customer receives the independently published Koschei release key/fingerprint location and verification command.

Do not provision solely from client-side `checkout.completed`; the browser callback is not the server-side fulfillment authority.

## Secrets

Never place these in the compiler, repository, source package, or customer ZIP:

- Paddle API key
- Paddle webhook destination secret
- download-service signing secret
- Koschei release signing private key

A Paddle client-side token is intended for browser use, but it still does not belong in the Koschei compiler artifact.

## Entitlement boundary

A durable external entitlement should bind at least:

- Paddle transaction ID
- Paddle customer ID when present
- purchased offer/price identity
- `koschei-lang` product identity
- allowed artifact release family/platform
- issued/revoked state
- issue timestamp and audit record

The only conceptual result crossing from commerce to distribution is:

```json
{
  "product": "koschei-lang",
  "channel": "paddle-production",
  "entitled": true,
  "offer_id": "<external-configured-offer>",
  "transaction_id": "<Paddle transaction id>"
}
```

This result never changes Koschei semantics and is not a capability inside a user program.

## PROTECTS AGAINST

- Treating an unverified browser callback as proof of payment.
- Accidental leakage of Paddle secrets into a customer binary.
- Coupling payment-provider identity to Koschei semantic identity.
- Duplicate webhook delivery causing duplicate provisioning when the external service is idempotent.

## DOES NOT PROTECT

- A compromised Paddle account.
- A compromised fulfillment/download service.
- Chargeback/refund lifecycle mistakes unless the entitlement service consumes the required lifecycle events.
- Theft of the Koschei release signing private key.

## ASSUMPTIONS

- The external service verifies Paddle signatures against the correct notification-destination secret.
- Product/price identifiers come from the approved Paddle account.
- Entitlements are stored durably and processed idempotently.
- Release artifacts pass the independent Koschei production release gate.

## FAILURE MODE

If signature verification, transaction/product matching, or entitlement storage fails, fulfillment fails closed: **no customer download entitlement is issued**.

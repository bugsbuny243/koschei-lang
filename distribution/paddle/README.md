# Koschei Lang — Paddle Production Distribution

Status: **production sales boundary under release qualification**

This directory is the customer-distribution contract for Koschei Lang purchases fulfilled after a Paddle payment. It is deliberately separate from Pi/Testnet distribution. **Nothing under `distribution/solohost/` is part of this channel.**

## Boundary

```text
Koschei Lang private source
        |
        v
owner-controlled release build
        |
        +--> functional/security smoke receipt
        +--> runtime requirements receipt
        +--> source-free customer artifact
        +--> immutable manifest + SHA-256
        +--> owner-held Ed25519 signing key
        |
        v
independently published release public key/fingerprint
        |
        v
Paddle transaction.completed (verified outside compiler)
        |
        v
external entitlement/download service
        |
        v
customer downloads + verifies exact signed artifact
```

Paddle is the commerce/Merchant-of-Record boundary. Payment state, customer identity, webhook secrets, API keys, and download entitlements are **not language semantics** and must never be embedded into `ks` or the customer release.

## Production gate

A Paddle artifact is publishable only when all of these are true:

1. `tools/smoke_paddle_binary_v1.py` produced a receipt for the exact binary.
2. The receipt records `ks2401_supply_chain_denial: true`.
3. Runtime requirements for the exact platform are measured and packaged.
4. `tools/paddle_release_v1.py assemble ...` creates source-free staging.
5. The staging manifest is signed with an owner-held Ed25519 private key.
6. The private key never enters the artifact.
7. The release public key or fingerprint is published independently of the download.
8. `tools/paddle_release_v1.py verify ... --trusted-public-key <out-of-band-key>` passes.
9. The package contains no Testnet notice, Pi/SoloHost metadata, compiler source, build secrets, or Paddle secrets.
10. Customer-facing security and limitation documents match the actual implementation.

## Release commands

```bash
python tools/smoke_paddle_binary_v1.py ./ks \
  --receipt /secure-evidence/paddle-smoke.json

python tools/inspect_paddle_runtime_v1.py ./ks \
  --platform linux-x86_64 \
  --output /secure-evidence/runtime-linux-x86_64.json

python tools/paddle_release_v1.py assemble \
  --binary ./ks \
  --output ./paddle-release \
  --version 0.10.0 \
  --platform linux-x86_64 \
  --source-commit <FULL_COMMIT_SHA> \
  --smoke-receipt /secure-evidence/paddle-smoke.json \
  --runtime-requirements /secure-evidence/runtime-linux-x86_64.json \
  --customer-readme distribution/paddle/customer/README.txt \
  --license-notice distribution/paddle/customer/LICENSE.txt

python tools/paddle_release_v1.py sign ./paddle-release \
  --private-key /owner-custody/koschei-release-ed25519.pem

python tools/paddle_release_v1.py verify ./paddle-release \
  --trusted-public-key /independent-anchor/koschei-release-public.pem
```

The exact Paddle `price_id`, client-side token, webhook destination, webhook secret, live domain, tax display, and refund policy are deployment/account configuration. They are not hard-coded into the compiler or artifact.

## What “sale ready” means here

This repository can produce and verify the **software payload** and defines the exact fulfillment boundary. Real-money checkout is not considered live until Paddle account approval, a live product/price, a default payment link/domain, a verified `transaction.completed` webhook destination, and the independent download entitlement service are configured externally.

## PROTECTS AGAINST

- Accidental mixing of Paddle production artifacts with Pi/Testnet packaging.
- Publishing source/build-secret material through the defined Paddle release gate.
- Treating an artifact-bundled key as the sole trust anchor.
- Silent binary replacement when the independent release key/fingerprint is used.

## DOES NOT PROTECT

- A compromised Paddle account, fulfillment service, build machine, host kernel, or release-signing private key.
- Runtime custody gaps that remain inside a correctly signed Koschei binary.
- Unsupported platforms or language features.

## ASSUMPTIONS

- The production binary passes the exact smoke/runtime gates before signing.
- The authoritative release key/fingerprint is published through an independently authenticated official channel.
- Paddle live account configuration and webhook verification are implemented outside compiler semantics.

## FAILURE MODE

If production/Testnet identity is mixed, required evidence is absent, independent signer trust fails, exact binary/runtime metadata differs, or forbidden source/secret material is present, publication fails closed and no Paddle production artifact is qualified for sale.

See `PADDLE_FULFILLMENT_INTERFACE_V1.md`, `RELEASE_TRUST_MODEL_V1.md`, `CUSTOMER_SECURITY_DISCLOSURE_V1.md`, and `PRODUCTION_LIMITS_V1.md`.

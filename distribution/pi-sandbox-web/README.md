# Koschei Lang Pi Sandbox Bridge V1

This directory exists only to complete and verify the Pi Developer Portal sandbox flow before production deployment.

It is **not** the Koschei compiler, a production entitlement service, or a payment backend.

## Developer Portal configuration

Koschei Lang Testnet configuration currently expects:

- App Hosting: `Self Hosted`
- Production URL: `https://lang.tradepigloball.co`
- Development URL: `http://localhost:3000`
- Testnet visibility: private during owner testing

## Run locally

From the repository root:

```bash
python tools/serve_pi_sandbox_v1.py
```

This binds only to `127.0.0.1:3000` by default.

Then use the Pi Developer Portal checklist step **Run Development App in the Sandbox**. Pi's sandbox flow should route the browser to the configured development URL.

The page must show:

- SDK: `ready`
- Mode: `sandbox`
- Network: `Pi Testnet`

Press **Continue with Pi** to exercise the frontend SDK authentication handshake.

## Security boundary

V1 intentionally requests only the `username` authentication scope.

The frontend result is display/test evidence only. It MUST NOT grant a Koschei license or durable entitlement. Before production authorization, the access token returned by Pi SDK must be verified by a server-side call to Pi Platform API `/v2/me`.

The browser bundle MUST NOT contain:

- Pi API keys;
- app-wallet secret seed/private keys;
- Koschei release signing private keys;
- payment approval/completion credentials;
- compiler source.

## Payments

No payment code is implemented in this sandbox slice. User-to-app payment requires server-side approval and completion. That flow will be added only behind the external Pi adapter/entitlement service, not inside Koschei language semantics.

## Production

Do not change `sandbox: true` in this development bridge and deploy it as production. Production gets a separate build/configuration with server-side identity verification, durable one-time purchase entitlements, HTTPS, and domain validation.

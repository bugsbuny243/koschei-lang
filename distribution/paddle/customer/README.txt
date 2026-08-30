KOSCHEI LANG — PADDLE PRODUCTION CUSTOMER PACKAGE

FILES
  ks / ks.exe
      Koschei Lang command-line executable.

  koschei-paddle-release-manifest.json
      Product/version/platform metadata and SHA-256 for the exact executable.

  koschei-paddle-release-manifest.sig
      Detached Ed25519 signature over the exact manifest bytes.

  RUNTIME-REQUIREMENTS.json
      Platform, architecture, libc and dynamic dependency requirements.

  LICENSE.txt
      Commercial binary license notice.

VERIFY BEFORE USE
  Obtain the official Koschei release public key or fingerprint from the
  independently published official channel identified on the purchase/download
  page. Do not trust a public key learned only from the same download.

QUICK START
  ks version
  ks new demo
  ks check demo
  ks run demo
  ks caps demo

SECURITY BOUNDARY
  Koschei rejects covered disk/network/environment/process effects when the
  required capability is unavailable to the checked code path. Current pre-1.0
  releases do not claim complete physical runtime isolation from the host.

NATIVE BUILDS
  `ks build` may require a compatible Go toolchain. Unsupported strict-native
  programs must fail closed rather than silently use an ambient-authority
  compatibility backend.

Keep purchase/entitlement information separately from this package. Paddle
payment/customer secrets are never required by the Koschei executable.

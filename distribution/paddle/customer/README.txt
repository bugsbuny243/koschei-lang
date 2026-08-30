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

PROTECTS AGAINST
  Covered unauthorized effects that are absent from the checked capability
  scope, and undetected production-binary replacement when the package is
  verified with the independently published release key/fingerprint.

DOES NOT PROTECT
  Host/kernel compromise, malicious build/signing infrastructure, arbitrary
  native/foreign escape paths, every software vulnerability, or complete host
  isolation. Full physical runtime custody is not claimed complete.

ASSUMPTIONS
  You verify the artifact before use, satisfy RUNTIME-REQUIREMENTS.json, and do
  not treat unverified native/foreign code as capability-safe Koschei code.

FAILURE MODE
  Unsupported strict-native execution must fail closed rather than silently use
  the legacy ambient-authority compatibility backend. Signature/hash/runtime
  verification failure means the package must not be trusted or executed.

NATIVE BUILDS
  `ks build` may require a compatible Go toolchain. Unsupported strict-native
  programs must fail closed rather than silently use an ambient-authority
  compatibility backend.

Keep purchase/entitlement information separately from this package. Paddle
payment/customer secrets are never required by the Koschei executable.

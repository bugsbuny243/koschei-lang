# Koschei Deployment Authorization v1

**Status:** active Trust Plane sub-contract.

Deployment Authorization answers a different question from artifact identity:

- build/release/static-capability evidence answers **what is this artifact?**
- local policy answers **what authority could this environment grant?**
- deployment authorization answers **may this exact artifact perform this exact
  launch/deploy operation in this exact environment during this authorization
  window?**

These lifetimes and authorities must not be collapsed into one object.

## 1. External signing boundary

Koschei Lang does not store or derive the production deployment signing key in
this module.

A deployment authority signs the exact canonical payload externally. The trusted
launcher receives only:

- the authorization object;
- signature bytes;
- a verifier callback backed by the configured trust root.

The module intentionally follows the existing private-distribution pattern of
canonical payload + external verifier rather than embedding an application HMAC
secret as deployment authority.

The cryptographic algorithm and key custody mechanism therefore remain a
launcher/deployment-infrastructure decision. Switching trust roots must not
change the canonical authorization semantics.

## 2. Signed fields

`koschei.deployment-authorization.v1` signs:

- `authorization_id`
- `operation` — exactly `launch` or `deploy`
- `environment`
- `artifact_sha256`
- `trust_manifest_digest`
- `policy_hash`
- `capability_request_digest`
- `not_before_epoch`
- `expires_after_epoch`
- `nonce`

No unsigned extension field may grant additional authority.

## 3. Time boundary

`not_before_epoch` and `expires_after_epoch` belong only to the deployment
authorization.

Expiration does **not** invalidate:

- source identity;
- native build manifest;
- artifact bytes;
- static capability evidence;
- release proof;
- Trust Plane artifact manifest.

It only invalidates this authorization to launch/deploy them.

Because authorization uses wall-clock epoch bounds, correct trusted time is an
explicit operational dependency and threat-model assumption for this layer.
Future launcher deployments must document their trusted-clock source and rollback
behavior.

## 4. Replay resistance

Signature verification alone is insufficient. A valid signed authorization that
can be replayed forever is still dangerous.

The v1 redemption API therefore requires an `atomic_redeemer` callback. It must
atomically claim the pair:

`authorization_id + authorization_payload_digest`

and return true only for the first successful claim.

A read-then-write sequence is not compliant because two concurrent launchers can
both observe "unused" before either writes.

If trusted replay storage is missing or unavailable, authorization fails closed.
A failed signature or failed binding check is never redeemed.

The authorization is consumed before the later process-execution layer receives
a launch permit. If process creation subsequently fails, the authorization stays
consumed. Availability loses to authority safety.

## 5. Exact binding

Redemption requires all of these to match simultaneously:

- expected operation;
- expected environment;
- local-policy environment;
- local `policy_hash`;
- artifact SHA;
- Trust Plane artifact-manifest digest;
- static-capability request digest;
- authorization time window;
- external signature;
- successful atomic first-use claim.

A staging authorization cannot silently authorize production. A launch grant
cannot silently become a deploy grant. A valid authorization for artifact A
cannot authorize artifact B, even when both artifacts request the same
capabilities.

## 6. No ambient signer authority

Ordinary Koschei application source cannot request `deploy.execute` or
`signing.request` through its static capability manifest.

Those are reserved trusted-launcher/broker authorities. Deployment Authorization
is one input into those future brokers; it does not hand a signing key or deploy
credential to application code.

## 7. Failure behavior

Any malformed payload, invalid signature, time-window failure, operation mismatch,
environment mismatch, policy mismatch, artifact substitution, trust-manifest
substitution, static-capability substitution, or failed atomic redemption returns
false.

No partial authority is granted.

## 8. Required adversarial tests

The v1 test matrix covers:

1. exact signed authorization succeeds once;
2. the same authorization cannot redeem twice;
3. an invalid signature does not consume the grant;
4. not-yet-valid authorization is denied;
5. expired authorization is denied without expiring artifact identity;
6. operation substitution is denied;
7. environment substitution is denied;
8. policy substitution is denied;
9. artifact substitution is denied;
10. Trust Plane manifest substitution is denied;
11. static capability evidence substitution is denied;
12. mutation after signing is denied;
13. missing atomic redemption authority is denied.

## 9. Next launcher contract

A future Trusted Launcher v1 must require **both**:

1. a successful deterministic Trust Plane launch decision for the exact artifact,
   build/release provenance, static capability request and local policy; and
2. successful single-use Deployment Authorization redemption.

Only then may it create a launch permit. OS/process sandbox enforcement remains a
separate boundary and must not be claimed by this authorization module.

# Koschei Deployment Authorization v1

**Status:** active Trust Plane sub-contract.

Deployment Authorization answers a different question from artifact identity:

- build/release/static-capability evidence answers **what is this artifact?**
- local policy answers **what authority could this environment grant?**
- deployment authorization answers **may this exact artifact perform this exact launch/deploy operation in this exact environment during this authorization window?**

These lifetimes and authorities must not be collapsed into one object.

## 1. External signing boundary

Koschei Lang does not store or derive the production deployment signing key in this module. A deployment authority signs the exact canonical payload externally. The launcher receives the authorization object, signature bytes, and a verifier callback backed by the configured trust root.

The cryptographic algorithm and key custody mechanism remain deployment-infrastructure decisions. Switching trust roots must not change canonical authorization semantics.

## 2. Signed fields

`koschei.deployment-authorization.v1` signs exactly:

- `authorization_id`
- `operation` — `launch` or `deploy`
- `environment`
- `artifact_sha256`
- `trust_manifest_digest`
- `policy_hash`
- `capability_request_digest`
- `not_before_epoch`
- `expires_after_epoch`
- `nonce`

No unsigned extension field may grant authority.

## 3. Time boundary

`not_before_epoch` and `expires_after_epoch` belong only to deployment authorization. Expiration does not invalidate source identity, build evidence, artifact bytes, static capability evidence, release proof, or Trust Plane artifact identity.

Because authorization uses wall-clock epoch bounds, correct trusted time is an explicit operational dependency and threat-model assumption.

## 4. Replay resistance and redemption evidence

Signature verification alone is insufficient. V1 therefore requires an `atomic_redeemer` that atomically claims:

`authorization_id + authorization_payload_digest`

and succeeds only on the first claim. Read-then-write replay checks are not compliant.

A successful claim returns a `RedeemedAuthorization` evidence object. It contains the exact authorization digest, artifact/policy/capability bindings, redemption epoch, and a canonical `redemption_digest` over those fields.

`RedeemedAuthorization` is deliberately **not executable authority**. It has no spawn/deploy primitive. The Trusted Launcher must combine it with a valid deterministic Trust Plane launch decision before any launch permit exists.

If replay storage is missing or unavailable, redemption fails closed. Failed signatures and failed bindings never consume the authorization. If a later process-creation layer fails after redemption, the grant stays consumed; authority safety wins over availability.

## 5. Evidence revalidation

Deployment redemption does not trust dataclass construction. Before a signed authorization can be redeemed it independently revalidates:

- the canonical local-policy hash;
- the canonical static-capability request digest;
- the canonical Trust Artifact Manifest digest;
- manifest requested capabilities against static source capabilities;
- requested capabilities against local policy grants.

A forged policy/request/manifest object therefore cannot manufacture redemption evidence merely by supplying plausible-looking SHA-256 strings.

## 6. Exact binding

Redemption requires simultaneous agreement on operation, environment, local policy, artifact SHA, Trust Artifact Manifest digest, static capability request digest, requested capability set, authorization time window, external signature, and atomic first-use claim.

A staging authorization cannot become production authority. A launch grant cannot become a deploy grant. An authorization for artifact A cannot authorize artifact B.

## 7. No ambient signer authority

Ordinary Koschei source cannot request `deploy.execute` or `signing.request` through the language-level static capability manifest. Those remain trusted broker/launcher authorities. Deployment Authorization never hands a signing key or deployment credential to application code.

## 8. Failure behavior

Malformed evidence, invalid signatures, forged canonical identities, time-window failures, operation/environment/policy mismatches, artifact substitution, trust-manifest substitution, static-capability substitution, capability escalation, or failed atomic redemption return no redemption evidence.

No partial authority is granted.

## 9. Required adversarial coverage

The v1 matrix covers single successful redemption, replay denial, bad-signature non-consumption, time bounds, operation/environment/policy substitution, artifact and manifest substitution, static capability substitution/escalation, post-signature mutation, forged canonical evidence, and missing atomic redemption storage.

## 10. Trusted Launcher relationship

Trusted Launcher v1 requires both:

1. successful deterministic Trust Plane evaluation for the exact artifact, provenance, static capability request, and local policy; and
2. a valid atomically single-use `RedeemedAuthorization`.

The resulting `TrustedLaunchPermit` binds the authorization payload digest **and** the atomic `redemption_digest`. OS/process enforcement remains a separate boundary and must prove its own controls before process authority exists.

# Koschei SoloHost Release Trust Model V1

Status: **release-security contract; production key not yet provisioned**

This contract covers authenticity and byte integrity of a Koschei Lang customer
artifact. It does not claim that signing proves compiler correctness, runtime
isolation, or the absence of malicious source-level behavior.

## Trust chain

```text
independent official trust channel
        |
        +--> pinned Ed25519 owner public key / key id
                    |
                    v
signed release manifest
        |
        +--> immutable product / version / platform identity
        +--> executable path
        +--> executable SHA-256 + byte size
                    |
                    v
exact customer executable bytes
```

The public key may also be included in a ZIP for convenience, but that copy is
never authoritative. Verification must begin with a key obtained independently
of the artifact being checked.

## PROTECTS AGAINST

- replacement of the executable while retaining the original signed manifest;
- replacement of the manifest without possession of the trusted signing private key;
- attacker-generated key/signature substitution when the verifier is given the
  independently pinned owner public key;
- accidental executable truncation or byte corruption detected by SHA-256/size;
- publishing an unsigned staging manifest through the production publication gate;
- path substitution intended to make the verifier hash a different executable.

## DOES NOT PROTECT AGAINST

- compromise or misuse of the owner signing private key;
- compromise of the independent channel from which the trusted public key is learned;
- a malicious or compromised compiler/build machine producing intentionally bad
  bytes that the legitimate owner process then signs;
- post-verification runtime compromise by the OS, kernel, administrator/root,
  debugger, injected library, hardware, or equivalent host authority;
- semantic/compiler bugs that produce unsafe behavior while preserving a valid
  signed artifact chain;
- rollback to an older legitimately signed release unless a separate minimum-version
  or revocation policy is enforced.

## ASSUMPTIONS

- Ed25519 and SHA-256 remain suitable for this release-authentication purpose;
- the production private key is generated/stored outside the repository and is not
  shipped to customers;
- the verifier receives the trusted public key through a channel independent from
  the release artifact bytes;
- OpenSSL used by the publication verifier is itself trustworthy enough for the
  publication environment;
- the owner-controlled release process signs only manifests whose evidence and
  release policy have already passed.

## FAILURE MODE

The publication gate fails closed when the external trust anchor is absent, when
its derived key id differs from the manifest signer, when the detached Ed25519
signature does not verify, when executable SHA-256/size differ, or when required
release metadata is malformed.

If the production private key is suspected compromised, existing verification of
new releases must stop. Key rotation requires publishing a new public trust anchor
through the independent official channel and an explicit rotation/revocation
record. A new key silently bundled only inside a new ZIP is not an acceptable
rotation mechanism.

## Remaining production work

1. Generate the production Ed25519 signing key outside Git/release artifacts.
2. Publish and pin the public key or `ed25519-sha256:` identity on an independent
   official Koschei-controlled trust page/channel.
3. Define key rotation/revocation and minimum-version policy.
4. Make the owner release job call the fail-closed verifier with that external key
   before any SoloHost publication step.

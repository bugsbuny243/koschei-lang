# Paddle Production Release Trust Model v1

The customer must not learn the authoritative Koschei release key only from the same package whose authenticity is being checked.

## Trust chain

```text
independent official channel
        |
        v
trusted Ed25519 public key / fingerprint
        |
        v
signed production manifest
        |
        +--> exact ks SHA-256
        +--> exact ks size
        +--> platform/version/source commit
        +--> runtime-requirements digest
        +--> KS2401 smoke evidence assertion
```

The signing private key is supplied to the signing command by an owner-controlled path and is never copied into the artifact. The verifier requires the trusted public key as a separate input.

## PROTECTS AGAINST

- Replacement of `ks` without changing the manifest.
- Manifest changes without possession of the trusted release signing private key.
- Attacker package + attacker keypair substitution when the buyer obtains the trusted public key/fingerprint independently.
- Publishing unsigned staging as a production Paddle artifact.
- Shipping Testnet markers or obvious source/build-secret material through the Paddle production gate.

## DOES NOT PROTECT

- A compromised owner release-signing private key.
- A malicious or compromised compiler/build machine that signs malicious bytes.
- A compromised independent channel that publishes an attacker key/fingerprint.
- Runtime custody failures inside a correctly signed binary.
- Vulnerabilities in Paddle or the external entitlement/download service.

## ASSUMPTIONS

- Ed25519/OpenSSL behaves correctly.
- The buyer obtains the trusted release public key/fingerprint from an independently authenticated official channel.
- Owner signing-key custody is separated from the customer artifact and normal source checkout.
- The exact binary passed the referenced smoke gate before assembly.

## FAILURE MODE

If the independent key is unavailable, signer identity differs, signature fails, binary digest/size differs, runtime requirements do not match, the manifest is not `paddle-production/PRODUCTION`, or forbidden Testnet/source/secret material is present, verification returns **REJECTED** and the artifact is not publishable.

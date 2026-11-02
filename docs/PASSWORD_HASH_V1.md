# Message authentication and password hashing v1

`password_hash_v1` adds three pure builtins. Koschei implements no
cryptographic primitive: under `ks run` they are Python's `hmac` and
`hashlib`, in native binaries Go's `crypto/hmac`, `crypto/sha256`,
`crypto/pbkdf2` and `crypto/subtle` (Go 1.24 or newer).

| Call | Type | Result |
|---|---|---|
| `hmac_sha256(key: Bytes, message: Bytes)` | `String` | lowercase hex HMAC-SHA256 (RFC 2104 / RFC 4231) |
| `pbkdf2_sha256(password: Bytes, salt: Bytes, iterations: Int, length: Int)` | `String or Error` | lowercase hex PBKDF2-HMAC-SHA256 key of `length` bytes (RFC 8018) |
| `secure_equal(a: String, b: String)` | `Bool` | equality of the UTF-8 bytes in time that does not depend on where they differ |

## PBKDF2 bounds

A stored password hash must not be weak by accident, so `pbkdf2_sha256`
checks its parameters in this order and returns the first failure as a
`KS3490` Error value:

1. salt: 16 to 1024 bytes — take it from `RandomCaps.bytes(16)` and store it
   next to the hash;
2. iterations: 100,000 to 10,000,000 — 600,000 is OWASP's 2023 recommendation
   for PBKDF2-HMAC-SHA256;
3. key length: 16 to 64 bytes;
4. password: at most 4,096 bytes.

The empty password is accepted: whether it is allowed is the application's
rule, not the hash's.

## Use

Compare a received tag or a recomputed hash with `secure_equal`, never with
`==`, which may stop at the first differing byte:

```ks
fn verify(password: String, salt: Bytes, stored: String) -> Bool {
    let hash = pbkdf2_sha256(password.to_bytes(), salt, 600000, 32) or {
        return false
    }
    return secure_equal(hash, stored)
}
```

A webhook signature is `hmac_sha256(secret, body.to_bytes())` compared with
`secure_equal` to the header the sender set. Keep the secret out of the
source: read it through `EnvCaps` or a file the program is allowed to read.

## What this does not claim

- PBKDF2 is the standard, widely available choice; memory-hard functions such
  as Argon2id or scrypt are not in v1 because neither Python's standard
  library nor Go's ships them.
- These builtins have not been through an independent audit of their own;
  they delegate to the platform providers, which have.

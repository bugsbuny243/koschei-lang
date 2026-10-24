// Koschei Core Library: secure
//
// Written in Koschei over the kernel `sha3_256` digest, which delegates to an
// audited host implementation: Koschei implements no cryptographic primitive.
// Digests are self-describing ("sha3-256:" + 64 lowercase hex characters), so
// a later algorithm can live beside this one without ambiguity.

fn hash(value: String) -> Result<String, Error> {
    let digest = sha3_256(value) or return Err(Error("secure.hash: input exceeds the digest budget"))
    return Ok("sha3-256:" + digest)
}

// Domain-separated digest of a context label and an ordered list of parts.
// Every field is written as "<length>:<text>", with lengths in characters, so
// two different (context, parts) inputs can never encode to the same bytes.
// The context names the purpose (for example "koschei.marvel.hela.tombstone/v1")
// and may not be empty: an unlabelled digest could be replayed in another
// purpose.
fn digest(context: String, parts: List<String>) -> Result<String, Error> {
    if context.length() == 0 {
        return Err(Error("secure.digest: context must not be empty"))
    }
    let mut encoded = "koschei.secure.digest/v1\n{context.length()}:{context}"
    for part in parts {
        encoded = encoded + "\n{part.length()}:{part}"
    }
    let value = sha3_256(encoded) or return Err(Error("secure.digest: input exceeds the digest budget"))
    return Ok("sha3-256:" + value)
}

// The all-zero digest: the conventional "no previous record" link at the
// start of a chain. No known input hashes to it.
fn zero_digest() -> String {
    return "sha3-256:0000000000000000000000000000000000000000000000000000000000000000"
}

// True when `value` has the shape this module produces.
fn is_digest(value: String) -> Bool {
    let pieces = value.split(":")
    if pieces.length() != 2 {
        return false
    }
    let algorithm = pieces.get(0) or return false
    let hex = pieces.get(1) or return false
    if algorithm != "sha3-256" || hex.length() != 64 {
        return false
    }
    // Removing every lowercase hex digit must leave nothing behind.
    let mut rest = hex
    for symbol in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"] {
        rest = "".join(rest.split(symbol)) or return false
    }
    return rest.length() == 0
}

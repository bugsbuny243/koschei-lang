// Koschei Core Library — Marvel universe: odin
//
// Capability derivation, after the seL4 capability derivation tree. A root
// grant names a holder, a set of rights and the last epoch it is good for.
// Every other grant is derived from one: never wider (a subset of the
// parent's rights), never longer-lived (it ends no later than the parent) and
// one level deeper, at most `max_depth()` levels. `check` honours a grant
// only through its whole chain back to the root and re-checks each link, so
// a hand-built chain that widens is refused (complete mediation), and
// revoking one grant revokes every grant derived from it.
//
// Grants are decision values over application data (API keys, delegated
// roles); they confer no Koschei runtime authority, which only travels as
// capability tokens. A digest is not a signature: anyone can build a
// canonical grant. `seal` binds a grant to a secret key with HMAC-SHA256 and
// `check_sealed` refuses a chain with a link the key did not seal.
import secure
import text

struct Grant {
    // The parent grant's digest; `secure.zero_digest()` for a root.
    parent: String,
    holder: String,
    // Canonical: distinct names in ascending order (`text.unique_sorted`).
    rights: List<String>,
    // The last epoch at which the grant may be used.
    not_after: Int,
    // 0 for a root, parent depth + 1 otherwise.
    depth: Int,
    grant_digest: String,
}

struct GrantVerdict {
    allowed: Bool,
    reason: String,
    // The index of the first chain link that failed; `None` when allowed or
    // when the chain is empty.
    failed_link: Option<Int>,
}

// The deepest derivation `derive` accepts; a root has depth 0.
fn max_depth() -> Int {
    return 16
}

// Builds the canonical grant for these fields; `root` and `derive` call it.
// Public only because Koschei v1 has no private functions; it checks the
// field shapes, not the derivation rules.
fn issue(parent: String, holder: String, rights: List<String>, not_after: Int, depth: Int) -> Result<Grant, Error> {
    if !secure.is_digest(parent) {
        return Err(Error("odin.issue: parent must be a sha3-256 digest"))
    }
    if holder.length() == 0 {
        return Err(Error("odin.issue: holder must be explicit"))
    }
    if rights.contains("") {
        return Err(Error("odin.issue: a right must be named"))
    }
    if not_after < 0 || depth < 0 || depth > max_depth() {
        return Err(Error("odin.issue: invalid lifetime or depth"))
    }
    let canonical = text.unique_sorted(rights)
    let mut parts = [parent, holder, "{not_after}", "{depth}", "{canonical.length()}"]
    for right in canonical {
        parts = parts.push(right)
    }
    let digest = secure.digest("koschei.marvel.odin.grant/v1", parts) or return Err(Error("odin.issue: grant is too large to digest"))
    return Ok(Grant {
        parent: parent,
        holder: holder,
        rights: canonical,
        not_after: not_after,
        depth: depth,
        grant_digest: digest,
    })
}

fn root(holder: String, rights: List<String>, not_after: Int) -> Result<Grant, Error> {
    return issue(secure.zero_digest(), holder, rights, not_after, 0)
}

// A grant for `holder` derived from `parent`: only rights the parent holds,
// a lifetime that ends no later and one level deeper.
fn derive(parent: Grant, holder: String, rights: List<String>, not_after: Int) -> Result<Grant, Error> {
    if !is_canonical(parent) {
        return Err(Error("odin.derive: canonical parent required"))
    }
    for right in rights {
        if !parent.rights.contains(right) {
            return Err(Error("odin.derive: rights must be a subset of the parent's"))
        }
    }
    if not_after > parent.not_after {
        return Err(Error("odin.derive: a grant cannot outlive its parent"))
    }
    if parent.depth >= max_depth() {
        return Err(Error("odin.derive: derivation is too deep"))
    }
    return issue(parent.grant_digest, holder, rights, not_after, parent.depth + 1)
}

// True when `grant` is exactly what `issue` returns for its fields. A digest
// is not a signature; this detects edited or hand-built grants, not who
// issued them.
fn is_canonical(grant: Grant) -> Bool {
    let expected = issue(grant.parent, grant.holder, grant.rights, grant.not_after, grant.depth)
    return match expected {
        Ok(value) => value.rights == grant.rights && value.grant_digest == grant.grant_digest,
        Err(_) => false,
    }
}

fn denied(reason: String, link: Int) -> GrantVerdict {
    return GrantVerdict { allowed: false, reason: reason, failed_link: Some(link) }
}

// Whether the last grant of `chain` (root first) allows `right` at `epoch`.
// Every link must be canonical, name its predecessor, be one level deeper,
// hold no right its predecessor lacks, end no later, be absent from `revoked`
// (grant digests) and not have expired; the last link must hold `right`.
// Links are checked from the root, so a revoked ancestor denies its whole
// subtree.
fn check(chain: List<Grant>, right: String, epoch: Int, revoked: List<String>) -> GrantVerdict {
    if chain.length() == 0 {
        return GrantVerdict { allowed: false, reason: "empty chain", failed_link: None() }
    }
    let mut index = 0
    let mut previous: Option<Grant> = None()
    let mut holds = false
    for grant in chain {
        if !is_canonical(grant) {
            return denied("grant is not canonical", index)
        }
        match previous {
            None => {
                if grant.depth != 0 || grant.parent != secure.zero_digest() {
                    return denied("chain does not start at a root", index)
                }
            },
            Some(parent) => {
                if grant.parent != parent.grant_digest || grant.depth != parent.depth + 1 {
                    return denied("broken chain", index)
                }
                for name in grant.rights {
                    if !parent.rights.contains(name) {
                        return denied("widened rights", index)
                    }
                }
                if grant.not_after > parent.not_after {
                    return denied("outlives its parent", index)
                }
            },
        }
        if revoked.contains(grant.grant_digest) {
            return denied("revoked", index)
        }
        if epoch > grant.not_after {
            return denied("expired", index)
        }
        holds = grant.rights.contains(right)
        previous = Some(grant)
        index = index + 1
    }
    if !holds {
        return denied("right not granted", index - 1)
    }
    return GrantVerdict { allowed: true, reason: "allowed", failed_link: None() }
}

// The lowercase hex HMAC-SHA256 of the grant digest under `key`.
fn seal(grant: Grant, key: Bytes) -> String {
    return hmac_sha256(key, grant.grant_digest.to_bytes())
}

// `check`, after requiring that `key` sealed every link: `seals[i]` belongs
// to `chain[i]` and is compared in constant time.
fn check_sealed(chain: List<Grant>, seals: List<String>, key: Bytes, right: String, epoch: Int, revoked: List<String>) -> GrantVerdict {
    if seals.length() != chain.length() {
        return GrantVerdict { allowed: false, reason: "one seal per link required", failed_link: None() }
    }
    let mut index = 0
    for grant in chain {
        let given = seals.get(index) or ""
        if !secure_equal(seal(grant, key), given) {
            return denied("seal mismatch", index)
        }
        index = index + 1
    }
    return check(chain, right, epoch, revoked)
}

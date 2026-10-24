// Koschei Core Library — Marvel universe: hela
//
// Irreversible authority death. A tombstone records that a principal's
// authority was revoked at an epoch. From that epoch on, the authority stays
// dead: replay, a stale epoch, another reality or a forked state cannot bring
// it back.
//
// Decisions match the Python guardian `koschei/hela_authority_death_v1.py`
// for canonical tombstones. Digest inputs are `secure` digests ("sha3-256:" +
// 64 hex) rather than raw 32-byte values, and the tombstone digest uses the
// domain-separated `secure.digest` encoding, so it differs from the Python
// byte layout.

import secure

struct AuthorityTombstone {
    principal_digest: String,
    authority_id: String,
    death_epoch: Int,
    reality_digest: String,
    cause_digest: String,
    // `secure.zero_digest()` for the first tombstone of a chain.
    previous_tombstone: String,
    tombstone_digest: String,
}

fn bury(principal_digest: String, authority_id: String, death_epoch: Int, reality_digest: String, cause_digest: String, previous_tombstone: String) -> Result<AuthorityTombstone, Error> {
    if !secure.is_digest(principal_digest) {
        return Err(Error("hela.bury: principal_digest must be a sha3-256 digest"))
    }
    if !secure.is_digest(reality_digest) {
        return Err(Error("hela.bury: reality_digest must be a sha3-256 digest"))
    }
    if !secure.is_digest(cause_digest) {
        return Err(Error("hela.bury: cause_digest must be a sha3-256 digest"))
    }
    if !secure.is_digest(previous_tombstone) {
        return Err(Error("hela.bury: previous_tombstone must be a sha3-256 digest"))
    }
    if authority_id.length() == 0 || death_epoch < 1 {
        return Err(Error("hela.bury: invalid authority/death epoch"))
    }
    let parts = [principal_digest, authority_id, "{death_epoch}", reality_digest, cause_digest, previous_tombstone]
    let digest = secure.digest("koschei.marvel.hela.tombstone/v1", parts) or return Err(Error("hela.bury: tombstone is too large to digest"))
    return Ok(AuthorityTombstone {
        principal_digest: principal_digest,
        authority_id: authority_id,
        death_epoch: death_epoch,
        reality_digest: reality_digest,
        cause_digest: cause_digest,
        previous_tombstone: previous_tombstone,
        tombstone_digest: digest,
    })
}

// True when `tombstone` is exactly what `bury` returns for its fields. A
// digest is not a signature; this detects edited or hand-built tombstones,
// not who buried the authority.
fn is_canonical(tombstone: AuthorityTombstone) -> Bool {
    let buried = bury(tombstone.principal_digest, tombstone.authority_id, tombstone.death_epoch, tombstone.reality_digest, tombstone.cause_digest, tombstone.previous_tombstone)
    return match buried {
        Ok(expected) => expected.tombstone_digest == tombstone.tombstone_digest,
        Err(_) => false,
    }
}

// True when the candidate authority is still dead. Fails closed: a malformed
// principal digest or a tombstone that is not canonical counts as dead.
fn remains_dead(tombstone: AuthorityTombstone, principal_digest: String, authority_id: String, candidate_epoch: Int) -> Bool {
    if !secure.is_digest(principal_digest) || !is_canonical(tombstone) {
        return true
    }
    return principal_digest == tombstone.principal_digest && authority_id == tombstone.authority_id && candidate_epoch >= tombstone.death_epoch
}

// The same decision, named for the caller that is about to grant authority.
fn is_resurrection_attempt(tombstone: AuthorityTombstone, principal_digest: String, authority_id: String, candidate_epoch: Int) -> Bool {
    return remains_dead(tombstone, principal_digest, authority_id, candidate_epoch)
}

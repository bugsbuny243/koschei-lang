// Koschei Core Library — Marvel universe: wanda
//
// Tamper-evident reality commitments. A reality may evolve epoch by epoch,
// but a past that was already admitted cannot be silently rewritten: each
// commitment links to the one before it, and two different commitments for
// the same reality and epoch are a fork.
//
// Decisions match the Python guardian `koschei/wanda_reality_integrity_v1.py`
// for canonical commitments. Digest inputs are `secure` digests, and the
// commitment digest uses the domain-separated `secure.digest` encoding, so it
// differs from the Python byte layout. A commitment that is not canonical
// gets the fail-closed answer from every check.

import secure

struct RealityCommitment {
    reality_id: String,
    epoch: Int,
    state_digest: String,
    authority_digest: String,
    // `secure.zero_digest()` for the first commitment of a reality.
    previous_commitment: String,
    commitment_digest: String,
}

fn commit(reality_id: String, epoch: Int, state_digest: String, authority_digest: String, previous_commitment: String) -> Result<RealityCommitment, Error> {
    if reality_id.length() == 0 || epoch < 0 {
        return Err(Error("wanda.commit: invalid reality identity/epoch"))
    }
    if !secure.is_digest(state_digest) {
        return Err(Error("wanda.commit: state_digest must be a sha3-256 digest"))
    }
    if !secure.is_digest(authority_digest) {
        return Err(Error("wanda.commit: authority_digest must be a sha3-256 digest"))
    }
    if !secure.is_digest(previous_commitment) {
        return Err(Error("wanda.commit: previous_commitment must be a sha3-256 digest"))
    }
    let parts = [reality_id, "{epoch}", state_digest, authority_digest, previous_commitment]
    let digest = secure.digest("koschei.marvel.wanda.commitment/v1", parts) or return Err(Error("wanda.commit: commitment is too large to digest"))
    return Ok(RealityCommitment {
        reality_id: reality_id,
        epoch: epoch,
        state_digest: state_digest,
        authority_digest: authority_digest,
        previous_commitment: previous_commitment,
        commitment_digest: digest,
    })
}

// True when `commitment` is exactly what `commit` returns for its fields. A
// digest is not a signature; this detects edited or hand-built commitments,
// not who committed them.
fn is_canonical(commitment: RealityCommitment) -> Bool {
    let expected = commit(commitment.reality_id, commitment.epoch, commitment.state_digest, commitment.authority_digest, commitment.previous_commitment)
    return match expected {
        Ok(value) => value.commitment_digest == commitment.commitment_digest,
        Err(_) => false,
    }
}

// True when `child` is the next epoch of `parent` and links to it.
fn extends(parent: RealityCommitment, child: RealityCommitment) -> Bool {
    if !is_canonical(parent) || !is_canonical(child) {
        return false
    }
    // Canonical epochs are non-negative, so the difference cannot overflow.
    return parent.reality_id == child.reality_id && child.epoch - parent.epoch == 1 && child.previous_commitment == parent.commitment_digest
}

// True when two different commitments claim the same reality and epoch.
// Fails closed: a commitment that is not canonical counts as a fork.
fn detects_fork(first: RealityCommitment, second: RealityCommitment) -> Bool {
    if !is_canonical(first) || !is_canonical(second) {
        return true
    }
    return first.reality_id == second.reality_id && first.epoch == second.epoch && first.commitment_digest != second.commitment_digest
}

// True when `candidate` would move `current` back to the same or an earlier
// epoch. Fails closed: a commitment that is not canonical counts as a rollback.
fn detects_rollback(current: RealityCommitment, candidate: RealityCommitment) -> Bool {
    if !is_canonical(current) || !is_canonical(candidate) {
        return true
    }
    return current.reality_id == candidate.reality_id && candidate.epoch <= current.epoch
}

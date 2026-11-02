// Koschei Core Library: matrix_horizon
// Matrix/Hara pure horizon policy, not the durable SQLite event-horizon fence.
// This module ports the deterministic cross-Matrix transition requirements:
// unchanged Veyra/Aevra, different Matrix/Hara and exactly the next epoch.
// A head digest is an integrity checksum, NOT a signature or proof of which
// Hara is currently authorized. The caller must use the independently
// authenticated durable Python fence for atomic tombstones and anti-replay.
// It creates no authority, performs no I/O and never changes durable state.

import secure

// A *proposed* Matrix horizon, not the durable current record.
// All digest fields use Koschei domain-separated SHA3-256 text digests;
// the Python reference's SHA-256 byte encoding is deliberately different.
struct MatrixHorizonProposal {
    veyra_digest: String,
    aevra_digest: String,
    matrix_digest: String,
    hara_digest: String,
    epoch: Int,
    previous_hara_digest: String,
    cause_digest: String,
    record_digest: String,
}

// Public because v1 has no private functions. A record that can be
// constructed is only a self-consistent *claim*. It cannot admit execution.
fn record(veyra_digest: String, aevra_digest: String, matrix_digest: String, hara_digest: String, epoch: Int, previous_hara_digest: String, cause_digest: String) -> Result<MatrixHorizonProposal, Error> {
    if !secure.is_digest(veyra_digest) || veyra_digest == secure.zero_digest() {
        return Err(Error("matrix_horizon.record: invalid Veyra digest"))
    }
    if !secure.is_digest(aevra_digest) || aevra_digest == secure.zero_digest() {
        return Err(Error("matrix_horizon.record: invalid Aevra digest"))
    }
    if !secure.is_digest(matrix_digest) || matrix_digest == secure.zero_digest() {
        return Err(Error("matrix_horizon.record: invalid Matrix digest"))
    }
    if !secure.is_digest(hara_digest) || hara_digest == secure.zero_digest() {
        return Err(Error("matrix_horizon.record: invalid Hara digest"))
    }
    if !secure.is_digest(previous_hara_digest) {
        return Err(Error("matrix_horizon.record: invalid previous Hara digest"))
    }
    if !secure.is_digest(cause_digest) || cause_digest == secure.zero_digest() {
        return Err(Error("matrix_horizon.record: invalid cause digest"))
    }
    if epoch < 0 || previous_hara_digest == hara_digest {
        return Err(Error("matrix_horizon.record: invalid horizon epoch or self predecessor"))
    }
    let parts = [veyra_digest, aevra_digest, matrix_digest, hara_digest, "{epoch}", previous_hara_digest, cause_digest]
    let digest = secure.digest("koschei.matrix.horizon.proposal/v1", parts) or return Err(Error("matrix_horizon.record: digest budget exceeded"))
    return Ok(MatrixHorizonProposal {
        veyra_digest: veyra_digest,
        aevra_digest: aevra_digest,
        matrix_digest: matrix_digest,
        hara_digest: hara_digest,
        epoch: epoch,
        previous_hara_digest: previous_hara_digest,
        cause_digest: cause_digest,
        record_digest: digest,
    })
}

// Construct a genesis *proposal*. An external durable fence still has to
// initialize the current Hara atomically and reject duplicate initialization.
fn genesis(veyra_digest: String, aevra_digest: String, matrix_digest: String, hara_digest: String, epoch: Int, cause_digest: String) -> Result<MatrixHorizonProposal, Error> {
    return record(veyra_digest, aevra_digest, matrix_digest, hara_digest, epoch, secure.zero_digest(), cause_digest)
}

// Recompute the complete proposal's content digest. Not an issuer signature;
// a caller can construct a new consistent proposal without authorization.
fn is_canonical(head: MatrixHorizonProposal) -> Bool {
    let rebuilt = record(head.veyra_digest, head.aevra_digest, head.matrix_digest, head.hara_digest, head.epoch, head.previous_hara_digest, head.cause_digest)
    return match rebuilt {
        Ok(value) => value.record_digest == head.record_digest,
        Err(_) => false,
    }
}

// Pure preparation gate reflecting DurableMatrixHorizonFence.advance's
// identity and next-epoch checks; it does NOT update SQLite, tombstone old
// Haras, fence stale writers, or prove the supplied head is current.
// The caller MUST independently authenticate the current durable head.
fn propose_transition(current: MatrixHorizonProposal, next_veyra_digest: String, next_aevra_digest: String, next_matrix_digest: String, next_hara_digest: String, next_epoch: Int, cause_digest: String) -> Result<MatrixHorizonProposal, Error> {
    if !is_canonical(current) {
        return Err(Error("matrix_horizon.propose_transition: canonical current proposal required"))
    }
    if next_veyra_digest != current.veyra_digest || next_aevra_digest != current.aevra_digest {
        return Err(Error("matrix_horizon.propose_transition: cannot change Veyra or Aevra"))
    }
    if next_matrix_digest == current.matrix_digest {
        return Err(Error("matrix_horizon.propose_transition: different Matrix required"))
    }
    if next_hara_digest == current.hara_digest {
        return Err(Error("matrix_horizon.propose_transition: new Hara required"))
    }
    if next_epoch <= current.epoch || next_epoch - current.epoch != 1 {
        return Err(Error("matrix_horizon.propose_transition: exactly the next epoch required"))
    }
    // Immediate rollback to the known predecessor can be rejected locally.
    // Longer-term replay prevention still needs the durable tombstone ledger.
    if next_hara_digest == current.previous_hara_digest {
        return Err(Error("matrix_horizon.propose_transition: predecessor Hara is stale"))
    }
    return record(current.veyra_digest, current.aevra_digest, next_matrix_digest, next_hara_digest, next_epoch, current.hara_digest, cause_digest)
}

// Compare a proposal with a CALLER-SUPPLIED observation; this is not
// require_current(), because only the durable fence knows current state.
fn matches_snapshot(head: MatrixHorizonProposal, veyra_digest: String, aevra_digest: String, matrix_digest: String, hara_digest: String, epoch: Int) -> Bool {
    if !is_canonical(head) {
        return false
    }
    return head.veyra_digest == veyra_digest && head.aevra_digest == aevra_digest && head.matrix_digest == matrix_digest && head.hara_digest == hara_digest && head.epoch == epoch
}

// Koschei Core Library — Marvel universe: vormir
//
// Sacrifice before rebirth. To come back at the next epoch, an authority must
// give something up: the commitment names the authority it surrenders and a
// different one it asks for, and moves exactly one epoch forward. The root of
// the next epoch is admitted only for that artifact, at that epoch, once the
// surrendered authority is revoked.
//
// The epoch-sacrifice receipt binds a sacrificed epoch to its successor with
// at least two independent witnesses (distinct domains, distinct evidence).
//
// Decisions, error causes and digests match the Python guardian
// `koschei/vormir_sacrifice_v1.py` byte for byte: digests are raw 32-byte
// `Bytes`, and each sealed digest is the lowercase hex SHA3-256 of the same
// byte layout. The durable part (tombstoning the old epoch on disk before the
// successor is accepted, `commit_vormir_epoch_sacrifice_v1`) stays in the
// host: it needs a durable fence, which a library module cannot hold.

struct VormirCommitment {
    principal_digest: Bytes,
    artifact_digest: Bytes,
    surrendered_authority: String,
    requested_authority: String,
    prior_epoch: Int,
    next_epoch: Int,
    hardware_attestation_digest: Bytes,
    verifier_digest: Bytes,
    // Lowercase hex SHA3-256 of the commitment layout.
    commitment_digest: String,
}

struct VormirWitness {
    domain_digest: Bytes,
    evidence_digest: Bytes,
}

struct VormirEpochReceipt {
    activation_plan_digest: String,
    sacrificed_epoch: Int,
    successor_epoch: Int,
    previous_state_digest: String,
    fresh_state_digest: String,
    rebirth_receipt_digest: String,
    tombstone_record_digest: String,
    // Canonical order: sorted by domain, then evidence.
    witnesses: List<VormirWitness>,
    sacrifice_digest: String,
}

// The context prefix, NUL-terminated as in the Python layout.
fn context() -> Bytes {
    let nul = bytes_from_hex("00") or return "koschei.vormir-sacrifice/v1".to_bytes()
    return "koschei.vormir-sacrifice/v1".to_bytes() + nul
}

fn nul() -> Bytes {
    return bytes_from_hex("00") or "".to_bytes()
}

fn is_digest32(value: Bytes) -> Bool {
    return value.length() == 32
}

fn commit(principal_digest: Bytes, artifact_digest: Bytes, surrendered_authority: String, requested_authority: String, prior_epoch: Int, next_epoch: Int, hardware_attestation_digest: Bytes, verifier_digest: Bytes) -> Result<VormirCommitment, Error> {
    if !is_digest32(principal_digest) {
        return Err(Error("principal_digest must be exactly 32 bytes"))
    }
    if !is_digest32(artifact_digest) {
        return Err(Error("artifact_digest must be exactly 32 bytes"))
    }
    if !is_digest32(hardware_attestation_digest) {
        return Err(Error("hardware_attestation_digest must be exactly 32 bytes"))
    }
    if !is_digest32(verifier_digest) {
        return Err(Error("verifier_digest must be exactly 32 bytes"))
    }
    if surrendered_authority.length() == 0 || requested_authority.length() == 0 {
        return Err(Error("authorities must be explicit"))
    }
    if surrendered_authority == requested_authority {
        return Err(Error("sacrifice must attenuate a distinct authority"))
    }
    if prior_epoch < 0 || next_epoch != prior_epoch + 1 {
        return Err(Error("Vormir requires exactly one monotonic epoch transition"))
    }
    let sep = nul()
    let layout = context() + principal_digest + sep + artifact_digest + sep + surrendered_authority.to_bytes() + sep + requested_authority.to_bytes() + sep + "{prior_epoch}".to_bytes() + sep + "{next_epoch}".to_bytes() + sep + hardware_attestation_digest + sep + verifier_digest
    let digest = sha3_256_bytes(layout) or return Err(Error("vormir.commit: commitment is too large to digest"))
    return Ok(VormirCommitment {
        principal_digest: principal_digest,
        artifact_digest: artifact_digest,
        surrendered_authority: surrendered_authority,
        requested_authority: requested_authority,
        prior_epoch: prior_epoch,
        next_epoch: next_epoch,
        hardware_attestation_digest: hardware_attestation_digest,
        verifier_digest: verifier_digest,
        commitment_digest: digest,
    })
}

// True when `commitment` is exactly what `commit` returns for its fields.
fn is_canonical(commitment: VormirCommitment) -> Bool {
    let rebuilt = commit(commitment.principal_digest, commitment.artifact_digest, commitment.surrendered_authority, commitment.requested_authority, commitment.prior_epoch, commitment.next_epoch, commitment.hardware_attestation_digest, commitment.verifier_digest)
    return match rebuilt {
        Ok(expected) => expected.commitment_digest == commitment.commitment_digest,
        Err(_) => false,
    }
}

// The commitment-only gate (`admits_vormir_root_v1`): the surrendered
// authority is the one revoked, the epoch is the committed next epoch and
// the artifact is the committed one. Fails closed on a malformed artifact
// digest or a commitment that is not canonical (the Python gate only checks
// the type; a hand-edited record is refused here).
fn admits_root(commitment: VormirCommitment, revoked_authority: String, observed_epoch: Int, observed_artifact_digest: Bytes) -> Bool {
    if !is_digest32(observed_artifact_digest) || !is_canonical(commitment) {
        return false
    }
    return revoked_authority == commitment.surrendered_authority && observed_epoch == commitment.next_epoch && observed_artifact_digest == commitment.artifact_digest
}

// Why `witnesses` cannot be canonicalized, or "" when they can
// (`_canonical_epoch_witnesses` and the witness checks of `__post_init__`).
fn witness_problem(witnesses: List<VormirWitness>) -> String {
    for witness in witnesses {
        if !is_digest32(witness.domain_digest) {
            return "Vormir witness domain_digest must be exactly 32 bytes"
        }
        if !is_digest32(witness.evidence_digest) {
            return "Vormir witness evidence_digest must be exactly 32 bytes"
        }
    }
    if witnesses.length() < 2 {
        return "Vormir requires at least two witness domains"
    }
    let mut domains: List<String> = []
    let mut evidence: List<String> = []
    for witness in witnesses {
        domains = domains.push(witness.domain_digest.hex())
        evidence = evidence.push(witness.evidence_digest.hex())
    }
    if domains.unique().length() != domains.length() {
        return "Vormir witness domains must be distinct"
    }
    if evidence.unique().length() != evidence.length() {
        return "Vormir witness evidence must be distinct"
    }
    return ""
}

// Witnesses in canonical order (`_canonical_epoch_witnesses`): at least two,
// distinct domains, distinct evidence, sorted by domain then evidence.
fn canonical_witnesses(witnesses: List<VormirWitness>) -> Result<List<VormirWitness>, Error> {
    let problem = witness_problem(witnesses)
    if problem != "" {
        return Err(Error(problem))
    }
    let mut keys: List<String> = []
    for witness in witnesses {
        // Fixed-width lowercase hex sorts in byte order; the separator sits at
        // the same position in every key.
        keys = keys.push(witness.domain_digest.hex() + ":" + witness.evidence_digest.hex())
    }
    let ordered_keys = keys.sort() or return Err(Error("vormir: witness keys cannot be sorted"))
    let mut sorted: List<VormirWitness> = []
    for key in ordered_keys {
        let halves = key.split(":")
        let domain_hex = halves.get(0) or return Err(Error("vormir: witness key is malformed"))
        let evidence_hex = halves.get(1) or return Err(Error("vormir: witness key is malformed"))
        let domain = bytes_from_hex(domain_hex) or return Err(Error("vormir: witness key is malformed"))
        let item = bytes_from_hex(evidence_hex) or return Err(Error("vormir: witness key is malformed"))
        sorted = sorted.push(VormirWitness { domain_digest: domain, evidence_digest: item })
    }
    return Ok(sorted)
}

// `_epoch_sacrifice_digest`: lowercase hex SHA3-256 of the receipt layout.
fn sacrifice_digest(activation_plan_digest: String, sacrificed_epoch: Int, successor_epoch: Int, previous_state_digest: String, fresh_state_digest: String, rebirth_receipt_digest: String, tombstone_record_digest: String, witnesses: List<VormirWitness>) -> Result<String, Error> {
    let sep = nul()
    let mut layout = context() + "epoch-sacrifice".to_bytes() + sep + activation_plan_digest.to_bytes() + sep + "{sacrificed_epoch}".to_bytes() + sep + "{successor_epoch}".to_bytes() + sep + previous_state_digest.to_bytes() + sep + fresh_state_digest.to_bytes() + sep + rebirth_receipt_digest.to_bytes() + sep + tombstone_record_digest.to_bytes()
    for witness in witnesses {
        layout = layout + sep + "W".to_bytes() + sep + witness.domain_digest + witness.evidence_digest
    }
    let digest = sha3_256_bytes(layout) or return Err(Error("vormir: receipt is too large to digest"))
    return Ok(digest)
}

// Seals a receipt from fields the durable host step produced.
fn seal(activation_plan_digest: String, sacrificed_epoch: Int, successor_epoch: Int, previous_state_digest: String, fresh_state_digest: String, rebirth_receipt_digest: String, tombstone_record_digest: String, witnesses: List<VormirWitness>) -> Result<VormirEpochReceipt, Error> {
    if sacrificed_epoch < 1 || successor_epoch != sacrificed_epoch + 1 {
        return Err(Error("Vormir epoch sacrifice is not monotonic"))
    }
    let problem = witness_problem(witnesses)
    if problem != "" {
        return Err(Error(problem))
    }
    let ordered = canonical_witnesses(witnesses) or return Err(Error(problem))
    let digest = sacrifice_digest(activation_plan_digest, sacrificed_epoch, successor_epoch, previous_state_digest, fresh_state_digest, rebirth_receipt_digest, tombstone_record_digest, ordered) or return Err(Error("vormir: receipt is too large to digest"))
    return Ok(VormirEpochReceipt {
        activation_plan_digest: activation_plan_digest,
        sacrificed_epoch: sacrificed_epoch,
        successor_epoch: successor_epoch,
        previous_state_digest: previous_state_digest,
        fresh_state_digest: fresh_state_digest,
        rebirth_receipt_digest: rebirth_receipt_digest,
        tombstone_record_digest: tombstone_record_digest,
        witnesses: ordered,
        sacrifice_digest: digest,
    })
}

// `assert_sealed`: the reason a receipt is not sealed, or "" when it is.
fn seal_problem(receipt: VormirEpochReceipt) -> String {
    if receipt.sacrificed_epoch < 1 || receipt.successor_epoch != receipt.sacrificed_epoch + 1 {
        return "Vormir epoch sacrifice is not monotonic"
    }
    if receipt.witnesses.length() < 2 {
        return "Vormir requires at least two witness domains"
    }
    let mut domains: List<String> = []
    let mut evidence: List<String> = []
    for witness in receipt.witnesses {
        domains = domains.push(witness.domain_digest.hex())
        evidence = evidence.push(witness.evidence_digest.hex())
    }
    if domains.unique().length() != domains.length() {
        return "Vormir witness domains must be distinct"
    }
    if evidence.unique().length() != evidence.length() {
        return "Vormir witness evidence must be distinct"
    }
    for witness in receipt.witnesses {
        if !is_digest32(witness.domain_digest) {
            return "Vormir witness domain must be exactly 32 bytes"
        }
        if !is_digest32(witness.evidence_digest) {
            return "Vormir witness evidence must be exactly 32 bytes"
        }
    }
    let expected = sacrifice_digest(receipt.activation_plan_digest, receipt.sacrificed_epoch, receipt.successor_epoch, receipt.previous_state_digest, receipt.fresh_state_digest, receipt.rebirth_receipt_digest, receipt.tombstone_record_digest, receipt.witnesses) or return "Vormir epoch sacrifice seal mismatch"
    if expected != receipt.sacrifice_digest {
        return "Vormir epoch sacrifice seal mismatch"
    }
    return ""
}

fn is_sealed(receipt: VormirEpochReceipt) -> Bool {
    return seal_problem(receipt) == ""
}

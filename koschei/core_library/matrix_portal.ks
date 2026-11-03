// Koschei Core Library: matrix_portal
// Pure cross-Reality portal proposal: identity and integrity binding only.
// A connection does NOT grant network, disk, execution or delegation rights.
// This ports eligibility checks from matrix_portal_transit_v1.py into .ks.
// The digest is Koschei's typed, domain-separated SHA3-256 text encoding;
// it is NOT byte-compatible with the host Python proof's wire encoding.
// Caller must independently authenticate current Reality commitments,
// authorize the effect and target, and enforce replay/persistence policy.

import secure
import wanda

// Content-bound portal *proposal*, not a signed grant or an executed transit.
// Public fields are mutable copies: match() reconstructs from canonical Wanda
// commitments and independently rechecks every field before accepting.
struct PortalTransitProposal {
    source_reality: String,
    destination_reality: String,
    source_commitment: String,
    destination_commitment: String,
    payload_digest: String,
    effect: String,
    target_digest: String,
    epoch: Int,
    transit_digest: String,
}

// Prepare a cross-Reality portal proposal without performing an effect.
// It does not authenticate the record issuer or authorize the destination.
fn propose(source: RealityCommitment, destination: RealityCommitment, payload_digest: String, effect: String, target_digest: String, epoch: Int) -> Result<PortalTransitProposal, Error> {
    if !wanda.is_canonical(source) || !wanda.is_canonical(destination) {
        return Err(Error("matrix_portal.propose: canonical Reality commitments required"))
    }
    if source.reality_id == destination.reality_id {
        return Err(Error("matrix_portal.propose: distinct Realities required"))
    }
    if !secure.is_digest(payload_digest) || !secure.is_digest(target_digest) {
        return Err(Error("matrix_portal.propose: invalid payload or target digest"))
    }
    if effect.length() == 0 || epoch < 0 {
        return Err(Error("matrix_portal.propose: explicit effect and valid epoch required"))
    }
    let parts = [
        source.reality_id,
        destination.reality_id,
        source.commitment_digest,
        destination.commitment_digest,
        payload_digest,
        effect,
        target_digest,
        "{epoch}",
    ]
    let digest = secure.digest("koschei.matrix.portal.transit.proposal/v1", parts) or return Err(Error("matrix_portal.propose: digest budget exceeded"))
    return Ok(PortalTransitProposal {
        source_reality: source.reality_id,
        destination_reality: destination.reality_id,
        source_commitment: source.commitment_digest,
        destination_commitment: destination.commitment_digest,
        payload_digest: payload_digest,
        effect: effect,
        target_digest: target_digest,
        epoch: epoch,
        transit_digest: digest,
    })
}

// Recreate expected proof against CALLER-PROVIDED canonical Wanda records.
// A changed Reality commitment, payload, requested effect, target or epoch
// fails closed, including when the proposal's digest is manually forged.
// The returned Bool is an integrity comparison, not execution admission.
fn matches(proof: PortalTransitProposal, source: RealityCommitment, destination: RealityCommitment, payload_digest: String, effect: String, target_digest: String, epoch: Int) -> Bool {
    let recreated = propose(source, destination, payload_digest, effect, target_digest, epoch)
    return match recreated {
        Ok(expected) => proof.source_reality == expected.source_reality
            && proof.destination_reality == expected.destination_reality
            && proof.source_commitment == expected.source_commitment
            && proof.destination_commitment == expected.destination_commitment
            && proof.payload_digest == expected.payload_digest
            && proof.effect == expected.effect
            && proof.target_digest == expected.target_digest
            && proof.epoch == expected.epoch
            && proof.transit_digest == expected.transit_digest,
        Err(_) => false,
    }
}

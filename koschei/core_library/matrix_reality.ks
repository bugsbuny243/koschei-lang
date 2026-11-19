// Koschei Core Library — Matrix universe: matrix_reality
//
// A Matrix is the local execution reality inside one Veyra; a Hara is the
// horizon of one Aevra (one program) inside that Matrix. Two programs may
// share a Matrix and still not share a Hara. An admission binds one Matrix,
// one Hara, one Aevra, one Veyra, one native MIR fingerprint and one epoch.
// Nothing here grants authority.
//
// Ports `koschei/matrix_reality_v1.py`: the same checks, the same error
// messages and byte-identical SHA-256 seals. The Veyra and Aevra identities
// (and the MIR fingerprint) are sealed by the host (`galaxy_identity_v1`);
// this module takes them as a `MatrixHost` the caller has already verified.

struct MatrixHost {
    veyra_digest: String,
    veyra_birth_epoch: Int,
    aevra_digest: String,
    aevra_birth_epoch: Int,
    mir_fingerprint: String,
}

struct MatrixIdentity {
    veyra_digest: String,
    instance_digest: String,
    reality_commitment_digest: String,
    birth_epoch: Int,
    digest: String,
}

struct HaraIdentity {
    matrix_digest: String,
    aevra_digest: String,
    horizon_commitment_digest: String,
    epoch: Int,
    digest: String,
}

struct MatrixAdmission {
    matrix_digest: String,
    hara_digest: String,
    aevra_digest: String,
    veyra_digest: String,
    native_mir_fingerprint: String,
    epoch: Int,
    evidence_digest: String,
    digest: String,
}

// `_digest64`: a 64-character non-zero hex digest, lowercased; "" when the
// text is not one. bytes_from_hex both checks the alphabet and lowercases.
fn normalized(value: String) -> String {
    if value.length() != 64 {
        return ""
    }
    let raw = bytes_from_hex(value) or return ""
    let lower = raw.hex()
    if lower == "0000000000000000000000000000000000000000000000000000000000000000" {
        return ""
    }
    return lower
}

// The reason `value` is not a digest, or "".
fn digest_problem(value: String, label: String) -> String {
    if value.length() != 64 {
        return "{label} must be a 64-character digest"
    }
    if normalized(value) == "" {
        return "{label} must be a non-zero hexadecimal digest"
    }
    return ""
}

// `_hash`: SHA-256 of context, kind, NUL and the rows joined by newlines.
fn seal(kind: String, rows: List<String>) -> String {
    let nul = bytes_from_hex("00") or return ""
    let mut text = ""
    let mut first = true
    for row in rows {
        if first {
            text = row
            first = false
        } else {
            text = text + "\n" + row
        }
    }
    let layout = "koschei.matrix-reality/v1".to_bytes() + nul + kind.to_bytes() + nul + text.to_bytes()
    return sha256_bytes(layout) or ""
}

fn matrix_seal(veyra: String, instance: String, reality: String, epoch: Int) -> String {
    return seal("matrix", ["veyra={veyra}", "instance={instance}", "reality={reality}", "epoch={epoch}"])
}

fn hara_seal(matrix: String, aevra: String, horizon: String, epoch: Int) -> String {
    return seal("hara", ["matrix={matrix}", "aevra={aevra}", "horizon={horizon}", "epoch={epoch}"])
}

fn admission_seal(admission: MatrixAdmission) -> String {
    return seal("admission", [
        "matrix={admission.matrix_digest}",
        "hara={admission.hara_digest}",
        "aevra={admission.aevra_digest}",
        "veyra={admission.veyra_digest}",
        "mir={admission.native_mir_fingerprint}",
        "epoch={admission.epoch}",
        "evidence={admission.evidence_digest}",
    ])
}

// `MatrixIdentity.assert_sealed`: why `matrix` is not sealed for this host's
// Veyra, or "".
fn matrix_problem(matrix: MatrixIdentity, host: MatrixHost) -> String {
    if matrix.veyra_digest != host.veyra_digest {
        return "Matrix belongs to a different Veyra"
    }
    let instance = digest_problem(matrix.instance_digest, "Matrix instance_digest")
    if instance != "" {
        return instance
    }
    let reality = digest_problem(matrix.reality_commitment_digest, "Matrix reality_commitment_digest")
    if reality != "" {
        return reality
    }
    if matrix.birth_epoch < host.veyra_birth_epoch {
        return "Matrix cannot predate its Veyra"
    }
    if matrix.digest != matrix_seal(matrix.veyra_digest, matrix.instance_digest, matrix.reality_commitment_digest, matrix.birth_epoch) {
        return "Matrix identity seal mismatch"
    }
    return ""
}

fn birth_matrix(host: MatrixHost, instance_digest: String, reality_commitment_digest: String, birth_epoch: Int) -> Result<MatrixIdentity, Error> {
    let instance_problem = digest_problem(instance_digest, "Matrix instance_digest")
    if instance_problem != "" {
        return Err(Error(instance_problem))
    }
    let reality_problem = digest_problem(reality_commitment_digest, "Matrix reality_commitment_digest")
    if reality_problem != "" {
        return Err(Error(reality_problem))
    }
    if birth_epoch < host.veyra_birth_epoch {
        return Err(Error("Matrix cannot predate its Veyra"))
    }
    let instance = normalized(instance_digest)
    let reality = normalized(reality_commitment_digest)
    return Ok(MatrixIdentity {
        veyra_digest: host.veyra_digest,
        instance_digest: instance,
        reality_commitment_digest: reality,
        birth_epoch: birth_epoch,
        digest: matrix_seal(host.veyra_digest, instance, reality, birth_epoch),
    })
}

fn later(left: Int, right: Int) -> Int {
    if left > right {
        return left
    }
    return right
}

// `HaraIdentity.assert_sealed`, after the Matrix is sealed.
fn hara_problem(hara: HaraIdentity, matrix: MatrixIdentity, host: MatrixHost) -> String {
    let matrix_reason = matrix_problem(matrix, host)
    if matrix_reason != "" {
        return matrix_reason
    }
    if hara.matrix_digest != matrix.digest {
        return "Hara belongs to a different Matrix"
    }
    if hara.aevra_digest != host.aevra_digest {
        return "Hara belongs to a different Aevra"
    }
    let horizon = digest_problem(hara.horizon_commitment_digest, "Hara horizon_commitment_digest")
    if horizon != "" {
        return horizon
    }
    if hara.epoch < later(matrix.birth_epoch, host.aevra_birth_epoch) {
        return "Hara cannot predate Matrix or Aevra"
    }
    if hara.digest != hara_seal(hara.matrix_digest, hara.aevra_digest, hara.horizon_commitment_digest, hara.epoch) {
        return "Hara identity seal mismatch"
    }
    return ""
}

fn birth_hara(matrix: MatrixIdentity, host: MatrixHost, horizon_commitment_digest: String, epoch: Int) -> Result<HaraIdentity, Error> {
    let matrix_reason = matrix_problem(matrix, host)
    if matrix_reason != "" {
        return Err(Error(matrix_reason))
    }
    let horizon_problem = digest_problem(horizon_commitment_digest, "Hara horizon_commitment_digest")
    if horizon_problem != "" {
        return Err(Error(horizon_problem))
    }
    if epoch < later(matrix.birth_epoch, host.aevra_birth_epoch) {
        return Err(Error("Hara cannot predate Matrix or Aevra"))
    }
    let horizon = normalized(horizon_commitment_digest)
    return Ok(HaraIdentity {
        matrix_digest: matrix.digest,
        aevra_digest: host.aevra_digest,
        horizon_commitment_digest: horizon,
        epoch: epoch,
        digest: hara_seal(matrix.digest, host.aevra_digest, horizon, epoch),
    })
}

// `MatrixAdmission.assert_sealed`, after the Matrix and Hara are sealed.
fn admission_problem(admission: MatrixAdmission, matrix: MatrixIdentity, hara: HaraIdentity, host: MatrixHost) -> String {
    let hara_reason = hara_problem(hara, matrix, host)
    if hara_reason != "" {
        return hara_reason
    }
    if admission.matrix_digest != matrix.digest {
        return "Matrix admission matrix mismatch"
    }
    if admission.hara_digest != hara.digest {
        return "Matrix admission Hara mismatch"
    }
    if admission.aevra_digest != host.aevra_digest {
        return "Matrix admission Aevra mismatch"
    }
    if admission.veyra_digest != host.veyra_digest {
        return "Matrix admission Veyra mismatch"
    }
    if admission.native_mir_fingerprint != host.mir_fingerprint {
        return "Matrix admission executable reality mismatch"
    }
    if admission.epoch != hara.epoch {
        return "Matrix admission epoch mismatch"
    }
    let evidence = digest_problem(admission.evidence_digest, "Matrix admission evidence_digest")
    if evidence != "" {
        return evidence
    }
    if admission.digest != admission_seal(admission) {
        return "Matrix admission seal mismatch"
    }
    return ""
}

fn admit(matrix: MatrixIdentity, hara: HaraIdentity, host: MatrixHost, evidence_digest: String) -> Result<MatrixAdmission, Error> {
    let hara_reason = hara_problem(hara, matrix, host)
    if hara_reason != "" {
        return Err(Error(hara_reason))
    }
    let evidence_reason = digest_problem(evidence_digest, "Matrix admission evidence_digest")
    if evidence_reason != "" {
        return Err(Error(evidence_reason))
    }
    let unsealed = MatrixAdmission {
        matrix_digest: matrix.digest,
        hara_digest: hara.digest,
        aevra_digest: host.aevra_digest,
        veyra_digest: host.veyra_digest,
        native_mir_fingerprint: host.mir_fingerprint,
        epoch: hara.epoch,
        evidence_digest: normalized(evidence_digest),
        digest: "",
    }
    return Ok(MatrixAdmission {
        matrix_digest: unsealed.matrix_digest,
        hara_digest: unsealed.hara_digest,
        aevra_digest: unsealed.aevra_digest,
        veyra_digest: unsealed.veyra_digest,
        native_mir_fingerprint: unsealed.native_mir_fingerprint,
        epoch: unsealed.epoch,
        evidence_digest: unsealed.evidence_digest,
        digest: admission_seal(unsealed),
    })
}

fn is_admitted(admission: MatrixAdmission, matrix: MatrixIdentity, hara: HaraIdentity, host: MatrixHost) -> Bool {
    return admission_problem(admission, matrix, hara, host) == ""
}

// Koschei Core Library — Galaxy identity: galaxy_identity
//
// Veyra is a customer-Galaxy identity commitment; Aevra is a living program
// identity bound to one Veyra and one compiler product. Neither grants
// authority. A copy of the bytes is not an Aevra: birth is also bound to a
// Veyra, to the compiler's native MIR (one of its sigil bindings) and to
// explicit birth evidence.
//
// Ports `koschei/galaxy_identity_v1.py`: the same checks, the same messages
// and byte-identical SHA-256 seals. The native MIR is sealed by the compiler
// (`native_sigil_mir_v1`); it comes in as a `GalaxyMir` the host verified.
// `matrix_host` turns sealed identities into the `MatrixHost` that
// `matrix_reality` takes, so the whole Matrix chain can run in Koschei.

import matrix_reality

struct VeyraIdentity {
    profile_digest: String,
    genesis_digest: String,
    constitution_digest: String,
    instance_digest: String,
    birth_epoch: Int,
    digest: String,
}

struct GalaxyBinding {
    sigil: String,
    subject: String,
}

struct GalaxyMir {
    fingerprint: String,
    bindings: List<GalaxyBinding>,
}

struct AevraIdentity {
    veyra_digest: String,
    native_mir_fingerprint: String,
    sigil: String,
    semantic_subject_digest: String,
    birth_evidence_digest: String,
    birth_epoch: Int,
    digest: String,
}

// `_require_digest`: why `value` is not a digest, or "".
fn digest_problem(value: String, label: String) -> String {
    if value.length() != 64 {
        return "{label} must be a 64-character digest"
    }
    let raw = bytes_from_hex(value) or return "{label} must be hexadecimal"
    if raw.hex() == "0000000000000000000000000000000000000000000000000000000000000000" {
        return "{label} cannot be the zero digest"
    }
    return ""
}

// The lowercase form of a valid digest.
fn lowered(value: String) -> String {
    let raw = bytes_from_hex(value) or return value
    return raw.hex()
}

// `_hash_rows`: SHA-256 of context, kind, NUL and the rows joined by newlines.
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
    let layout = "koschei.galaxy-identity/v1".to_bytes() + nul + kind.to_bytes() + nul + text.to_bytes()
    return sha256_bytes(layout) or ""
}

fn subject_digest(subject: String) -> String {
    return sha256_bytes(subject.to_bytes()) or ""
}

fn veyra_seal(profile: String, genesis: String, constitution: String, instance: String, epoch: Int) -> String {
    return seal("veyra", ["profile={profile}", "genesis={genesis}", "constitution={constitution}", "instance={instance}", "epoch={epoch}"])
}

fn aevra_seal(aevra: AevraIdentity) -> String {
    return seal("aevra", [
        "veyra={aevra.veyra_digest}",
        "mir={aevra.native_mir_fingerprint}",
        "sigil={aevra.sigil}",
        "subject={aevra.semantic_subject_digest}",
        "birth-evidence={aevra.birth_evidence_digest}",
        "epoch={aevra.birth_epoch}",
    ])
}

// The four Veyra digests in order, with their labels; "" when all are valid.
fn veyra_digest_problem(profile: String, genesis: String, constitution: String, instance: String) -> String {
    let checks = [
        digest_problem(profile, "profile_digest"),
        digest_problem(genesis, "genesis_digest"),
        digest_problem(constitution, "constitution_digest"),
        digest_problem(instance, "instance_digest"),
    ]
    for problem in checks {
        if problem != "" {
            return problem
        }
    }
    return ""
}

// `VeyraIdentity.assert_sealed`: why `veyra` is not sealed, or "".
fn veyra_problem(veyra: VeyraIdentity) -> String {
    let digests = veyra_digest_problem(veyra.profile_digest, veyra.genesis_digest, veyra.constitution_digest, veyra.instance_digest)
    if digests != "" {
        return digests
    }
    if veyra.birth_epoch < 0 {
        return "Veyra birth_epoch must be non-negative"
    }
    let expected = veyra_seal(lowered(veyra.profile_digest), lowered(veyra.genesis_digest), lowered(veyra.constitution_digest), lowered(veyra.instance_digest), veyra.birth_epoch)
    if veyra.digest != expected {
        return "Veyra identity seal mismatch"
    }
    return ""
}

fn birth_veyra(profile_digest: String, genesis_digest: String, constitution_digest: String, instance_digest: String, birth_epoch: Int) -> Result<VeyraIdentity, Error> {
    let digests = veyra_digest_problem(profile_digest, genesis_digest, constitution_digest, instance_digest)
    if digests != "" {
        return Err(Error(digests))
    }
    if birth_epoch < 0 {
        return Err(Error("Veyra birth_epoch must be non-negative"))
    }
    let profile = lowered(profile_digest)
    let genesis = lowered(genesis_digest)
    let constitution = lowered(constitution_digest)
    let instance = lowered(instance_digest)
    return Ok(VeyraIdentity {
        profile_digest: profile,
        genesis_digest: genesis,
        constitution_digest: constitution,
        instance_digest: instance,
        birth_epoch: birth_epoch,
        digest: veyra_seal(profile, genesis, constitution, instance, birth_epoch),
    })
}

// `AevraIdentity.assert_sealed`, after the Veyra is sealed.
fn aevra_problem(aevra: AevraIdentity, veyra: VeyraIdentity, mir: GalaxyMir) -> String {
    let veyra_reason = veyra_problem(veyra)
    if veyra_reason != "" {
        return veyra_reason
    }
    if aevra.veyra_digest != veyra.digest {
        return "Aevra belongs to a different Veyra"
    }
    if aevra.native_mir_fingerprint != mir.fingerprint {
        return "Aevra belongs to a different compiler product"
    }
    if aevra.birth_epoch < veyra.birth_epoch {
        return "Aevra cannot predate its Veyra"
    }
    let subject_problem = digest_problem(aevra.semantic_subject_digest, "semantic_subject_digest")
    if subject_problem != "" {
        return subject_problem
    }
    let evidence_problem = digest_problem(aevra.birth_evidence_digest, "birth_evidence_digest")
    if evidence_problem != "" {
        return evidence_problem
    }
    let mut sigil_found = false
    let mut subject_found = false
    for binding in mir.bindings {
        if binding.sigil == aevra.sigil {
            sigil_found = true
            if subject_digest(binding.subject) == aevra.semantic_subject_digest {
                subject_found = true
            }
        }
    }
    if !sigil_found {
        return "Aevra sigil is absent from native MIR"
    }
    if !subject_found {
        return "Aevra semantic subject is absent from native MIR"
    }
    if aevra.digest != aevra_seal(aevra) {
        return "Aevra identity seal mismatch"
    }
    return ""
}

fn birth_aevra(veyra: VeyraIdentity, mir: GalaxyMir, sigil: String, subject: String, birth_evidence_digest: String, birth_epoch: Int) -> Result<AevraIdentity, Error> {
    let veyra_reason = veyra_problem(veyra)
    if veyra_reason != "" {
        return Err(Error(veyra_reason))
    }
    if subject.length() == 0 {
        return Err(Error("Aevra subject cannot be empty"))
    }
    let mut named = false
    for binding in mir.bindings {
        if binding.sigil == sigil && binding.subject == subject {
            named = true
        }
    }
    if !named {
        return Err(Error("Aevra birth must name a canonical native MIR binding"))
    }
    if birth_epoch < veyra.birth_epoch {
        return Err(Error("Aevra cannot predate its Veyra"))
    }
    let evidence_problem = digest_problem(birth_evidence_digest, "birth_evidence_digest")
    if evidence_problem != "" {
        return Err(Error(evidence_problem))
    }
    let unsealed = AevraIdentity {
        veyra_digest: veyra.digest,
        native_mir_fingerprint: mir.fingerprint,
        sigil: sigil,
        semantic_subject_digest: subject_digest(subject),
        birth_evidence_digest: lowered(birth_evidence_digest),
        birth_epoch: birth_epoch,
        digest: "",
    }
    return Ok(AevraIdentity {
        veyra_digest: unsealed.veyra_digest,
        native_mir_fingerprint: unsealed.native_mir_fingerprint,
        sigil: unsealed.sigil,
        semantic_subject_digest: unsealed.semantic_subject_digest,
        birth_evidence_digest: unsealed.birth_evidence_digest,
        birth_epoch: unsealed.birth_epoch,
        digest: aevra_seal(unsealed),
    })
}

// The `MatrixHost` for `matrix_reality`, once Veyra and Aevra are sealed.
fn matrix_host(veyra: VeyraIdentity, aevra: AevraIdentity, mir: GalaxyMir) -> Result<MatrixHost, Error> {
    let problem = aevra_problem(aevra, veyra, mir)
    if problem != "" {
        return Err(Error(problem))
    }
    return Ok(MatrixHost {
        veyra_digest: veyra.digest,
        veyra_birth_epoch: veyra.birth_epoch,
        aevra_digest: aevra.digest,
        aevra_birth_epoch: aevra.birth_epoch,
        mir_fingerprint: mir.fingerprint,
    })
}

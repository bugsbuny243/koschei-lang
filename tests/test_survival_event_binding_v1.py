from dataclasses import replace
import hashlib

import pytest

from koschei.galaxy_identity_v1 import birth_aevra, birth_veyra
from koschei.khar_sathra_v1 import AxisWitness, seal_sathra
from koschei.matrix_reality_v1 import admit_matrix_hara, birth_hara, birth_matrix
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.native_sigil_request_binding_v1 import seal_effect_request
from koschei.parser import parse
from koschei.sathra_request_binding_v1 import bind_sathra_to_request
from koschei.survival_branch_v1 import SurvivalBranch, select_survival_branch
from koschei.survival_event_binding_v1 import (
    SurvivalEventBindingError,
    bind_survival_decision_to_event,
    survival_action_commitment,
)


def d(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def context(*, payload="payload-a", matrix_tag="matrix-a"):
    mir = lower_native_sigils(
        parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
    )
    veyra = birth_veyra(
        profile_digest=d("bank-profile"),
        genesis_digest=d("genesis"),
        constitution_digest=d("khar-v1"),
        instance_digest=d("bank-a"),
        birth_epoch=7,
    )
    aevra = birth_aevra(
        veyra,
        mir,
        sigil="vor",
        subject="withdrawal",
        birth_evidence_digest=d("birth"),
        birth_epoch=7,
    )
    matrix = birth_matrix(
        veyra,
        instance_digest=d(matrix_tag),
        reality_commitment_digest=d("reality:" + matrix_tag),
        birth_epoch=7,
    )
    hara = birth_hara(
        matrix,
        veyra,
        aevra,
        mir,
        horizon_commitment_digest=d("hara:" + matrix_tag),
        epoch=7,
    )
    admission = admit_matrix_hara(
        matrix,
        hara,
        veyra,
        aevra,
        mir,
        evidence_digest=d("admission:" + matrix_tag),
    )
    request = seal_effect_request(
        mir,
        effect_id="withdrawal-42",
        subject="withdrawal",
        operation="signer.execute",
        request_digest=d(payload),
        identity_digest=d("operator"),
        epoch=7,
        nonce_digest=d("nonce:" + payload),
    )
    sathra = seal_sathra(
        AxisWitness(
            axis=axis,
            aevra_digest=aevra.digest,
            veyra_digest=veyra.digest,
            event_digest=request.digest,
            reality_digest=mir.fingerprint,
            epoch=request.epoch,
            witness_digest=d("witness:" + axis + ":" + request.digest),
        )
        for axis in ("khor", "sei", "rha", "vaal", "teyr", "esh")
    )
    sb = bind_sathra_to_request(mir, veyra, aevra, request, sathra)
    action = survival_action_commitment(
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        request=request,
    )
    chosen = SurvivalBranch(
        branch_digest=d("branch:chosen:" + payload),
        action_commitment_digest=action,
        khar_preserved=True,
        authority_escape=0,
        cross_domain_spread=0,
        evidence_loss=0,
        irreversible_loss=10,
        availability_loss=20,
        recoverability=900,
    )
    alternate = SurvivalBranch(
        branch_digest=d("branch:alternate:" + payload),
        action_commitment_digest=d("alternate-action:" + payload),
        khar_preserved=True,
        authority_escape=0,
        cross_domain_spread=0,
        evidence_loss=0,
        irreversible_loss=100,
        availability_loss=500,
        recoverability=500,
    )
    decision = select_survival_branch((alternate, chosen))
    assert decision.chosen_branch_digest == chosen.branch_digest
    return mir, veyra, aevra, matrix, hara, admission, request, sathra, sb, chosen, decision


def bind(values):
    mir, veyra, aevra, matrix, hara, admission, request, sathra, sb, chosen, decision = values
    return bind_survival_decision_to_event(
        decision=decision,
        branch=chosen,
        mir=mir,
        veyra=veyra,
        aevra=aevra,
        matrix=matrix,
        hara=hara,
        matrix_admission=admission,
        request=request,
        sathra=sathra,
        sathra_binding=sb,
    )


def test_survival_decision_binds_to_exact_galaxy_event():
    values = context()
    result = bind(values)
    assert result.request_digest == values[6].digest
    assert result.sathra_digest == values[7].digest
    assert result.matrix_digest == values[3].digest
    assert result.hara_digest == values[4].digest


def test_selected_action_cannot_move_to_different_request():
    first = context(payload="payload-a")
    second = context(payload="payload-b")
    _, _, _, _, _, _, request_b, sathra_b, sb_b, _, _ = second
    mir, veyra, aevra, matrix, hara, admission, _, _, _, chosen_a, decision_a = first

    with pytest.raises(SurvivalEventBindingError, match="not bound to this exact Galaxy event"):
        bind_survival_decision_to_event(
            decision=decision_a,
            branch=chosen_a,
            mir=mir,
            veyra=veyra,
            aevra=aevra,
            matrix=matrix,
            hara=hara,
            matrix_admission=admission,
            request=request_b,
            sathra=sathra_b,
            sathra_binding=sb_b,
        )


def test_selected_action_cannot_move_to_other_matrix_hara():
    first = context(matrix_tag="matrix-a")
    other = context(matrix_tag="matrix-b")
    mir, veyra, aevra, _, _, _, request, sathra, sb, chosen, decision = first
    _, _, _, matrix_b, hara_b, admission_b, _, _, _, _, _ = other

    with pytest.raises(SurvivalEventBindingError, match="not bound to this exact Galaxy event"):
        bind_survival_decision_to_event(
            decision=decision,
            branch=chosen,
            mir=mir,
            veyra=veyra,
            aevra=aevra,
            matrix=matrix_b,
            hara=hara_b,
            matrix_admission=admission_b,
            request=request,
            sathra=sathra,
            sathra_binding=sb,
        )


def test_non_chosen_branch_cannot_reuse_decision():
    values = context()
    mir, veyra, aevra, matrix, hara, admission, request, sathra, sb, chosen, decision = values
    foreign = replace(chosen, branch_digest=d("branch:foreign"))
    with pytest.raises(SurvivalEventBindingError, match="decision/branch mismatch"):
        bind_survival_decision_to_event(
            decision=decision,
            branch=foreign,
            mir=mir,
            veyra=veyra,
            aevra=aevra,
            matrix=matrix,
            hara=hara,
            matrix_admission=admission,
            request=request,
            sathra=sathra,
            sathra_binding=sb,
        )


def test_tampered_survival_event_binding_fails_closed():
    values = context()
    result = bind(values)
    forged = replace(result, request_digest=d("forged"))
    mir, veyra, aevra, matrix, hara, admission, request, sathra, sb, chosen, decision = values
    with pytest.raises(SurvivalEventBindingError):
        forged.assert_sealed(
            decision=decision,
            branch=chosen,
            mir=mir,
            veyra=veyra,
            aevra=aevra,
            matrix=matrix,
            hara=hara,
            matrix_admission=admission,
            request=request,
            sathra=sathra,
            sathra_binding=sb,
        )

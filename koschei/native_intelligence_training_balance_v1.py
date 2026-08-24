"""Balance the native training release with oracle-backed rejection learning.

The base corpus deliberately keeps one family per stage/split.  That clean split
geometry exposed an important training problem: its train families are positive
examples.  A model trained only on ACCEPTED targets cannot learn Koschei's
fail-closed boundary.

This module adds one independent train-only rejection family for every N0..N6
stage.  Families remain split-isolated.  The default balanced release therefore
contains 28 families x 96 variants = 2,688 examples.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile

from .adversarial_lab_v2 import REQUIRED_GATES, evaluate_release_v2
from .galaxy_identity_v1 import birth_aevra
from .khar_sathra_v1 import seal_sathra
from .library_adaptive_visibility_v0 import VisibilityPolicyV0, derive_adaptive_visibility_v0
from .native_intelligence_holdout_v1 import NativeIntelligenceHoldoutV1
from .native_intelligence_training_corpus_v1 import (
    DEFAULT_VARIANTS_PER_FAMILY,
    NativeTrainingCorpusError,
    NativeTrainingCorpusReleaseV1,
    SPLITS,
    STAGES,
    _axis_witnesses,
    _branches,
    _canonical_json,
    _example,
    _hash,
    _native_fixture,
    _populate_gate_root,
    _rejecting_example,
    _sha,
    _token,
    _veyra,
    _visibility,
    build_native_training_corpus_v1,
)
from .nur_nyr_projection_v1 import project_native_mir_nyr
from .parser import Parser
from .native_sigil_semantics_v1 import check_native_sigils
from .survival_branch_v1 import select_survival_branch
from .universe_state_machine_v1 import SigilState, initial_universe_state, transition_sigil

BALANCED_FAMILY_COUNT = 28


def _n0_train_reject(index: int):
    family = "native-train-duplicate-root-rejected"
    token = _token("N0", family, index)
    source = (
        f"ka treasuryx{token};\n"
        f"vor withdrawalx{token};\n"
        f"shi evidencex{token};\n"
        f"thal recoveryx{token};\n"
        f"nur visibilityx{token};\n"
        f"nur shadowx{token};\n"
    )
    def action():
        return check_native_sigils(Parser.from_source(source).parse())
    return _rejecting_example(
        stage="N0", family=family, split="train", index=index,
        task="Learn that a repeated native root is non-canonical even when its subject differs.",
        input_value=source, raw_input=True,
        oracle="parser->native-semantics",
        action=action,
    )


def _n1_train_reject(index: int):
    family = "aevra-train-unknown-subject-rejected"
    token = _token("N1", family, index)
    source, _, mir = _native_fixture(token)
    epoch = 80 + index
    veyra = _veyra(token, instance="a", epoch=epoch)
    unknown = f"unknownx{token}"
    return _rejecting_example(
        stage="N1", family=family, split="train", index=index,
        task="Learn that Aevra birth cannot invent a subject absent from sealed native MIR.",
        input_value={"source": source, "veyra": veyra.digest, "subject": unknown},
        oracle="galaxy_identity_v1.birth_aevra",
        action=lambda: birth_aevra(
            veyra, mir, sigil="ka", subject=unknown,
            birth_evidence_digest=_sha(f"birth|{token}"), birth_epoch=epoch,
        ),
    )


def _n2_train_reject(index: int):
    family = "sathra-train-reused-witness-rejected"
    token = _token("N2", family, index)
    rows = list(_axis_witnesses(token))
    rows[1] = replace(rows[1], witness_digest=rows[0].witness_digest)
    witnesses = tuple(rows)
    return _rejecting_example(
        stage="N2", family=family, split="train", index=index,
        task="Learn that one witness cannot satisfy two Khar axes inside a six-axis event.",
        input_value={"axes": [row.axis for row in witnesses], "reused_by": [rows[0].axis, rows[1].axis]},
        oracle="khar_sathra_v1.seal_sathra",
        action=lambda: seal_sathra(witnesses),
    )


def _n3_train_reject(index: int):
    family = "universe-train-ka-bypass-rejected"
    token = _token("N3", family, index)
    state = initial_universe_state(("ka", "vor", "shi", "thal", "nur"), epoch=90 + index)
    state = transition_sigil(state, "vor", SigilState.PREPARED, evidence_digest=_sha(f"{token}|vor|prepare"))
    state = transition_sigil(state, "vor", SigilState.SEALED, evidence_digest=_sha(f"{token}|vor|seal"))
    sealed = state
    return _rejecting_example(
        stage="N3", family=family, split="train", index=index,
        task="Learn that no non-ka sigil can activate before the genesis boundary is active.",
        input_value={"state": sealed.digest, "attempt": "vor sealed->active while ka inactive"},
        oracle="universe_state_machine_v1.transition_sigil",
        action=lambda: transition_sigil(
            sealed, "vor", SigilState.ACTIVE, evidence_digest=_sha(f"{token}|vor|activate")
        ),
    )


def _n4_train_reject(index: int):
    family = "nyr-train-insufficient-root-budget-rejected"
    token = _token("N4", family, index)
    source, _, mir = _native_fixture(token)
    veyra = _veyra(token, instance="a", epoch=1)
    decision, _ = _visibility(token, novelty=1, current_tick=100)
    policy = VisibilityPolicyV0(
        normal_root_budget=4,
        reduced_root_budget=4,
        minimal_root_budget=4,
        normal_relation_budget=4,
        reduced_relation_budget=3,
        minimal_relation_budget=1,
        epoch_span_ticks=10,
        rotate_compartments=True,
    )
    envelope = derive_adaptive_visibility_v0(
        decision=decision,
        policy=policy,
        current_tick=100,
        rotation_secret_commitment=__import__("hashlib").sha3_256(f"rotation|{token}".encode()).digest(),
    )
    return _rejecting_example(
        stage="N4", family=family, split="train", index=index,
        task="Learn that Nur refuses a Nyr surface when the live root budget cannot cover sealed MIR.",
        input_value={"source": source, "root_budget": envelope.root_budget, "required_roots": len(mir.bindings)},
        oracle="nur_nyr_projection_v1.project_native_mir_nyr",
        action=lambda: project_native_mir_nyr(
            mir,
            veyra,
            envelope,
            veil_key=__import__("hashlib").sha3_256(f"veil|{token}".encode()).digest(),
        ),
    )


def _n5_train_reject(index: int):
    family = "survival-train-duplicate-branch-rejected"
    token = _token("N5", family, index)
    branches = _branches(token)
    duplicated = (branches[0], branches[1], branches[0])
    return _rejecting_example(
        stage="N5", family=family, split="train", index=index,
        task="Learn that survival reasoning rejects duplicate branch identity before ranking futures.",
        input_value={"branches": [row.branch_digest for row in duplicated]},
        oracle="survival_branch_v1.select_survival_branch",
        action=lambda: select_survival_branch(duplicated),
    )


def _n6_train_reject(index: int, root: Path):
    family = "adversarial-train-runner-failure-rejected"
    token = _token("N6", family, index)
    target_gate = REQUIRED_GATES[index % len(REQUIRED_GATES)]

    def runner(test_file: str):
        gate = next(row for row in REQUIRED_GATES if row.test_file == test_file)
        if gate.gate_id == target_gate.gate_id:
            raise RuntimeError("oracle runner failure")
        return True, gate.min_tests, "oracle-count"

    report = evaluate_release_v2(
        candidate_id=f"train-reject-{token}",
        repo_root=root,
        runner=runner,
    )
    failed = next(row for row in report.results if row.gate_id == target_gate.gate_id)
    if report.commercial_ready or failed.passed:
        raise NativeTrainingCorpusError("N6 runner-failure oracle drift")
    return _example(
        stage="N6", family=family, split="train", index=index,
        task="Learn that an adversarial-suite runner failure blocks security specialization admission.",
        input_value={"candidate": f"train-reject-{token}", "runner_failure_gate": target_gate.gate_id},
        target={
            "decision": "REJECTED",
            "commercial_ready": False,
            "failed_gate": target_gate.gate_id,
            "detail": failed.detail,
            "report_sha256": report.report_sha256,
            "authority": False,
        },
        oracle="adversarial_lab_v2.evaluate_release_v2",
    )


def _decision(example) -> str:
    try:
        value = json.loads(example.target_text)["decision"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise NativeTrainingCorpusError("training target has no canonical decision") from error
    if value not in {"ACCEPTED", "REJECTED"}:
        raise NativeTrainingCorpusError("training target has unsupported canonical decision")
    return value


def require_native_training_balance_v1(corpus: NativeTrainingCorpusReleaseV1) -> None:
    """Require both positive and negative supervision for every N0..N6 train stage."""

    for stage in STAGES:
        decisions = {
            _decision(row)
            for row in corpus.examples
            if row.stage == stage and row.split == "train"
        }
        if decisions != {"ACCEPTED", "REJECTED"}:
            raise NativeTrainingCorpusError(
                f"native training stage {stage} must contain ACCEPTED and REJECTED train supervision"
            )


def build_balanced_native_training_corpus_v1(
    holdout: NativeIntelligenceHoldoutV1,
    *,
    variants_per_family: int = DEFAULT_VARIANTS_PER_FAMILY,
) -> NativeTrainingCorpusReleaseV1:
    """Build the train-balanced release used by real native-intelligence plans."""

    base = build_native_training_corpus_v1(
        holdout,
        variants_per_family=variants_per_family,
    )
    extras = []
    factories = (
        _n0_train_reject,
        _n1_train_reject,
        _n2_train_reject,
        _n3_train_reject,
        _n4_train_reject,
        _n5_train_reject,
    )
    for factory in factories:
        for index in range(variants_per_family):
            extras.append(factory(index))

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _populate_gate_root(root)
        for index in range(variants_per_family):
            extras.append(_n6_train_reject(index, root))

    frozen = base.examples + tuple(extras)
    stage_counts = tuple((stage, sum(row.stage == stage for row in frozen)) for stage in STAGES)
    split_counts = tuple((split, sum(row.split == split for row in frozen)) for split in SPLITS)
    family_splits = tuple(sorted({row.family: row.split for row in frozen}.items()))
    split_digests = tuple(
        (
            split,
            _hash(
                b"split",
                {"split": split, "examples": sorted(row.digest for row in frozen if row.split == split)},
            ),
        )
        for split in SPLITS
    )
    result = NativeTrainingCorpusReleaseV1(
        source_commit=base.source_commit,
        constitutional_holdout_digest=base.constitutional_holdout_digest,
        generator_version=base.generator_version,
        variants_per_family=variants_per_family,
        example_count=len(frozen),
        stage_counts=stage_counts,
        split_counts=split_counts,
        family_splits=family_splits,
        split_digests=split_digests,
        examples=frozen,
        authority=False,
        digest="",
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"release",
            {
                "source_commit": result.source_commit,
                "constitutional_holdout_digest": result.constitutional_holdout_digest,
                "generator_version": result.generator_version,
                "variants_per_family": result.variants_per_family,
                "example_count": result.example_count,
                "stage_counts": list(result.stage_counts),
                "split_counts": list(result.split_counts),
                "family_splits": list(result.family_splits),
                "split_digests": list(result.split_digests),
                "example_digests": [row.digest for row in result.examples],
                "authority": False,
            },
        ),
    )
    result.assert_sealed(holdout)
    require_native_training_balance_v1(result)
    if len(result.family_splits) != BALANCED_FAMILY_COUNT:
        raise NativeTrainingCorpusError("balanced native training family count drift")
    return result

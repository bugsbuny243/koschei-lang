"""Oracle-backed training corpus release for Koschei native intelligence v1.

The constitutional N0..N6 curriculum is a holdout, not training data.  This
module generates a separate deterministic supervised corpus by varying inputs to
living Koschei oracles.  Families are split as indivisible groups so near-copy
variants from one template cannot leak across train/validation/test.

The default release contains 2,016 examples: 96 variants for each of 21 oracle
families (one train, one validation and one test family for every N0..N6 stage).
The release is sealed to the source commit and constitutional holdout and carries
no execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Callable

from .adversarial_lab_v2 import MIN_TOTAL_ATTACK_TESTS, REQUIRED_GATES, evaluate_release_v2
from .bounded_autonomy_v1 import AutonomyBounds, propose_bounded_survival
from .galaxy_identity_v1 import GalaxyIdentityError, birth_aevra, birth_veyra
from .khar_sathra_v1 import AxisWitness, KHAR_AXES, KharSathraError, seal_sathra
from .library_adaptive_visibility_v0 import VisibilityPolicyV0, derive_adaptive_visibility_v0
from .library_adversary_learning_resistance_v0 import (
    DiscoveryClass,
    DiscoveryObservationV0,
    KnowledgeBudgetV0,
    evaluate_learning_resistance_v0,
)
from .native_intelligence_holdout_v1 import (
    NativeIntelligenceHoldoutV1,
    TrainingExampleFingerprintV1,
    fingerprint_training_example_v1,
    require_training_disjoint_from_holdout_v1,
)
from .native_sigil_mir_v1 import lower_native_sigils
from .native_sigil_semantics_v1 import check_native_sigils
from .nur_nyr_projection_v1 import NyrProjectionError, project_native_mir_nyr
from .parser import Parser
from .survival_branch_v1 import (
    SurvivalBranch,
    SurvivalBranchError,
    SurvivalObjective,
    select_survival_branch,
)
from .universe_rebirth_v1 import UniverseRebirthError, rebirth_contained_universe
from .universe_state_machine_v1 import SigilState, contain_universe, initial_universe_state, transition_sigil

GENERATOR_VERSION = "koschei.native-intelligence-training-corpus/v1"
DEFAULT_VARIANTS_PER_FAMILY = 96
SPLITS = ("train", "validation", "test")
STAGES = ("N0", "N1", "N2", "N3", "N4", "N5", "N6")
_CTX = b"koschei.native-intelligence-training-corpus/v1\x00"
_SIGILS = ("ka", "vor", "shi", "thal", "nur")


class NativeTrainingCorpusError(ValueError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(kind: bytes, payload: object) -> str:
    return hashlib.sha256(_CTX + kind + b"\x00" + _canonical_json(payload).encode("utf-8")).hexdigest()


def _sha(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


def _b32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode("utf-8")).digest()


def _token(stage: str, family: str, index: int) -> str:
    return _sha(f"{GENERATOR_VERSION}|{stage}|{family}|{index}")[:16]


def _source(token: str) -> str:
    return (
        f"ka treasuryx{token};\n"
        f"vor withdrawalx{token};\n"
        f"shi evidencex{token};\n"
        f"thal recoveryx{token};\n"
        f"nur visibilityx{token};\n"
    )


def _native_fixture(token: str):
    source = _source(token)
    program = Parser.from_source(source).parse()
    semantic = check_native_sigils(program)
    mir = lower_native_sigils(program, semantic)
    return source, semantic, mir


def _veyra(token: str, *, instance: str, epoch: int):
    return birth_veyra(
        profile_digest=_sha(f"profile|{token}"),
        genesis_digest=_sha(f"genesis|{token}"),
        constitution_digest=_sha(f"constitution|{token}"),
        instance_digest=_sha(f"instance|{token}|{instance}"),
        birth_epoch=epoch,
    )


@dataclass(frozen=True, slots=True)
class NativeTrainingExampleV1:
    example_id: str
    stage: str
    family: str
    split: str
    task: str
    input_text: str
    target_text: str
    oracle: str
    oracle_digest: str
    input_digest: str
    target_digest: str
    pair_digest: str
    digest: str
    authority: bool = False
    version: int = 1

    def fingerprint(self) -> TrainingExampleFingerprintV1:
        return fingerprint_training_example_v1(
            example_id=self.example_id,
            input_text=self.input_text,
            target_text=self.target_text,
        )

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise NativeTrainingCorpusError("unsupported native training example version")
        if self.stage not in STAGES:
            raise NativeTrainingCorpusError("unsupported native training stage")
        if self.split not in SPLITS:
            raise NativeTrainingCorpusError("unsupported native training split")
        if not all(isinstance(value, str) and value and "\x00" not in value for value in (
            self.example_id, self.family, self.task, self.input_text, self.target_text, self.oracle
        )):
            raise NativeTrainingCorpusError("native training example contains empty or invalid text")
        if self.authority is not False:
            raise NativeTrainingCorpusError("native training example cannot carry authority")
        fingerprint = self.fingerprint()
        if self.input_digest != fingerprint.input_digest:
            raise NativeTrainingCorpusError("native training input digest mismatch")
        if self.target_digest != fingerprint.target_digest:
            raise NativeTrainingCorpusError("native training target digest mismatch")
        if self.pair_digest != fingerprint.pair_digest:
            raise NativeTrainingCorpusError("native training pair digest mismatch")
        expected_oracle = _hash(
            b"oracle",
            {"oracle": self.oracle, "target_text": self.target_text},
        )
        if self.oracle_digest != expected_oracle:
            raise NativeTrainingCorpusError("native training oracle digest mismatch")
        expected = _hash(
            b"example",
            {
                "example_id": self.example_id,
                "stage": self.stage,
                "family": self.family,
                "split": self.split,
                "task": self.task,
                "oracle": self.oracle,
                "oracle_digest": self.oracle_digest,
                "input_digest": self.input_digest,
                "target_digest": self.target_digest,
                "pair_digest": self.pair_digest,
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingCorpusError("native training example seal mismatch")


@dataclass(frozen=True, slots=True)
class NativeTrainingCorpusReleaseV1:
    source_commit: str
    constitutional_holdout_digest: str
    generator_version: str
    variants_per_family: int
    example_count: int
    stage_counts: tuple[tuple[str, int], ...]
    split_counts: tuple[tuple[str, int], ...]
    family_splits: tuple[tuple[str, str], ...]
    split_digests: tuple[tuple[str, str], ...]
    examples: tuple[NativeTrainingExampleV1, ...]
    authority: bool
    digest: str
    version: int = 1

    def split_digest(self, split: str) -> str:
        try:
            return dict(self.split_digests)[split]
        except KeyError as error:
            raise NativeTrainingCorpusError(f"unknown native training split: {split}") from error

    def assert_sealed(self, holdout: NativeIntelligenceHoldoutV1) -> None:
        if self.version != 1:
            raise NativeTrainingCorpusError("unsupported native training corpus version")
        holdout.assert_sealed()
        if self.source_commit != holdout.source_commit:
            raise NativeTrainingCorpusError("training corpus belongs to a different source commit")
        if self.constitutional_holdout_digest != holdout.digest:
            raise NativeTrainingCorpusError("training corpus belongs to a different constitutional holdout")
        if self.generator_version != GENERATOR_VERSION:
            raise NativeTrainingCorpusError("unsupported native training corpus generator")
        if self.authority is not False:
            raise NativeTrainingCorpusError("native training corpus cannot carry authority")
        if not isinstance(self.variants_per_family, int) or self.variants_per_family < 1:
            raise NativeTrainingCorpusError("variants_per_family must be positive")
        if self.example_count != len(self.examples) or self.example_count < 1:
            raise NativeTrainingCorpusError("native training corpus example_count mismatch")

        ids: set[str] = set()
        inputs: set[str] = set()
        pairs: set[str] = set()
        observed_family_split: dict[str, str] = {}
        fingerprints: list[TrainingExampleFingerprintV1] = []
        for example in self.examples:
            example.assert_sealed()
            if example.example_id in ids:
                raise NativeTrainingCorpusError("duplicate native training example identity")
            if example.input_digest in inputs:
                raise NativeTrainingCorpusError("duplicate native training input")
            if example.pair_digest in pairs:
                raise NativeTrainingCorpusError("duplicate native training input/target pair")
            prior = observed_family_split.setdefault(example.family, example.split)
            if prior != example.split:
                raise NativeTrainingCorpusError("oracle family crosses train/validation/test boundary")
            ids.add(example.example_id)
            inputs.add(example.input_digest)
            pairs.add(example.pair_digest)
            fingerprints.append(example.fingerprint())

        require_training_disjoint_from_holdout_v1(holdout, fingerprints)

        expected_stage_counts = tuple(
            (stage, sum(example.stage == stage for example in self.examples))
            for stage in STAGES
        )
        if self.stage_counts != expected_stage_counts:
            raise NativeTrainingCorpusError("native training stage_counts mismatch")
        expected_split_counts = tuple(
            (split, sum(example.split == split for example in self.examples))
            for split in SPLITS
        )
        if self.split_counts != expected_split_counts:
            raise NativeTrainingCorpusError("native training split_counts mismatch")
        if any(count < 1 for _, count in self.split_counts):
            raise NativeTrainingCorpusError("every native training split must be non-empty")
        for stage in STAGES:
            for split in SPLITS:
                if not any(example.stage == stage and example.split == split for example in self.examples):
                    raise NativeTrainingCorpusError("every N0..N6 stage must exist in every split")

        expected_family_splits = tuple(sorted(observed_family_split.items()))
        if self.family_splits != expected_family_splits:
            raise NativeTrainingCorpusError("native training family_splits mismatch")
        expected_split_digests = tuple(
            (
                split,
                _hash(
                    b"split",
                    {
                        "split": split,
                        "examples": sorted(
                            example.digest for example in self.examples if example.split == split
                        ),
                    },
                ),
            )
            for split in SPLITS
        )
        if self.split_digests != expected_split_digests:
            raise NativeTrainingCorpusError("native training split digest mismatch")

        expected = _hash(
            b"release",
            {
                "source_commit": self.source_commit,
                "constitutional_holdout_digest": self.constitutional_holdout_digest,
                "generator_version": self.generator_version,
                "variants_per_family": self.variants_per_family,
                "example_count": self.example_count,
                "stage_counts": list(self.stage_counts),
                "split_counts": list(self.split_counts),
                "family_splits": list(self.family_splits),
                "split_digests": list(self.split_digests),
                "example_digests": [example.digest for example in self.examples],
                "authority": False,
            },
        )
        if self.digest != expected:
            raise NativeTrainingCorpusError("native training corpus release seal mismatch")


def _example(
    *,
    stage: str,
    family: str,
    split: str,
    index: int,
    task: str,
    input_value: object,
    target: dict[str, object],
    oracle: str,
    raw_input: bool = False,
) -> NativeTrainingExampleV1:
    input_text = str(input_value) if raw_input else _canonical_json(input_value)
    target_text = _canonical_json(target)
    example_id = f"{stage.lower()}-{family}-{index:05d}"
    fingerprint = fingerprint_training_example_v1(
        example_id=example_id,
        input_text=input_text,
        target_text=target_text,
    )
    oracle_digest = _hash(b"oracle", {"oracle": oracle, "target_text": target_text})
    result = NativeTrainingExampleV1(
        example_id=example_id,
        stage=stage,
        family=family,
        split=split,
        task=task,
        input_text=input_text,
        target_text=target_text,
        oracle=oracle,
        oracle_digest=oracle_digest,
        input_digest=fingerprint.input_digest,
        target_digest=fingerprint.target_digest,
        pair_digest=fingerprint.pair_digest,
        digest="",
        authority=False,
    )
    object.__setattr__(
        result,
        "digest",
        _hash(
            b"example",
            {
                "example_id": result.example_id,
                "stage": result.stage,
                "family": result.family,
                "split": result.split,
                "task": result.task,
                "oracle": result.oracle,
                "oracle_digest": result.oracle_digest,
                "input_digest": result.input_digest,
                "target_digest": result.target_digest,
                "pair_digest": result.pair_digest,
                "authority": False,
            },
        ),
    )
    result.assert_sealed()
    return result


def _rejecting_example(
    *, stage: str, family: str, split: str, index: int, task: str,
    input_value: object, oracle: str, action: Callable[[], object], raw_input: bool = False,
) -> NativeTrainingExampleV1:
    try:
        action()
    except ValueError as error:
        return _example(
            stage=stage,
            family=family,
            split=split,
            index=index,
            task=task,
            input_value=input_value,
            target={"decision": "REJECTED", "reason": str(error), "authority": False},
            oracle=oracle,
            raw_input=raw_input,
        )
    raise NativeTrainingCorpusError(f"oracle drift: rejecting family {family} was accepted")


# N0 ------------------------------------------------------------------------

def _n0_train(index: int) -> NativeTrainingExampleV1:
    family = "native-accepted-source"
    token = _token("N0", family, index)
    source, semantic, mir = _native_fixture(token)
    return _example(
        stage="N0", family=family, split="train", index=index,
        task="Compile a fresh five-root Koschei source into typed native semantics and sealed MIR.",
        input_value=source, raw_input=True,
        target={
            "decision": "ACCEPTED",
            "sigils": [row.sigil for row in semantic.declarations],
            "typed_semantic_digest": semantic.digest,
            "native_mir_fingerprint": mir.fingerprint,
            "authority": False,
        },
        oracle="parser->native-semantics->sealed-mir",
    )


def _n0_validation(index: int) -> NativeTrainingExampleV1:
    family = "native-duplicate-binding-rejected"
    token = _token("N0", family, index)
    source = (
        f"ka treasuryx{token};\nka treasuryx{token};\n"
        f"vor withdrawalx{token};\nshi evidencex{token};\nthal recoveryx{token};\nnur visibilityx{token};\n"
    )
    def action():
        program = Parser.from_source(source).parse()
        return check_native_sigils(program)
    return _rejecting_example(
        stage="N0", family=family, split="validation", index=index,
        task="Reject duplicate native sigil/subject birth instead of silently merging it.",
        input_value=source, raw_input=True, oracle="parser->native-semantics",
        action=action,
    )


def _n0_test(index: int) -> NativeTrainingExampleV1:
    family = "native-ka-order-rejected"
    token = _token("N0", family, index)
    source = (
        f"vor withdrawalx{token};\nka treasuryx{token};\n"
        f"shi evidencex{token};\nthal recoveryx{token};\nnur visibilityx{token};\n"
    )
    def action():
        program = Parser.from_source(source).parse()
        semantic = check_native_sigils(program)
        return lower_native_sigils(program, semantic)
    return _rejecting_example(
        stage="N0", family=family, split="test", index=index,
        task="Reject a native composition whose genesis root is not first.",
        input_value=source, raw_input=True, oracle="parser->native-semantics->sealed-mir",
        action=action,
    )


# N1 ------------------------------------------------------------------------

def _n1_train(index: int) -> NativeTrainingExampleV1:
    family = "distinct-customer-veyras"
    token = _token("N1", family, index)
    epoch = 10 + index
    a = _veyra(token, instance="a", epoch=epoch)
    b = _veyra(token, instance="b", epoch=epoch)
    return _example(
        stage="N1", family=family, split="train", index=index,
        task="Recognize distinct living customer Veyras under the same profile and constitution inputs.",
        input_value={"token": token, "birth_epoch": epoch, "instances": ["a", "b"]},
        target={
            "decision": "ACCEPTED",
            "same_profile": a.profile_digest == b.profile_digest,
            "same_constitution": a.constitution_digest == b.constitution_digest,
            "distinct_veyras": a.digest != b.digest,
            "veyra_a": a.digest,
            "veyra_b": b.digest,
            "authority": False,
        },
        oracle="galaxy_identity_v1.birth_veyra",
    )


def _n1_validation(index: int) -> NativeTrainingExampleV1:
    family = "aevra-exact-birth-binding"
    token = _token("N1", family, index)
    source, _, mir = _native_fixture(token)
    epoch = 20 + index
    veyra = _veyra(token, instance="a", epoch=epoch)
    subject = f"treasuryx{token}"
    aevra = birth_aevra(
        veyra, mir, sigil="ka", subject=subject,
        birth_evidence_digest=_sha(f"birth|{token}"), birth_epoch=epoch,
    )
    aevra.assert_sealed(veyra, mir)
    return _example(
        stage="N1", family=family, split="validation", index=index,
        task="Bind one Aevra birth to the exact Veyra, compiler product, subject and birth evidence.",
        input_value={"source": source, "birth_epoch": epoch, "subject": subject},
        target={
            "decision": "ACCEPTED",
            "aevra_digest": aevra.digest,
            "veyra_digest": aevra.veyra_digest,
            "native_mir_fingerprint": aevra.native_mir_fingerprint,
            "authority": False,
        },
        oracle="galaxy_identity_v1.birth_aevra",
    )


def _n1_test(index: int) -> NativeTrainingExampleV1:
    family = "aevra-cross-veyra-rejected"
    token = _token("N1", family, index)
    source, _, mir = _native_fixture(token)
    epoch = 30 + index
    a = _veyra(token, instance="a", epoch=epoch)
    b = _veyra(token, instance="b", epoch=epoch)
    subject = f"treasuryx{token}"
    aevra = birth_aevra(
        a, mir, sigil="ka", subject=subject,
        birth_evidence_digest=_sha(f"birth|{token}"), birth_epoch=epoch,
    )
    return _rejecting_example(
        stage="N1", family=family, split="test", index=index,
        task="Reject transfer of one living Aevra identity into another customer Veyra.",
        input_value={"source": source, "aevra": aevra.digest, "foreign_veyra": b.digest},
        oracle="galaxy_identity_v1.AevraIdentity.assert_sealed",
        action=lambda: aevra.assert_sealed(b, mir),
    )


# N2 ------------------------------------------------------------------------

def _axis_witnesses(token: str, *, count: int = 6, foreign_event_axis: str | None = None):
    common = {
        "aevra_digest": _sha(f"aevra|{token}"),
        "veyra_digest": _sha(f"veyra|{token}"),
        "event_digest": _sha(f"event|{token}"),
        "reality_digest": _sha(f"reality|{token}"),
        "epoch": 40 + int(token[:4], 16) % 1000,
    }
    rows = []
    for axis in KHAR_AXES[:count]:
        event = _sha(f"foreign-event|{token}") if axis == foreign_event_axis else common["event_digest"]
        rows.append(AxisWitness(
            axis=axis,
            aevra_digest=common["aevra_digest"],
            veyra_digest=common["veyra_digest"],
            event_digest=event,
            reality_digest=common["reality_digest"],
            epoch=common["epoch"],
            witness_digest=_sha(f"witness|{token}|{axis}"),
        ))
    return tuple(rows)


def _n2_train(index: int) -> NativeTrainingExampleV1:
    family = "six-axis-sathra"
    token = _token("N2", family, index)
    witnesses = _axis_witnesses(token)
    sathra = seal_sathra(witnesses)
    return _example(
        stage="N2", family=family, split="train", index=index,
        task="Seal exactly six same-event Khar witnesses into one Sathra.",
        input_value={"axes": [row.axis for row in witnesses], "event": witnesses[0].event_digest},
        target={
            "decision": "ACCEPTED",
            "axis_count": len(sathra.axis_witnesses),
            "sathra_digest": sathra.digest,
            "authority": False,
        },
        oracle="khar_sathra_v1.seal_sathra",
    )


def _n2_validation(index: int) -> NativeTrainingExampleV1:
    family = "five-of-six-is-zero"
    token = _token("N2", family, index)
    witnesses = _axis_witnesses(token, count=5)
    return _rejecting_example(
        stage="N2", family=family, split="validation", index=index,
        task="Reject five Khar axes as zero rather than partial critical authority.",
        input_value={"axes": [row.axis for row in witnesses], "result_if_partial": "ZERO"},
        oracle="khar_sathra_v1.seal_sathra",
        action=lambda: seal_sathra(witnesses),
    )


def _n2_test(index: int) -> NativeTrainingExampleV1:
    family = "cross-event-sathra-rejected"
    token = _token("N2", family, index)
    witnesses = _axis_witnesses(token, foreign_event_axis="esh")
    return _rejecting_example(
        stage="N2", family=family, split="test", index=index,
        task="Reject six witnesses collected from different events as one Sathra.",
        input_value={"axes": [row.axis for row in witnesses], "foreign_axis": "esh"},
        oracle="khar_sathra_v1.seal_sathra",
        action=lambda: seal_sathra(witnesses),
    )


# N3 ------------------------------------------------------------------------

def _active_state(token: str, epoch: int):
    state = initial_universe_state(_SIGILS, epoch=epoch)
    for sigil in _SIGILS:
        for target, phase in (
            (SigilState.PREPARED, "prepare"),
            (SigilState.SEALED, "seal"),
            (SigilState.ACTIVE, "activate"),
        ):
            state = transition_sigil(
                state, sigil, target, evidence_digest=_sha(f"{token}|{sigil}|{phase}")
            )
    return state


def _n3_train(index: int) -> NativeTrainingExampleV1:
    family = "terminal-containment"
    token = _token("N3", family, index)
    epoch = 50 + index
    active = _active_state(token, epoch)
    contained = contain_universe(active, evidence_digest=_sha(f"contain|{token}"))
    return _example(
        stage="N3", family=family, split="train", index=index,
        task="Move a living epoch into full containment without retaining an active sigil.",
        input_value={"active_state": active.digest, "epoch": epoch},
        target={
            "decision": "ACCEPTED",
            "contained_state": contained.digest,
            "all_contained": all(row.state is SigilState.CONTAINED for row in contained.sigils),
            "epoch": epoch,
            "authority": False,
        },
        oracle="universe_state_machine_v1.contain_universe",
    )


def _n3_validation(index: int) -> NativeTrainingExampleV1:
    family = "rebirth-new-inactive-epoch"
    token = _token("N3", family, index)
    epoch = 60 + index
    previous = contain_universe(_active_state(token, epoch), evidence_digest=_sha(f"contain|{token}"))
    fresh, receipt = rebirth_contained_universe(previous, cause_evidence_digest=_sha(f"rebirth|{token}"))
    return _example(
        stage="N3", family=family, split="validation", index=index,
        task="Rebirth only from full containment into a new epoch with zero inherited active state.",
        input_value={"previous_state": previous.digest, "previous_epoch": epoch},
        target={
            "decision": "ACCEPTED",
            "next_epoch": receipt.next_epoch,
            "fresh_state": fresh.digest,
            "all_inactive": all(row.state is SigilState.INACTIVE for row in fresh.sigils),
            "receipt_digest": receipt.digest,
            "authority": False,
        },
        oracle="universe_rebirth_v1.rebirth_contained_universe",
    )


def _n3_test(index: int) -> NativeTrainingExampleV1:
    family = "rebirth-without-containment-rejected"
    token = _token("N3", family, index)
    epoch = 70 + index
    active = _active_state(token, epoch)
    return _rejecting_example(
        stage="N3", family=family, split="test", index=index,
        task="Reject rebirth from a still-living epoch; recovery cannot become resurrection.",
        input_value={"active_state": active.digest, "epoch": epoch},
        oracle="universe_rebirth_v1.rebirth_contained_universe",
        action=lambda: rebirth_contained_universe(active, cause_evidence_digest=_sha(f"rebirth|{token}")),
    )


# N4 ------------------------------------------------------------------------

def _visibility(token: str, *, novelty: int, current_tick: int = 100):
    observation = DiscoveryObservationV0(
        observer_id=f"observer-{token}",
        session_digest=_b32(f"session|{token}"),
        tick=current_tick,
        discovery_class=DiscoveryClass.ROOT_ENUMERATION,
        target_digest=_b32(f"target|{token}"),
        novelty_units=novelty,
        boundary_attempt=False,
        evidence_digest=_b32(f"observation|{token}"),
    )
    budget = KnowledgeBudgetV0(
        max_total_units=10,
        max_distinct_targets=10,
        max_boundary_attempts=3,
        max_classes=7,
        window_ticks=10,
    )
    decision = evaluate_learning_resistance_v0(
        observations=(observation,), budget=budget, current_tick=current_tick
    )
    policy = VisibilityPolicyV0(
        normal_root_budget=5,
        reduced_root_budget=5,
        minimal_root_budget=5,
        normal_relation_budget=5,
        reduced_relation_budget=3,
        minimal_relation_budget=1,
        epoch_span_ticks=10,
        rotate_compartments=True,
    )
    return decision, policy


def _n4_train(index: int) -> NativeTrainingExampleV1:
    family = "nyr-rotates-across-epochs"
    token = _token("N4", family, index)
    source, _, mir = _native_fixture(token)
    veyra = _veyra(token, instance="a", epoch=1)
    decision, policy = _visibility(token, novelty=1, current_tick=100)
    first = derive_adaptive_visibility_v0(
        decision=decision, policy=policy, current_tick=100,
        rotation_secret_commitment=_b32(f"rotation|{token}"),
    )
    second = derive_adaptive_visibility_v0(
        decision=decision, policy=policy, current_tick=110,
        rotation_secret_commitment=_b32(f"rotation|{token}"),
    )
    a = project_native_mir_nyr(mir, veyra, first, veil_key=_b32(f"veil|{token}"))
    b = project_native_mir_nyr(mir, veyra, second, veil_key=_b32(f"veil|{token}"))
    return _example(
        stage="N4", family=family, split="train", index=index,
        task="Recognize that observer-facing Nyr aliases rotate while canonical MIR remains unchanged.",
        input_value={"source": source, "epoch_a": first.visibility_epoch, "epoch_b": second.visibility_epoch},
        target={
            "decision": "ACCEPTED",
            "aliases_rotate": tuple(row.alias for row in a.bindings) != tuple(row.alias for row in b.bindings),
            "surface_a": a.surface_digest,
            "surface_b": b.surface_digest,
            "canonical_mir": mir.fingerprint,
            "authority": False,
        },
        oracle="learning-resistance->adaptive-visibility->nur-nyr-projection",
    )


def _n4_validation(index: int) -> NativeTrainingExampleV1:
    family = "nyr-cross-veyra-nontransfer"
    token = _token("N4", family, index)
    source, _, mir = _native_fixture(token)
    a = _veyra(token, instance="a", epoch=1)
    b = _veyra(token, instance="b", epoch=1)
    decision, policy = _visibility(token, novelty=1, current_tick=100)
    envelope = derive_adaptive_visibility_v0(
        decision=decision, policy=policy, current_tick=100,
        rotation_secret_commitment=_b32(f"rotation|{token}"),
    )
    surface_a = project_native_mir_nyr(mir, a, envelope, veil_key=_b32(f"veil|{token}"))
    surface_b = project_native_mir_nyr(mir, b, envelope, veil_key=_b32(f"veil|{token}"))
    return _example(
        stage="N4", family=family, split="validation", index=index,
        task="Reject cross-customer projection transfer by deriving different Nyr surfaces per Veyra.",
        input_value={"source": source, "veyra_a": a.digest, "veyra_b": b.digest},
        target={
            "decision": "ACCEPTED",
            "surfaces_distinct": surface_a.surface_digest != surface_b.surface_digest,
            "surface_a": surface_a.surface_digest,
            "surface_b": surface_b.surface_digest,
            "authority": False,
        },
        oracle="nur_nyr_projection_v1.project_native_mir_nyr",
    )


def _n4_test(index: int) -> NativeTrainingExampleV1:
    family = "contained-visibility-exposes-zero-nyr"
    token = _token("N4", family, index)
    source, _, mir = _native_fixture(token)
    veyra = _veyra(token, instance="a", epoch=1)
    decision, policy = _visibility(token, novelty=11, current_tick=100)
    envelope = derive_adaptive_visibility_v0(
        decision=decision, policy=policy, current_tick=100,
        rotation_secret_commitment=_b32(f"rotation|{token}"),
    )
    return _rejecting_example(
        stage="N4", family=family, split="test", index=index,
        task="Reject Nyr projection when learning pressure has contained visibility to zero.",
        input_value={"source": source, "posture": decision.posture.value, "allowed": envelope.allowed},
        oracle="nur_nyr_projection_v1.project_native_mir_nyr",
        action=lambda: project_native_mir_nyr(mir, veyra, envelope, veil_key=_b32(f"veil|{token}")),
    )


# N5 ------------------------------------------------------------------------

def _branches(token: str) -> tuple[SurvivalBranch, ...]:
    offset = int(token[:2], 16) % 5
    return (
        SurvivalBranch(_sha(f"branch-a|{token}"), _sha(f"action-a|{token}"), True, 0, 0, 5 + offset, 8 + offset, 15, 930),
        SurvivalBranch(_sha(f"branch-b|{token}"), _sha(f"action-b|{token}"), True, 0, 0, 20 + offset, 30 + offset, 30, 800),
        SurvivalBranch(_sha(f"branch-c|{token}"), _sha(f"action-c|{token}"), False, 0, 0, 0, 0, 0, 1000),
    )


def _n5_train(index: int) -> NativeTrainingExampleV1:
    family = "least-loss-khar-survival"
    token = _token("N5", family, index)
    branches = _branches(token)
    objective = SurvivalObjective()
    decision = select_survival_branch(branches, objective=objective)
    return _example(
        stage="N5", family=family, split="train", index=index,
        task="Select the least-loss future only among branches that preserve Khar hard ceilings.",
        input_value={"branches": [row.branch_digest for row in branches], "objective": objective.digest},
        target={
            "decision": "ACCEPTED",
            "chosen_branch": decision.chosen_branch_digest,
            "rejected_branches": list(decision.rejected_branch_digests),
            "decision_digest": decision.digest,
            "authority": False,
        },
        oracle="survival_branch_v1.select_survival_branch",
    )


def _n5_validation(index: int) -> NativeTrainingExampleV1:
    family = "no-khar-future-rejected"
    token = _token("N5", family, index)
    branches = (
        SurvivalBranch(_sha(f"dead-a|{token}"), _sha(f"dead-action-a|{token}"), False, 0, 0, 0, 0, 0, 1000),
        SurvivalBranch(_sha(f"dead-b|{token}"), _sha(f"dead-action-b|{token}"), True, 1, 0, 0, 0, 0, 1000),
    )
    return _rejecting_example(
        stage="N5", family=family, split="validation", index=index,
        task="Reject survival selection when no candidate preserves Khar within hard ceilings.",
        input_value={"branches": [row.branch_digest for row in branches]},
        oracle="survival_branch_v1.select_survival_branch",
        action=lambda: select_survival_branch(branches),
    )


def _n5_test(index: int) -> NativeTrainingExampleV1:
    family = "bounded-autonomy-is-proposal-only"
    token = _token("N5", family, index)
    branches = _branches(token)
    objective = SurvivalObjective()
    bounds = AutonomyBounds(max_candidates=8, max_proposal_round=100000)
    proposal = propose_bounded_survival(
        branches,
        objective=objective,
        bounds=bounds,
        proposal_round=index,
        evidence_digest=_sha(f"autonomy-evidence|{token}"),
    )
    return _example(
        stage="N5", family=family, split="test", index=index,
        task="Treat autonomous survival output as an authority-free proposal, never an execution decision.",
        input_value={"branches": [row.branch_digest for row in branches], "proposal_round": index},
        target={
            "decision": "ACCEPTED",
            "chosen_branch": proposal.decision.chosen_branch_digest,
            "proposal_digest": proposal.digest,
            "authority": proposal.authority,
        },
        oracle="bounded_autonomy_v1.propose_bounded_survival",
    )


# N6 ------------------------------------------------------------------------

def _populate_gate_root(root: Path, *, missing_gate: str | None = None) -> None:
    for gate in REQUIRED_GATES:
        if gate.gate_id == missing_gate:
            continue
        path = root / gate.test_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# oracle suite marker\n", encoding="utf-8")


def _gate_runner(*, shrink_gate: str | None = None):
    def runner(test_file: str):
        gate = next(row for row in REQUIRED_GATES if row.test_file == test_file)
        count = gate.min_tests - 1 if gate.gate_id == shrink_gate else gate.min_tests
        return True, count, "oracle-count"
    return runner


def _n6_train(index: int, full_root: Path) -> NativeTrainingExampleV1:
    family = "adversarial-release-all-gates"
    token = _token("N6", family, index)
    report = evaluate_release_v2(
        candidate_id=f"train-{token}", repo_root=full_root, runner=_gate_runner()
    )
    if not report.commercial_ready or report.total_tests_run < MIN_TOTAL_ATTACK_TESTS:
        raise NativeTrainingCorpusError("N6 adversarial ready oracle drift")
    return _example(
        stage="N6", family=family, split="train", index=index,
        task="Admit security specialization only when every required adversarial gate and the global floor pass.",
        input_value={"candidate": f"train-{token}", "gate_count": len(REQUIRED_GATES)},
        target={
            "decision": "ACCEPTED",
            "commercial_ready": report.commercial_ready,
            "total_tests_run": report.total_tests_run,
            "minimum_total_tests": report.minimum_total_tests,
            "report_sha256": report.report_sha256,
            "authority": False,
        },
        oracle="adversarial_lab_v2.evaluate_release_v2",
    )


def _n6_validation(index: int, missing_root: Path) -> NativeTrainingExampleV1:
    family = "adversarial-release-missing-suite"
    token = _token("N6", family, index)
    report = evaluate_release_v2(
        candidate_id=f"validation-{token}", repo_root=missing_root, runner=_gate_runner()
    )
    failed = next(row for row in report.results if row.gate_id == "distribution-shift-observer")
    if report.commercial_ready or failed.passed:
        raise NativeTrainingCorpusError("N6 missing-suite oracle drift")
    return _example(
        stage="N6", family=family, split="validation", index=index,
        task="Reject security specialization when one required adversarial suite is absent.",
        input_value={"candidate": f"validation-{token}", "missing_gate": failed.gate_id},
        target={
            "decision": "REJECTED",
            "commercial_ready": report.commercial_ready,
            "failed_gate": failed.gate_id,
            "detail": failed.detail,
            "report_sha256": report.report_sha256,
            "authority": False,
        },
        oracle="adversarial_lab_v2.evaluate_release_v2",
    )


def _n6_test(index: int, full_root: Path) -> NativeTrainingExampleV1:
    family = "adversarial-release-shrink-rejected"
    token = _token("N6", family, index)
    report = evaluate_release_v2(
        candidate_id=f"test-{token}", repo_root=full_root,
        runner=_gate_runner(shrink_gate="distribution-shift-observer"),
    )
    failed = next(row for row in report.results if row.gate_id == "distribution-shift-observer")
    if report.commercial_ready or failed.passed:
        raise NativeTrainingCorpusError("N6 shrink oracle drift")
    return _example(
        stage="N6", family=family, split="test", index=index,
        task="Reject an adversarial release whose suite still passes but collected test count shrank below its ratchet.",
        input_value={"candidate": f"test-{token}", "shrunk_gate": failed.gate_id},
        target={
            "decision": "REJECTED",
            "commercial_ready": report.commercial_ready,
            "failed_gate": failed.gate_id,
            "tests_run": failed.tests_run,
            "minimum_tests": failed.min_tests,
            "detail": failed.detail,
            "report_sha256": report.report_sha256,
            "authority": False,
        },
        oracle="adversarial_lab_v2.evaluate_release_v2",
    )


def build_native_training_corpus_v1(
    holdout: NativeIntelligenceHoldoutV1,
    *,
    variants_per_family: int = DEFAULT_VARIANTS_PER_FAMILY,
) -> NativeTrainingCorpusReleaseV1:
    """Build one deterministic N0..N6 training release disjoint from the holdout."""

    holdout.assert_sealed()
    if not isinstance(variants_per_family, int) or not 1 <= variants_per_family <= 10_000:
        raise NativeTrainingCorpusError("variants_per_family must be in 1..10000")

    examples: list[NativeTrainingExampleV1] = []
    ordinary_families: tuple[Callable[[int], NativeTrainingExampleV1], ...] = (
        _n0_train, _n0_validation, _n0_test,
        _n1_train, _n1_validation, _n1_test,
        _n2_train, _n2_validation, _n2_test,
        _n3_train, _n3_validation, _n3_test,
        _n4_train, _n4_validation, _n4_test,
        _n5_train, _n5_validation, _n5_test,
    )
    for factory in ordinary_families:
        for index in range(variants_per_family):
            examples.append(factory(index))

    with tempfile.TemporaryDirectory() as full_directory, tempfile.TemporaryDirectory() as missing_directory:
        full_root = Path(full_directory)
        missing_root = Path(missing_directory)
        _populate_gate_root(full_root)
        _populate_gate_root(missing_root, missing_gate="distribution-shift-observer")
        for index in range(variants_per_family):
            examples.append(_n6_train(index, full_root))
            examples.append(_n6_validation(index, missing_root))
            examples.append(_n6_test(index, full_root))

    frozen = tuple(examples)
    stage_counts = tuple((stage, sum(row.stage == stage for row in frozen)) for stage in STAGES)
    split_counts = tuple((split, sum(row.split == split for row in frozen)) for split in SPLITS)
    family_splits = tuple(sorted({row.family: row.split for row in frozen}.items()))
    split_digests = tuple(
        (
            split,
            _hash(
                b"split",
                {
                    "split": split,
                    "examples": sorted(row.digest for row in frozen if row.split == split),
                },
            ),
        )
        for split in SPLITS
    )
    result = NativeTrainingCorpusReleaseV1(
        source_commit=holdout.source_commit,
        constitutional_holdout_digest=holdout.digest,
        generator_version=GENERATOR_VERSION,
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
    return result

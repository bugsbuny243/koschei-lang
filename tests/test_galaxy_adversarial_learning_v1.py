import hashlib

from koschei.galaxy_identity_v1 import birth_veyra
from koschei.library_adaptive_visibility_v0 import (
    VisibilityPolicyV0,
    derive_adaptive_visibility_v0,
)
from koschei.library_adversary_learning_resistance_v0 import (
    LearningResistanceDecisionV0,
    VisibilityPosture,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.nur_nyr_projection_v1 import NyrSurface, project_native_mir_nyr
from koschei.parser import parse


def b32(tag: str) -> bytes:
    return hashlib.sha3_256(tag.encode()).digest()


def h64(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


MIR = lower_native_sigils(
    parse("ka treasury; vor withdrawal; shi evidence; thal recovery; nur visibility;")
)
POLICY = VisibilityPolicyV0(32, 8, 2, 64, 12, 2, 10, True, False)
VEIL = b"galaxy-adversarial-corpus-veil!!"  # >=32 bytes
SUBJECTS = ("treasury", "withdrawal", "evidence", "recovery", "visibility")
SIGILS = ("ka", "vor", "shi", "thal", "nur")


def veyra(customer: str):
    return birth_veyra(
        profile_digest=h64("banking-profile"),
        genesis_digest=h64("genesis"),
        constitution_digest=h64("khar-v1"),
        instance_digest=h64(customer),
        birth_epoch=1,
    )


def envelope(customer: str, session: int, visibility_epoch: int):
    tick = visibility_epoch * POLICY.epoch_span_ticks
    decision = LearningResistanceDecisionV0(
        f"observer-{customer}",
        b32(f"session:{customer}:{session}"),
        max(0, tick - 2),
        tick,
        1,
        1,
        0,
        1,
        100,
        VisibilityPosture.NORMAL,
        3,
        b32(f"decision:{customer}:{session}:{visibility_epoch}"),
        True,
        False,
    )
    return derive_adaptive_visibility_v0(
        decision=decision,
        policy=POLICY,
        current_tick=tick,
        rotation_secret_commitment=b32("rotation-secret:" + customer),
    )


def surface(customer: str, session: int, epoch: int):
    return project_native_mir_nyr(
        MIR,
        veyra(customer),
        envelope(customer, session, epoch),
        veil_key=VEIL,
    )


def test_long_running_observation_corpus_has_no_stable_subject_alias():
    observed = {}
    for epoch in range(1, 13):
        item = surface("bank-a", 1, epoch)
        for binding in item.bindings:
            observed.setdefault(binding.sigil, set()).add(binding.alias)

    # The canonical sigil roots are deliberately stable language semantics, but
    # every subject projection rotates with the visibility epoch.
    assert set(observed) == set(SIGILS)
    assert all(len(aliases) == 12 for aliases in observed.values())


def test_cross_customer_observations_do_not_transfer_alias_map():
    bank_a = surface("bank-a", 1, 7)
    bank_b = surface("bank-b", 1, 7)
    aliases_a = {item.alias for item in bank_a.bindings}
    aliases_b = {item.alias for item in bank_b.bindings}
    assert aliases_a.isdisjoint(aliases_b)
    assert tuple(item.sigil for item in bank_a.bindings) == tuple(item.sigil for item in bank_b.bindings)


def test_observer_session_retraining_corpus_does_not_preserve_aliases():
    surfaces = [surface("bank-a", session, 7) for session in range(1, 9)]
    for index, left in enumerate(surfaces):
        for right in surfaces[index + 1 :]:
            assert {item.alias for item in left.bindings}.isdisjoint(
                {item.alias for item in right.bindings}
            )


def test_large_projection_corpus_never_contains_canonical_subject_or_veyra_identity():
    customers = ("bank-a", "bank-b", "exchange-a")
    for customer in customers:
        identity = veyra(customer)
        for session in range(1, 5):
            for epoch in range(1, 7):
                item = surface(customer, session, epoch)
                rendered = item.render()
                assert identity.digest not in rendered
                assert MIR.fingerprint not in rendered
                assert MIR.universe_plan_digest not in rendered
                assert all(subject not in rendered for subject in SUBJECTS)


def test_nyr_public_shape_contains_no_canonical_galaxy_locator_field():
    fields = set(NyrSurface.__dataclass_fields__)
    forbidden = {
        "veyra_digest",
        "aevra_digest",
        "native_mir_fingerprint",
        "universe_plan_digest",
        "activation_plan_digest",
        "canonical_subject",
        "failure_root_digest",
    }
    assert fields.isdisjoint(forbidden)


def test_same_canonical_mir_survives_while_all_observer_aliases_rotate():
    first = surface("bank-a", 1, 1)
    last = surface("bank-a", 8, 12)
    assert tuple(item.sigil for item in first.bindings) == SIGILS
    assert tuple(item.sigil for item in last.bindings) == SIGILS
    assert first.render() != last.render()
    # Projection changes do not mutate the compiler-produced canonical reality.
    MIR.assert_sealed()

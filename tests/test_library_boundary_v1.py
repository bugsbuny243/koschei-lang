from koschei.library_boundary_v1 import (
    admit_library_observation_v1,
    make_resource_budget_v1,
    observe_library_effect_v1,
    seal_library_authority_envelope_v1,
)

ARTIFACT = b"a" * 32
REV = b"r" * 32
TARGET = b"t" * 32


def envelope(effects=frozenset()):
    return seal_library_authority_envelope_v1(
        artifact_digest=ARTIFACT,
        revision_digest=REV,
        effects=effects,
        budget=make_resource_budget_v1(
            cpu_units=100, memory_bytes=1024, input_bytes=2048, nesting=8,
        ),
        epoch=7,
    )


def test_dependency_has_zero_ambient_authority_by_default():
    env = envelope()
    for effect in ("network", "process", "secret", "sign", "persist", "device", "ffi"):
        result = admit_library_observation_v1(
            env,
            observe_library_effect_v1(
                artifact_digest=ARTIFACT, effect=effect, target_digest=TARGET,
            ),
        )
        assert result.admitted is False
        assert result.precursor is not None
        assert result.precursor.reason == "authority-expansion"


def test_declared_compute_is_admitted_within_budget():
    env = envelope(frozenset({"compute"}))
    result = admit_library_observation_v1(
        env,
        observe_library_effect_v1(
            artifact_digest=ARTIFACT, effect="compute", cpu_units=80, memory_bytes=512,
        ),
    )
    assert result.admitted is True
    assert result.precursor is None


def test_resource_exhaustion_is_security_precursor_not_performance_warning():
    env = envelope(frozenset({"decode"}))
    cases = (
        (dict(cpu_units=101), "cpu-budget-exceeded"),
        (dict(memory_bytes=1025), "memory-budget-exceeded"),
        (dict(input_bytes=2049), "input-budget-exceeded"),
        (dict(nesting=9), "nesting-budget-exceeded"),
    )
    for kwargs, reason in cases:
        result = admit_library_observation_v1(
            env,
            observe_library_effect_v1(artifact_digest=ARTIFACT, effect="decode", **kwargs),
        )
        assert result.admitted is False
        assert result.precursor is not None
        assert result.precursor.reason == reason


def test_authority_bearing_effect_requires_exact_target_commitment():
    env = envelope(frozenset({"network"}))
    denied = admit_library_observation_v1(
        env, observe_library_effect_v1(artifact_digest=ARTIFACT, effect="network")
    )
    allowed = admit_library_observation_v1(
        env,
        observe_library_effect_v1(
            artifact_digest=ARTIFACT, effect="network", target_digest=TARGET
        ),
    )
    assert denied.admitted is False
    assert denied.precursor is not None
    assert denied.precursor.reason == "missing-exact-target"
    assert allowed.admitted is True


def test_artifact_substitution_is_detected_before_effect_admission():
    env = envelope(frozenset({"compute"}))
    result = admit_library_observation_v1(
        env,
        observe_library_effect_v1(artifact_digest=b"x" * 32, effect="compute"),
    )
    assert result.admitted is False
    assert result.precursor is not None
    assert result.precursor.reason == "artifact-substitution"


def test_observation_is_deterministically_committed_for_sentinel_evidence():
    env = envelope(frozenset({"compute"}))
    a = admit_library_observation_v1(
        env, observe_library_effect_v1(artifact_digest=ARTIFACT, effect="compute", cpu_units=7)
    )
    b = admit_library_observation_v1(
        env, observe_library_effect_v1(artifact_digest=ARTIFACT, effect="compute", cpu_units=7)
    )
    assert a.observation_digest == b.observation_digest

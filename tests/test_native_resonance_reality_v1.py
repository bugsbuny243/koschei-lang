import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_pulse_reality_v1 import PulseTraceV1
from koschei.native_resonance_reality_v1 import (
    NativeResonanceRealityError,
    derive_native_resonance_reality_v1,
)


def whole(value: int) -> base.NativeValue:
    return base.NativeValue(base.WHOLE, value)


def truth(value: bool) -> base.NativeValue:
    return base.NativeValue(base.TRUTH, value)


def pulse(values):
    return PulseTraceV1(tuple(values), b"p" * 32)


def test_change_resonance_emits_only_temporal_edges():
    result = derive_native_resonance_reality_v1(
        pulse((whole(1), whole(1), whole(2), whole(2), whole(3))),
        mode="change",
    )
    assert [fact.ordinal for fact in result.facts] == [2, 4]
    assert all(len(fact.fact_digest) == 32 for fact in result.facts)
    assert len(result.trace_digest) == 32


def test_rise_and_fall_are_truth_specific():
    values = pulse((truth(False), truth(True), truth(True), truth(False), truth(True)))
    rises = derive_native_resonance_reality_v1(values, mode="rise")
    falls = derive_native_resonance_reality_v1(values, mode="fall")
    assert [f.ordinal for f in rises.facts] == [1, 4]
    assert [f.ordinal for f in falls.facts] == [3]


def test_resonance_is_deterministic_and_does_not_embed_plain_values_in_repr():
    a = derive_native_resonance_reality_v1(pulse((whole(7), whole(9))), mode="change")
    b = derive_native_resonance_reality_v1(pulse((whole(7), whole(9))), mode="change")
    assert a.trace_digest == b.trace_digest
    assert a.facts[0].fact_digest == b.facts[0].fact_digest
    assert "<committed>" in repr(a.facts[0])


def test_truth_edges_reject_non_truth_and_cross_domain_splice():
    with pytest.raises(NativeResonanceRealityError):
        derive_native_resonance_reality_v1(pulse((whole(0), whole(1))), mode="rise")
    with pytest.raises(NativeResonanceRealityError):
        derive_native_resonance_reality_v1(pulse((whole(1), truth(True))), mode="change")


def test_resonance_requires_real_temporal_context_and_known_mode():
    with pytest.raises(NativeResonanceRealityError):
        derive_native_resonance_reality_v1(pulse((whole(1),)), mode="change")
    with pytest.raises(NativeResonanceRealityError):
        derive_native_resonance_reality_v1(pulse((whole(1), whole(2))), mode="callback")  # type: ignore[arg-type]


def test_resonance_produces_facts_not_callbacks_or_execution_authority():
    result = derive_native_resonance_reality_v1(
        pulse((truth(False), truth(True))), mode="rise"
    )
    fact = result.facts[0]
    assert not hasattr(fact, "execute")
    assert not hasattr(fact, "callback")
    assert not hasattr(fact, "authority")

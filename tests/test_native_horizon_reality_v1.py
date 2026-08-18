import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_horizon_reality_v1 import (
    NativeHorizonRealityError,
    derive_native_horizon_reality_v1,
)
from koschei.native_pulse_reality_v1 import PulseTraceV1


def whole(n):
    return base.NativeValue(base.WHOLE, n)


def truth(v):
    return base.NativeValue(base.TRUTH, v)


def trace(values, digest=b"p" * 32):
    return PulseTraceV1(tuple(values), digest)


def test_remember_horizon_is_immutable_committed_memory_chain():
    result = derive_native_horizon_reality_v1(trace([whole(4), whole(7), whole(9)]), mode="remember")
    assert [s.value.value for s in result.states] == [4, 7, 9]
    assert result.states[1].previous_digest == result.states[0].state_digest
    assert result.states[2].previous_digest == result.states[1].state_digest
    assert len(result.trace_digest) == 32


def test_tally_accumulates_without_assignment_or_mutable_global_state():
    result = derive_native_horizon_reality_v1(trace([whole(4), whole(7), whole(-2)]), mode="tally")
    assert [s.value.value for s in result.states] == [4, 11, 9]


def test_affirm_is_monotonic_truth_memory():
    result = derive_native_horizon_reality_v1(trace([truth(False), truth(True), truth(False)]), mode="affirm")
    assert [s.value.value for s in result.states] == [False, True, True]


def test_horizon_identity_binds_pulse_trace_and_temporal_order():
    a = derive_native_horizon_reality_v1(trace([whole(1), whole(2)], b"a" * 32), mode="tally")
    b = derive_native_horizon_reality_v1(trace([whole(1), whole(2)], b"a" * 32), mode="tally")
    c = derive_native_horizon_reality_v1(trace([whole(2), whole(1)], b"a" * 32), mode="tally")
    d = derive_native_horizon_reality_v1(trace([whole(1), whole(2)], b"b" * 32), mode="tally")
    assert a.trace_digest == b.trace_digest
    assert a.trace_digest != c.trace_digest
    assert a.trace_digest != d.trace_digest


def test_horizon_rejects_cross_domain_mode_abuse():
    with pytest.raises(NativeHorizonRealityError):
        derive_native_horizon_reality_v1(trace([truth(True)]), mode="tally")
    with pytest.raises(NativeHorizonRealityError):
        derive_native_horizon_reality_v1(trace([whole(1)]), mode="affirm")


def test_tally_overflow_fails_closed():
    with pytest.raises(NativeHorizonRealityError):
        derive_native_horizon_reality_v1(trace([whole((1 << 63) - 1), whole(1)]), mode="tally")


def test_unknown_mode_and_empty_trace_fail_closed():
    with pytest.raises(NativeHorizonRealityError):
        derive_native_horizon_reality_v1(trace([whole(1)]), mode="counter")
    with pytest.raises(NativeHorizonRealityError):
        derive_native_horizon_reality_v1(trace([]), mode="remember")

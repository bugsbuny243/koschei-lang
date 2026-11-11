import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_horizon_conduit_v1 import (
    NativeHorizonConduitError,
    bind_native_horizon_conduit_v1,
    project_native_horizon_conduit_v1,
)
from koschei.native_horizon_reality_v1 import derive_native_horizon_reality_v1
from koschei.native_pulse_reality_v1 import PulseTraceV1
from koschei.native_signal_reality_v1 import evaluate_native_signal_reality_v1


def whole(n):
    return base.NativeValue(base.WHOLE, n)


def truth(v):
    return base.NativeValue(base.TRUTH, v)


def trace(values, digest=b"h" * 32):
    return PulseTraceV1(tuple(values), digest)


def test_terminal_horizon_value_can_feed_downstream_signal_reality():
    horizon = derive_native_horizon_reality_v1(trace([whole(4), whole(7), whole(-2)]), mode="tally")
    contract = bind_native_horizon_conduit_v1(horizon, target_signal_slot=3, projection="value")
    frame = project_native_horizon_conduit_v1(horizon, contract)
    downstream = """witness memory signal 3
witness fee 2
witness total sum memory fee
resolve total
"""
    result = evaluate_native_signal_reality_v1(downstream, frame.bindings)
    assert result.value == 11


def test_affirm_horizon_can_drive_native_decision_via_signal_truth():
    horizon = derive_native_horizon_reality_v1(trace([truth(False), truth(True), truth(False)]), mode="affirm")
    contract = bind_native_horizon_conduit_v1(horizon, target_signal_slot=0)
    frame = project_native_horizon_conduit_v1(horizon, contract)
    assert frame.bindings[0].domain == base.TRUTH
    assert frame.bindings[0].value is True


def test_contract_is_bound_to_exact_trace_and_terminal_state():
    a = derive_native_horizon_reality_v1(trace([whole(1), whole(2)], b"a" * 32), mode="tally")
    b = derive_native_horizon_reality_v1(trace([whole(1), whole(2)], b"b" * 32), mode="tally")
    contract = bind_native_horizon_conduit_v1(a, target_signal_slot=1)
    with pytest.raises(NativeHorizonConduitError):
        project_native_horizon_conduit_v1(b, contract)


def test_projection_and_target_slot_change_contract_identity():
    horizon = derive_native_horizon_reality_v1(trace([whole(1)]), mode="remember")
    a = bind_native_horizon_conduit_v1(horizon, target_signal_slot=1, projection="value")
    b = bind_native_horizon_conduit_v1(horizon, target_signal_slot=2, projection="value")
    c = bind_native_horizon_conduit_v1(horizon, target_signal_slot=1, projection="ordinal")
    assert len({a.contract_digest, b.contract_digest, c.contract_digest}) == 3


def test_ordinal_projection_is_canonical_whole():
    horizon = derive_native_horizon_reality_v1(trace([whole(5), whole(6), whole(7)]), mode="remember")
    contract = bind_native_horizon_conduit_v1(horizon, target_signal_slot=9, projection="ordinal")
    frame = project_native_horizon_conduit_v1(horizon, contract, frame_ordinal=4)
    assert frame.ordinal == 4
    assert frame.bindings[9] == base.NativeValue(base.WHOLE, 2)


def test_invalid_slot_projection_and_negative_frame_fail_closed():
    horizon = derive_native_horizon_reality_v1(trace([whole(1)]), mode="remember")
    with pytest.raises(NativeHorizonConduitError):
        bind_native_horizon_conduit_v1(horizon, target_signal_slot=65536)
    with pytest.raises(NativeHorizonConduitError):
        bind_native_horizon_conduit_v1(horizon, target_signal_slot=0, projection="shared-state")
    contract = bind_native_horizon_conduit_v1(horizon, target_signal_slot=0)
    with pytest.raises(NativeHorizonConduitError):
        project_native_horizon_conduit_v1(horizon, contract, frame_ordinal=-1)

import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_pulse_reality_v1 import (
    MAX_PULSE_FRAMES_V1,
    NativePulseRealityError,
    PulseFrameV1,
    evaluate_native_pulse_reality_v1,
)

SOURCE = """witness price signal 0
witness fee 2
witness total sum price fee
resolve total
"""


def whole(value: int) -> base.NativeValue:
    return base.NativeValue(base.WHOLE, value)


def test_pulse_resolves_same_reality_across_time_without_loop_syntax():
    trace = evaluate_native_pulse_reality_v1(
        SOURCE,
        (PulseFrameV1(0, {0: whole(40)}), PulseFrameV1(1, {0: whole(41)})),
    )
    assert [v.value for v in trace.outputs] == [42, 43]
    assert len(trace.trace_digest) == 32


def test_pulse_trace_is_deterministic_and_order_sensitive():
    a = evaluate_native_pulse_reality_v1(
        SOURCE, (PulseFrameV1(0, {0: whole(1)}), PulseFrameV1(1, {0: whole(2)}))
    )
    b = evaluate_native_pulse_reality_v1(
        SOURCE, (PulseFrameV1(0, {0: whole(1)}), PulseFrameV1(1, {0: whole(2)}))
    )
    c = evaluate_native_pulse_reality_v1(
        SOURCE, (PulseFrameV1(0, {0: whole(2)}), PulseFrameV1(1, {0: whole(1)}))
    )
    assert a.trace_digest == b.trace_digest
    assert a.trace_digest != c.trace_digest


def test_pulse_rejects_time_splice_and_noncanonical_frames():
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, (PulseFrameV1(1, {0: whole(40)}),))
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, (PulseFrameV1(0, {0: whole(40)}), PulseFrameV1(2, {0: whole(41)})))
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, ())


def test_pulse_inherits_signal_fail_closed_binding_contract():
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, (PulseFrameV1(0, {}),))
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, (PulseFrameV1(0, {0: whole(40), 9: whole(1)}),))


def test_pulse_is_bounded():
    frames = tuple(PulseFrameV1(i, {0: whole(i)}) for i in range(MAX_PULSE_FRAMES_V1 + 1))
    with pytest.raises(NativePulseRealityError):
        evaluate_native_pulse_reality_v1(SOURCE, frames)


def test_mainstream_loop_surface_is_not_pulse_grammar():
    for bad in (
        "for x in y\nresolve x\n",
        "while true\nresolve x\n",
        "async fn tick\nresolve tick\n",
    ):
        with pytest.raises(NativePulseRealityError):
            evaluate_native_pulse_reality_v1(bad, (PulseFrameV1(0, {0: whole(1)}),))

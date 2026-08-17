import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_pulse_reality_v1 import PulseFrameV1, evaluate_native_pulse_reality_v1
from koschei.native_resonance_reality_v1 import derive_native_resonance_reality_v1
from koschei.native_resonance_conduit_v1 import (
    NativeResonanceConduitError,
    bind_resonance_conduit_v1,
    materialize_resonance_conduit_v1,
)

SOURCE = """witness x signal 0
resolve x
"""


def whole(value: int):
    return base.NativeValue(base.WHOLE, value)


def truth(value: bool):
    return base.NativeValue(base.TRUTH, value)


def test_resonance_conduit_projects_change_ordinals_into_destination_signal_frames():
    pulse = evaluate_native_pulse_reality_v1(
        SOURCE,
        (
            PulseFrameV1(0, {0: whole(1)}),
            PulseFrameV1(1, {0: whole(1)}),
            PulseFrameV1(2, {0: whole(2)}),
            PulseFrameV1(3, {0: whole(3)}),
        ),
    )
    resonance = derive_native_resonance_reality_v1(pulse, mode="change")
    contract = bind_resonance_conduit_v1(resonance, destination_slot=7, projection="ordinal")
    transfer = materialize_resonance_conduit_v1(resonance, contract)
    assert [frame.ordinal for frame in transfer.frames] == [0, 1]
    assert [frame.bindings[7].value for frame in transfer.frames] == [2, 3]
    assert len(transfer.transfer_digest) == 32


def test_occurred_projection_emits_truth_facts_without_execution_authority():
    pulse = evaluate_native_pulse_reality_v1(
        SOURCE,
        (PulseFrameV1(0, {0: whole(1)}), PulseFrameV1(1, {0: whole(2)})),
    )
    resonance = derive_native_resonance_reality_v1(pulse, mode="change")
    contract = bind_resonance_conduit_v1(resonance, destination_slot=9, projection="occurred")
    transfer = materialize_resonance_conduit_v1(resonance, contract)
    assert len(transfer.frames) == 1
    assert transfer.frames[0].bindings[9] == truth(True)


def test_trace_splice_fails_closed():
    a = derive_native_resonance_reality_v1(
        evaluate_native_pulse_reality_v1(
            SOURCE,
            (PulseFrameV1(0, {0: whole(1)}), PulseFrameV1(1, {0: whole(2)})),
        ),
        mode="change",
    )
    b = derive_native_resonance_reality_v1(
        evaluate_native_pulse_reality_v1(
            SOURCE,
            (PulseFrameV1(0, {0: whole(4)}), PulseFrameV1(1, {0: whole(5)})),
        ),
        mode="change",
    )
    contract = bind_resonance_conduit_v1(a, destination_slot=0, projection="ordinal")
    with pytest.raises(NativeResonanceConduitError):
        materialize_resonance_conduit_v1(b, contract)


def test_invalid_projection_and_slot_fail_closed():
    trace = derive_native_resonance_reality_v1(
        evaluate_native_pulse_reality_v1(
            SOURCE,
            (PulseFrameV1(0, {0: whole(1)}), PulseFrameV1(1, {0: whole(2)})),
        ),
        mode="change",
    )
    with pytest.raises(NativeResonanceConduitError):
        bind_resonance_conduit_v1(trace, destination_slot=70000, projection="ordinal")
    with pytest.raises(NativeResonanceConduitError):
        bind_resonance_conduit_v1(trace, destination_slot=0, projection="callback")

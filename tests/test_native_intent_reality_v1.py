import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_intent_reality_v1 import (
    IntentRealityV1,
    NativeIntentRealityError,
    derive_native_intent_reality_v1,
    verify_native_intent_reality_v1,
)


def whole(n):
    return base.NativeValue(base.WHOLE, n)


def truth(v):
    return base.NativeValue(base.TRUTH, v)


def glyphs(v):
    return base.NativeValue(base.GLYPHS, v)


def test_intent_commits_exact_adapter_action_and_value_without_executing():
    intent = derive_native_intent_reality_v1(adapter="network", action="publish", value=glyphs("hello"))
    assert intent.adapter == "network"
    assert intent.action == "publish"
    assert intent.value.value == "hello"
    assert len(intent.value_digest) == 32
    assert len(intent.intent_digest) == 32
    assert verify_native_intent_reality_v1(intent) is True


def test_intent_identity_changes_when_target_action_or_value_changes():
    a = derive_native_intent_reality_v1(adapter="network", action="publish", value=whole(7))
    b = derive_native_intent_reality_v1(adapter="network", action="publish", value=whole(8))
    c = derive_native_intent_reality_v1(adapter="persist", action="publish", value=whole(7))
    d = derive_native_intent_reality_v1(adapter="network", action="store", value=whole(7))
    assert len({a.intent_digest, b.intent_digest, c.intent_digest, d.intent_digest}) == 4


def test_intent_is_data_not_authority_or_callback():
    intent = derive_native_intent_reality_v1(adapter="signing", action="approve", value=truth(True))
    assert not hasattr(intent, "execute")
    assert not hasattr(intent, "send")
    assert not hasattr(intent, "call")
    assert "<committed>" in repr(intent)


def test_tampered_intent_fails_verification():
    good = derive_native_intent_reality_v1(adapter="network", action="publish", value=whole(7))
    forged = IntentRealityV1(good.adapter, good.action, whole(8), good.value_digest, good.intent_digest)
    with pytest.raises(NativeIntentRealityError):
        verify_native_intent_reality_v1(forged)


def test_noncanonical_labels_and_values_fail_closed():
    with pytest.raises(NativeIntentRealityError):
        derive_native_intent_reality_v1(adapter=" network", action="publish", value=whole(1))
    with pytest.raises(NativeIntentRealityError):
        derive_native_intent_reality_v1(adapter="network", action="", value=whole(1))
    with pytest.raises(NativeIntentRealityError):
        derive_native_intent_reality_v1(adapter="network", action="publish\nnow", value=whole(1))


def test_intent_does_not_smuggle_arbitrary_python_objects():
    with pytest.raises(NativeIntentRealityError):
        derive_native_intent_reality_v1(adapter="network", action="publish", value=object())

import pytest

from koschei import native_value_domains_v1 as base
from koschei.native_admission_reality_v1 import (
    NativeAdmissionRealityError,
    admit_native_intent_reality_v1,
    issue_admission_authority_v1,
)
from koschei.native_intent_reality_v1 import derive_native_intent_reality_v1


def intent(value="hello", adapter="network", action="publish"):
    return derive_native_intent_reality_v1(
        adapter=adapter, action=action, value=base.NativeValue(base.GLYPHS, value)
    )


def authority(i, *, start=100, end=200):
    return issue_admission_authority_v1(
        project_commitment=b"p" * 32, epoch=7, intent=i,
        not_before=start, expires_at=end, host_nonce=b"n" * 32,
    )


def test_exact_intent_can_cross_admission_membrane():
    i = intent()
    admitted = admit_native_intent_reality_v1(i, authority(i), now=150)
    assert admitted.intent_digest == i.intent_digest
    assert admitted.project_commitment == b"p" * 32
    assert admitted.epoch == 7
    assert len(admitted.admission_digest) == 32


def test_authority_for_one_intent_cannot_admit_another_value():
    a = intent("hello")
    b = intent("goodbye")
    with pytest.raises(NativeAdmissionRealityError):
        admit_native_intent_reality_v1(b, authority(a), now=150)


def test_adapter_and_action_are_part_of_exact_authority():
    a = intent(adapter="network", action="publish")
    for other in (
        intent(adapter="persist", action="publish"),
        intent(adapter="network", action="delete"),
    ):
        with pytest.raises(NativeAdmissionRealityError):
            admit_native_intent_reality_v1(other, authority(a), now=150)


def test_admission_window_is_fail_closed_and_short_lived():
    i = intent()
    auth = authority(i, start=100, end=200)
    with pytest.raises(NativeAdmissionRealityError):
        admit_native_intent_reality_v1(i, auth, now=99)
    with pytest.raises(NativeAdmissionRealityError):
        admit_native_intent_reality_v1(i, auth, now=200)
    with pytest.raises(NativeAdmissionRealityError):
        issue_admission_authority_v1(
            project_commitment=b"p" * 32, epoch=1, intent=i,
            not_before=0, expires_at=901, host_nonce=b"n" * 32,
        )


def test_repr_does_not_dump_project_or_authority_digest():
    i = intent()
    auth = authority(i)
    text = repr(auth)
    assert (b"p" * 32).hex() not in text
    assert auth.authority_digest.hex() not in text


def test_admission_is_not_execution():
    i = intent()
    admitted = admit_native_intent_reality_v1(i, authority(i), now=150)
    assert not hasattr(admitted, "execute")
    assert not hasattr(admitted, "send")
    assert not hasattr(admitted, "callback")

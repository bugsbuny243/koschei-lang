import pytest

from koschei.interpreter import EnumValue
from koschei.mir_variant_runtime_v1 import (
    MirVariantRuntimeError,
    split_canonical_variant_v1,
    variant_is_v1,
    variant_payload_v1,
)


def test_canonical_variant_identity_requires_exact_owner_and_variant():
    assert split_canonical_variant_v1("Option::Some") == ("Option", "Some")
    for invalid in ("", "Some", "::Some", "Option::", "A::B::C"):
        with pytest.raises(MirVariantRuntimeError):
            split_canonical_variant_v1(invalid)


def test_same_visible_variant_name_does_not_alias_different_owner():
    value = EnumValue("Alpha", "Ready", 7)
    assert variant_is_v1(value, "Alpha::Ready") is True
    assert variant_is_v1(value, "Beta::Ready") is False


def test_variant_comparison_refuses_host_object_shape_guessing():
    class FakeEnum:
        enum_name = "Option"
        variant = "Some"
        payload = 7

    with pytest.raises(MirVariantRuntimeError, match="EnumValue"):
        variant_is_v1(FakeEnum(), "Option::Some")


def test_payload_requires_exact_variant_identity():
    value = EnumValue("Result", "Ok", 42)
    assert variant_payload_v1(value, "Result::Ok") == 42
    with pytest.raises(MirVariantRuntimeError, match="proof mismatch"):
        variant_payload_v1(value, "Result::Err")


def test_payloadless_variant_cannot_be_extracted():
    value = EnumValue("Option", "None")
    with pytest.raises(MirVariantRuntimeError, match="no payload"):
        variant_payload_v1(value, "Option::None")

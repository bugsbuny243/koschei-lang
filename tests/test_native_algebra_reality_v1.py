import pytest

from koschei.native_algebra_reality_v1 import (
    NativeAlgebraRealityError,
    evaluate_native_algebra_reality_v1,
)


def test_exact_prime_field_arithmetic_is_canonical():
    source = """field 101
witness a scalar 7
witness b scalar 9
witness c add a b
witness d mul c b
resolve d
"""
    result = evaluate_native_algebra_reality_v1(source)
    assert result.value == 43
    assert len(result.reality_digest) == 32


def test_field_wrap_is_mathematics_not_host_overflow():
    source = """field 101
witness a scalar 100
witness b scalar 5
witness c add a b
resolve c
"""
    assert evaluate_native_algebra_reality_v1(source).value == 4


def test_inverse_is_exact_and_zero_fails_closed():
    source = """field 101
witness a scalar 9
witness b inv a
witness c mul a b
resolve c
"""
    assert evaluate_native_algebra_reality_v1(source).value == 1
    with pytest.raises(NativeAlgebraRealityError):
        evaluate_native_algebra_reality_v1("""field 101
witness z scalar 0
witness x inv z
resolve x
""")


def test_non_prime_and_noncanonical_residues_are_rejected():
    with pytest.raises(NativeAlgebraRealityError):
        evaluate_native_algebra_reality_v1("""field 100
witness a scalar 1
resolve a
""")
    with pytest.raises(NativeAlgebraRealityError):
        evaluate_native_algebra_reality_v1("""field 101
witness a scalar 101
resolve a
""")


def test_dependency_cycle_fails_closed():
    with pytest.raises(NativeAlgebraRealityError):
        evaluate_native_algebra_reality_v1("""field 101
witness a add b b
witness b add a a
resolve a
""")


def test_mainstream_operator_surface_is_not_algebra_grammar():
    for source in (
        "field 101\nwitness a scalar 1\na = a + 1\nresolve a\n",
        "field 101\nwitness a scalar 1\nwitness b scalar 2\nwitness c a + b\nresolve c\n",
    ):
        with pytest.raises(NativeAlgebraRealityError):
            evaluate_native_algebra_reality_v1(source)

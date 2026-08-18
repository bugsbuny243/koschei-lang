import pytest

from koschei.bounded_json_v1 import (
    JsonBudgetError,
    JsonBudgetV1,
    canonical_roundtrip_v1,
    encode_json_v1,
    parse_json_v1,
)


def test_canonical_order_and_compact_encoding():
    assert canonical_roundtrip_v1('{"b":2,"a":1}') == '{"a":1,"b":2}'


def test_input_byte_budget_fails_closed():
    budget = JsonBudgetV1(max_input_bytes=4, max_output_bytes=100, max_nodes=10, max_depth=4)
    with pytest.raises(JsonBudgetError):
        parse_json_v1('{"a":1}', budget=budget)


def test_depth_budget_fails_closed():
    budget = JsonBudgetV1(max_input_bytes=100, max_output_bytes=100, max_nodes=20, max_depth=2)
    with pytest.raises(JsonBudgetError):
        parse_json_v1('{"a":{"b":1}}', budget=budget)


def test_node_budget_fails_closed():
    budget = JsonBudgetV1(max_input_bytes=100, max_output_bytes=100, max_nodes=3, max_depth=10)
    with pytest.raises(JsonBudgetError):
        parse_json_v1('[1,2,3]', budget=budget)


def test_output_byte_budget_fails_closed():
    budget = JsonBudgetV1(max_input_bytes=100, max_output_bytes=4, max_nodes=10, max_depth=10)
    with pytest.raises(JsonBudgetError):
        encode_json_v1({"a": 1}, budget=budget)


def test_nonfinite_float_is_rejected():
    with pytest.raises(JsonBudgetError):
        encode_json_v1({"x": float("nan")})


def test_non_string_map_key_is_rejected():
    with pytest.raises(JsonBudgetError):
        encode_json_v1({1: "x"})

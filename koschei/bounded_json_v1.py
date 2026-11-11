"""Bounded canonical JSON building block for Koschei stdlib data/v1.

This module is intentionally self-contained and authority-free. It enforces
input/output byte, node and depth budgets before it can be promoted into the
interpreter/native stdlib surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


class JsonBudgetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JsonBudgetV1:
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 1_048_576
    max_nodes: int = 100_000
    max_depth: int = 64

    def validate(self) -> None:
        if min(self.max_input_bytes, self.max_output_bytes, self.max_nodes, self.max_depth) < 1:
            raise JsonBudgetError("all JSON budgets must be positive")


def _measure(value: Any, *, max_nodes: int, max_depth: int) -> tuple[int, int]:
    nodes = 0
    observed_depth = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise JsonBudgetError("json node budget exceeded")
        if depth > max_depth:
            raise JsonBudgetError("json depth budget exceeded")
        observed_depth = max(observed_depth, depth)
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise JsonBudgetError("json object keys must be strings")
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            for item in current:
                stack.append((item, depth + 1))
        elif current is None or isinstance(current, (str, bool, int, float)):
            continue
        else:
            raise JsonBudgetError(f"unsupported json value type: {type(current).__name__}")
    return nodes, observed_depth


def parse_json_v1(text: str, *, budget: JsonBudgetV1 = JsonBudgetV1()) -> Any:
    budget.validate()
    if not isinstance(text, str):
        raise JsonBudgetError("json input must be text")
    raw = text.encode("utf-8")
    if len(raw) > budget.max_input_bytes:
        raise JsonBudgetError("json input byte budget exceeded")
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise JsonBudgetError("invalid json") from exc
    _measure(value, max_nodes=budget.max_nodes, max_depth=budget.max_depth)
    return value


def encode_json_v1(value: Any, *, budget: JsonBudgetV1 = JsonBudgetV1()) -> str:
    budget.validate()
    _measure(value, max_nodes=budget.max_nodes, max_depth=budget.max_depth)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise JsonBudgetError("value is not canonical-json encodable") from exc
    if len(text.encode("utf-8")) > budget.max_output_bytes:
        raise JsonBudgetError("json output byte budget exceeded")
    return text


def canonical_roundtrip_v1(text: str, *, budget: JsonBudgetV1 = JsonBudgetV1()) -> str:
    return encode_json_v1(parse_json_v1(text, budget=budget), budget=budget)

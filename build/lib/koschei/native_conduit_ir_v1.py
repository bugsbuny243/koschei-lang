"""Koschei-native conduit composition on Native IR v1.

A conduit is a sealed local aperture, not a function parameter or import. This
module binds authenticated slot values directly into Native IR atoms, avoiding
legacy Program/function/let/return reconstruction.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .native_ir_v1 import NativeIrRealityV1, execute_native_ir_v1, lower_value_graph_to_native_ir_v1
from .native_mixed_reuse_v1 import NativeMixedReuseError, _conduit_contract
from .native_value_domains_v1 import NativeValue, ValueAtom, ValueTerm, parse_native_value_graph


class NativeConduitIrError(NativeMixedReuseError):
    pass


def _fail(message: str) -> None:
    raise NativeConduitIrError(message)


def lower_conduit_source_to_native_ir_v1(
    source: str,
    values_by_slot: Mapping[int, NativeValue],
) -> NativeIrRealityV1:
    """Bind exact sealed conduit slots directly into Koschei Native IR."""
    conduits = _conduit_contract(source)
    slots = {slot for slot, _ in conduits}
    if slots != set(values_by_slot):
        _fail("native conduit slots do not exactly match sealed input bindings")

    witness_by_slot = {slot: name for slot, name in conduits}
    rewritten: list[str] = []
    for line in source.rstrip("\n").split("\n"):
        tokens = line.split(" ")
        if len(tokens) == 4 and tokens[0] == "witness" and tokens[2] == "conduit":
            rewritten.append(f"witness {tokens[1]} 0")
        else:
            if "conduit" in tokens:
                _fail("conduit is valid only as a witness input aperture")
            rewritten.append(line)

    try:
        graph = parse_native_value_graph("\n".join(rewritten) + "\n")
    except Exception as error:
        raise NativeConduitIrError(str(error)) from error

    replacements = {witness_by_slot[slot]: value for slot, value in values_by_slot.items()}
    witnesses = []
    for witness in graph.witnesses:
        value = replacements.get(witness.name)
        if value is None:
            witnesses.append(witness)
        else:
            witnesses.append(replace(witness, term=ValueTerm(None, (ValueAtom(literal=value),))))
    graph = replace(graph, witnesses=tuple(witnesses))
    return lower_value_graph_to_native_ir_v1(graph)


def execute_conduit_source_native_ir_v1(
    source: str,
    values_by_slot: Mapping[int, NativeValue],
) -> NativeValue:
    return execute_native_ir_v1(lower_conduit_source_to_native_ir_v1(source, values_by_slot))


def compose_reusable_and_root_native_ir_v1(
    reusable_source: str,
    reusable_inputs: Mapping[int, NativeValue],
    root_source: str,
    *,
    root_slot: int,
) -> NativeValue:
    reusable_value = execute_conduit_source_native_ir_v1(reusable_source, reusable_inputs)
    return execute_conduit_source_native_ir_v1(root_source, {root_slot: reusable_value})

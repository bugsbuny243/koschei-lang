"""Koschei-native decision IR v1.

This lowers admitted decision realities directly into Native IR without creating
legacy Program/function/let/return AST nodes. `settle` remains a graph operation,
not statement control flow.
"""

from __future__ import annotations

from .native_decision_realities_v1 import (
    SETTLE,
    active_order_native_decision_graph,
    evaluate_native_decision_graph,
    parse_native_decision_graph,
)
from .native_ir_v1 import NativeIrAtomV1, NativeIrError, NativeIrRealityV1, NativeIrWitnessV1
from .native_value_domains_v1 import GLYPHS, TRUTH, WHOLE, MAX_GLYPHS_RESULT_BYTES, NativeValue
from .semantic import INT_MAX, INT_MIN


def lower_decision_graph_to_native_ir_v1(source: str) -> NativeIrRealityV1:
    graph = parse_native_decision_graph(source)
    values = evaluate_native_decision_graph(graph)
    order = active_order_native_decision_graph(graph, values)
    by_name = graph.by_name()
    lowered: list[NativeIrWitnessV1] = []
    for name in order:
        witness = by_name[name]
        atoms = tuple(NativeIrAtomV1(literal=atom.literal, witness=atom.witness) for atom in witness.term.atoms)
        lowered.append(NativeIrWitnessV1(name, witness.term.operation, atoms))
    return NativeIrRealityV1(tuple(lowered), graph.resolve)


def execute_native_decision_ir_v1(ir: NativeIrRealityV1) -> NativeValue:
    values: dict[str, NativeValue] = {}

    def atom_value(atom: NativeIrAtomV1) -> NativeValue:
        if atom.literal is not None:
            return atom.literal
        if atom.witness is None or atom.witness not in values:
            raise NativeIrError("native decision IR references an unavailable witness")
        return values[atom.witness]

    for witness in ir.witnesses:
        if witness.name in values:
            raise NativeIrError("native decision IR contains duplicate witness identity")
        if witness.operation is None:
            if len(witness.atoms) != 1:
                raise NativeIrError("native decision literal/reference witness has invalid arity")
            value = atom_value(witness.atoms[0])
        elif witness.operation == SETTLE:
            if len(witness.atoms) != 3:
                raise NativeIrError("settle requires exactly three native IR atoms")
            condition = atom_value(witness.atoms[0])
            affirmative = atom_value(witness.atoms[1])
            negative = atom_value(witness.atoms[2])
            if condition.domain != TRUTH:
                raise NativeIrError("settle condition must be truth")
            if affirmative.domain != negative.domain:
                raise NativeIrError("settle candidates must share one native domain")
            value = affirmative if bool(condition.value) else negative
        else:
            if len(witness.atoms) != 2:
                raise NativeIrError("native decision operation witness has invalid arity")
            left = atom_value(witness.atoms[0])
            right = atom_value(witness.atoms[1])
            op = witness.operation
            if op in {"sum", "difference", "product"}:
                if left.domain != WHOLE or right.domain != WHOLE:
                    raise NativeIrError(f"{op} requires whole/whole")
                a, b = int(left.value), int(right.value)
                result = a + b if op == "sum" else a - b if op == "difference" else a * b
                if not INT_MIN <= result <= INT_MAX:
                    raise NativeIrError(f"{op} exceeds signed Int64 reality")
                value = NativeValue(WHOLE, result)
            elif op == "same":
                if left.domain != right.domain:
                    raise NativeIrError("same requires identical native domains")
                value = NativeValue(TRUTH, left.value == right.value)
            elif op == "merge":
                if left.domain != GLYPHS or right.domain != GLYPHS:
                    raise NativeIrError("merge requires glyphs/glyphs")
                merged = str(left.value) + str(right.value)
                if len(merged.encode("utf-8")) > MAX_GLYPHS_RESULT_BYTES:
                    raise NativeIrError("merged glyphs exceeds native byte budget")
                value = NativeValue(GLYPHS, merged)
            else:
                raise NativeIrError(f"unsupported native decision IR operation {op!r}")
        values[witness.name] = value

    if ir.resolve not in values:
        raise NativeIrError("native decision IR resolve witness is unavailable")
    return values[ir.resolve]

"""Fail-closed CFG proof validation for Koschei MIR variant payload access.

`MirVariantIs` observes one compiler-selected canonical variant identity.
`MirVariantPayload` is legal only on a CFG path where the exact same source SSA
and variant identity were proven by the true edge of that observation.

This module does not inspect runtime objects, enum declarations, or source AST.
It validates only sealed MIR-shaped facts.
"""
from __future__ import annotations

from .mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from .mir_ir import MirBasicBlock, MirBranch, MirJump

VariantProofV1 = tuple[int, str]


def _canonical_variant_identity(value: str) -> bool:
    if not isinstance(value, str):
        return False
    owner, separator, variant = value.partition("::")
    return bool(separator and owner and variant and "::" not in variant)


def _variant_tests(blocks: tuple[MirBasicBlock, ...]) -> dict[int, VariantProofV1]:
    tests: dict[int, VariantProofV1] = {}
    for block in blocks:
        for instruction in block.instructions:
            if isinstance(instruction, (MirVariantIs, MirVariantPayload)):
                if not _canonical_variant_identity(instruction.variant):
                    raise ValueError(
                        "MIR variant identity must be canonical Owner::Variant"
                    )
            if isinstance(instruction, MirVariantIs):
                tests[instruction.target] = (instruction.source, instruction.variant)
    return tests


def _successors(block: MirBasicBlock) -> tuple[int, ...]:
    terminator = block.terminator
    if isinstance(terminator, MirJump):
        return (terminator.target,)
    if isinstance(terminator, MirBranch):
        return (terminator.then_block, terminator.else_block)
    return ()


def validate_variant_proofs_v1(blocks: tuple[MirBasicBlock, ...]) -> None:
    """Require exact true-edge proof before every `MirVariantPayload`.

    Proofs propagate across jumps and are intersected at CFG joins. A
    `MirVariantIs` creates a positive proof only on the true branch of the same
    basic block. This deliberately rejects payload extraction in the test block,
    on the false edge, after an ambiguous join, or under a different variant.
    """

    if not blocks:
        raise ValueError("MIR variant proof validation requires block 0")

    by_id = {block.id: block for block in blocks}
    if 0 not in by_id:
        raise ValueError("MIR variant proof validation requires block 0")

    tests = _variant_tests(blocks)

    incoming: dict[int, frozenset[VariantProofV1] | None] = {
        block.id: None for block in blocks
    }
    incoming[0] = frozenset()

    changed = True
    while changed:
        changed = False
        for block in blocks:
            facts = incoming[block.id]
            if facts is None:
                continue

            terminator = block.terminator
            edge_facts: list[tuple[int, frozenset[VariantProofV1]]] = []
            if isinstance(terminator, MirBranch):
                positive = tests.get(terminator.condition)
                if positive is None:
                    edge_facts.extend(
                        ((terminator.then_block, facts), (terminator.else_block, facts))
                    )
                else:
                    edge_facts.append(
                        (terminator.then_block, frozenset((*facts, positive)))
                    )
                    edge_facts.append((terminator.else_block, facts))
            elif isinstance(terminator, MirJump):
                edge_facts.append((terminator.target, facts))

            for target, candidate in edge_facts:
                if target not in incoming:
                    raise ValueError(
                        f"MIR variant proof edge targets unknown block {target}"
                    )
                current = incoming[target]
                merged = candidate if current is None else current.intersection(candidate)
                if merged != current:
                    incoming[target] = frozenset(merged)
                    changed = True

    for block in blocks:
        facts = incoming[block.id] or frozenset()
        for instruction in block.instructions:
            if not isinstance(instruction, MirVariantPayload):
                continue
            required = (instruction.source, instruction.variant)
            if required not in facts:
                raise ValueError(
                    "MIR variant payload lacks exact proven predecessor path: "
                    f"%{instruction.source} {instruction.variant}"
                )


__all__ = ["VariantProofV1", "validate_variant_proofs_v1"]

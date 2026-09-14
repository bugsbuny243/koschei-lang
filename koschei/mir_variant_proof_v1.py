"""Fail-closed CFG proof validation for Koschei MIR variant facts.

`MirVariantConstruct` materializes one already-canonical variant identity.
`MirVariantIs` observes one compiler-selected canonical variant identity.
`MirVariantPayload` is legal only on a CFG path where the exact same source SSA
and variant identity were proven by the true edge of that observation.

This validation hook also requires every instruction to belong to the exact MIR
v4 registry. That closes the seal boundary against unregistered dataclass-shaped
opcodes before fingerprinted MIR is accepted for execution.

This module does not inspect runtime objects or source AST.
"""
from __future__ import annotations

from .mir_extension_instructions_v4 import (
    MirVariantConstruct,
    MirVariantIs,
    MirVariantPayload,
)
from .mir_ir import MirBasicBlock, MirBranch, MirJump

VariantProofV1 = tuple[int, str]
VariantTestV1 = tuple[int, int, str]


def _canonical_variant_identity(value: str) -> bool:
    if not isinstance(value, str):
        return False
    owner, separator, variant = value.partition("::")
    return bool(separator and owner and variant and "::" not in variant)


def _require_exact_registry_v4(blocks: tuple[MirBasicBlock, ...]) -> None:
    # Lazy import avoids the bootstrap cycle: the registry imports core MIR
    # instruction classes from mir_ir, while mir_ir calls this validator only
    # after all core classes are defined.
    from .mir_instruction_registry_v4 import require_mir_v4_instruction

    for block in blocks:
        for instruction in block.instructions:
            require_mir_v4_instruction(instruction)


def _variant_tests(blocks: tuple[MirBasicBlock, ...]) -> dict[int, VariantTestV1]:
    tests: dict[int, VariantTestV1] = {}
    for block in blocks:
        for instruction in block.instructions:
            if isinstance(
                instruction,
                (MirVariantConstruct, MirVariantIs, MirVariantPayload),
            ):
                if not _canonical_variant_identity(instruction.variant):
                    raise ValueError(
                        "MIR variant identity must be canonical Owner::Variant"
                    )
            if isinstance(instruction, MirVariantIs):
                tests[instruction.target] = (
                    block.id,
                    instruction.source,
                    instruction.variant,
                )
    return tests


def validate_variant_proofs_v1(blocks: tuple[MirBasicBlock, ...]) -> None:
    """Require exact registry membership and true-edge payload proof.

    Proofs propagate across jumps and are intersected at CFG joins. A
    `MirVariantIs` creates a positive proof only when the branch consuming its
    result is in the same basic block as that exact test. This deliberately
    rejects payload extraction in the test block, on the false edge, after an
    ambiguous join, under a different variant, or from a non-dominating test.
    """

    if not blocks:
        raise ValueError("MIR variant proof validation requires block 0")

    _require_exact_registry_v4(blocks)

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
                test = tests.get(terminator.condition)
                positive = None
                if test is not None and test[0] == block.id:
                    positive = (test[1], test[2])
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


__all__ = ["VariantProofV1", "VariantTestV1", "validate_variant_proofs_v1"]

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from koschei.ast_nodes import Block, FunctionDeclaration, Program, SourceLocation
from koschei.mir import (
    MirFunction,
    MirModule,
    MirResources,
    _fingerprint,
)
from koschei.mir_extension_instructions_v4 import MirVariantIs, MirVariantPayload
from koschei.mir_ir import MirBasicBlock, MirConst, MirReturn, block_contract
from koschei.type_system import BOOL, INT, VOID
from koschei.typed_hir import TypedHIRReport


def _blocks(variant: str) -> tuple[MirBasicBlock, ...]:
    location = SourceLocation(7, 11)
    return (
        MirBasicBlock(
            0,
            (
                MirConst(0, None, VOID, location),
                MirVariantIs(1, 0, variant, BOOL, location),
                MirVariantPayload(2, 0, variant, INT, location),
            ),
            MirReturn(None),
        ),
    )


def _module(variant: str) -> MirModule:
    location = SourceLocation(1, 1)
    declaration = FunctionDeclaration(
        "main",
        (),
        None,
        Block(()),
        location,
    )
    blocks = _blocks(variant)
    function = MirFunction(
        name="main",
        parameters=(),
        return_type=VOID,
        calls=(),
        effects=(),
        resources=MirResources(
            basic_blocks=1,
            instructions=3,
            ast_fallbacks=0,
            backward_edges=0,
            self_recursive=False,
        ),
        declaration=declaration,
        blocks=blocks,
    )
    report = TypedHIRReport((), (), 0)
    return MirModule(
        key="root",
        name="root",
        path=Path("root.ks"),
        program=Program((declaration,)),
        imports=MappingProxyType({}),
        functions=(function,),
        typed_report=report,
    )


def test_block_contract_preserves_exact_canonical_variant_identity() -> None:
    contract = block_contract(_blocks("Alpha::Ready")[0])
    variant_instructions = [
        item
        for item in contract["instructions"]
        if item["kind"] in {"MirVariantIs", "MirVariantPayload"}
    ]

    assert [item["kind"] for item in variant_instructions] == [
        "MirVariantIs",
        "MirVariantPayload",
    ]
    assert [item["variant"] for item in variant_instructions] == [
        "Alpha::Ready",
        "Alpha::Ready",
    ]


def test_owner_substitution_changes_sealed_mir_fingerprint() -> None:
    alpha = _module("Alpha::Ready")
    beta = _module("Beta::Ready")

    alpha_fingerprint = _fingerprint("root", MappingProxyType({"root": alpha}))
    beta_fingerprint = _fingerprint("root", MappingProxyType({"root": beta}))

    assert alpha_fingerprint != beta_fingerprint


def test_same_canonical_semantics_produces_same_fingerprint() -> None:
    first = _module("Result::Ok")
    second = _module("Result::Ok")

    assert _fingerprint("root", MappingProxyType({"root": first})) == _fingerprint(
        "root", MappingProxyType({"root": second})
    )

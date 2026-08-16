"""Authenticated Object Space -> Koschei Native IR dispatch v1.

This is a native execution authority path, not a compatibility compiler path.
Frontend selection comes only from authenticated Object Space graph metadata.
Source appearance, filename, parser success and legacy fallback are never routing
signals on this path.

V1 deliberately supports only the authenticated native witness frontend. Other
Object Space schemas fail closed until they receive an explicit Native IR handler.
"""

from __future__ import annotations

from dataclasses import dataclass

from .native_ir_v1 import (
    NativeIrAtomV1,
    NativeIrRealityV1,
    NativeIrWitnessV1,
    execute_native_ir_v1,
)
from .native_kernel_v1 import dependency_order, parse_native_kernel
from .native_value_domains_v1 import NativeValue, WHOLE
from .object_space_frontend_identity_v1 import (
    NATIVE_WITNESS_FRONTEND_V1,
    ObjectSpaceFrontendIdentityError,
    decode_authenticated_frontend_graph,
    is_authenticated_frontend_graph_secret,
)
from .object_space_v1 import ObjectSpaceProject


class ObjectSpaceNativeIrDispatchError(ObjectSpaceFrontendIdentityError):
    pass


@dataclass(frozen=True, slots=True)
class NativeIrExecutionAuthorityV1:
    """Authenticated execution authority after Object Space admission.

    The authority deliberately contains Native IR and the resolved native value,
    not Program/ModuleGraph/FunctionDeclaration compatibility carriers.
    """

    frontend_id: bytes
    ir: NativeIrRealityV1
    value: NativeValue


def _fail(message: str) -> None:
    raise ObjectSpaceNativeIrDispatchError(message)


def _native_ascii(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        _fail("authenticated native payload must be bytes")
    try:
        return payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ObjectSpaceNativeIrDispatchError(
            "authenticated witness frontend v1 requires canonical ASCII source"
        ) from error


def lower_authenticated_object_space_to_native_ir_v1(
    project: ObjectSpaceProject,
) -> NativeIrRealityV1:
    """Lower authenticated Object Space authority directly to Native IR.

    This function intentionally does not call check_native_kernel(), because that
    compatibility helper also constructs the legacy AST. Native syntax/graph
    admission is performed by parse_native_kernel() and dependency_order(), then
    the admitted witness reality is represented directly in Native IR.
    """

    if not isinstance(project, ObjectSpaceProject):
        _fail("Native IR dispatch requires a canonical ObjectSpaceProject")
    if not is_authenticated_frontend_graph_secret(project.graph_secret):
        _fail(
            "Object Space schema has no registered Native IR authority handler; "
            "legacy/source-sniff fallback is forbidden"
        )

    records = decode_authenticated_frontend_graph(project)
    if len(records) != 1:
        _fail("authenticated witness Native IR v1 requires exactly one root object")
    record = records[0]
    if record.frontend_id != NATIVE_WITNESS_FRONTEND_V1:
        _fail("authenticated frontend identity has no Native IR witness handler")
    if record.object_id != project.root_object_id:
        _fail("authenticated Native IR object is not the Object Space root")

    source = _native_ascii(project.object_payloads[record.object_id])
    try:
        kernel = parse_native_kernel(source)
        order = dependency_order(kernel)
    except Exception as error:
        raise ObjectSpaceNativeIrDispatchError(str(error)) from error

    by_name = kernel.by_name()
    lowered: list[NativeIrWitnessV1] = []
    for name in order:
        witness = by_name[name]
        atoms = tuple(
            NativeIrAtomV1(
                literal=(NativeValue(WHOLE, atom.literal) if atom.literal is not None else None),
                witness=atom.witness,
            )
            for atom in witness.term.atoms
        )
        lowered.append(
            NativeIrWitnessV1(
                name=witness.name,
                operation=witness.term.operation,
                atoms=atoms,
            )
        )
    return NativeIrRealityV1(tuple(lowered), kernel.resolve)


def execute_authenticated_object_space_native_ir_v1(
    project: ObjectSpaceProject,
) -> NativeIrExecutionAuthorityV1:
    """Authenticate, lower and execute without Program/ModuleGraph fallback."""

    ir = lower_authenticated_object_space_to_native_ir_v1(project)
    value = execute_native_ir_v1(ir)
    return NativeIrExecutionAuthorityV1(
        frontend_id=NATIVE_WITNESS_FRONTEND_V1,
        ir=ir,
        value=value,
    )

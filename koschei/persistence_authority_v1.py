"""Exact-object persistence authority for Koschei bootstrap v1.

Persistence must not be general filesystem authority with a nicer name. A
PersistCaps token is sealed to one exact absolute state-object path plus explicit
payload/deadline budgets. The path is chosen only while narrowing PersistRoot; it
is never supplied again to load/commit operations.

The current ``caps.persist.allow`` spelling is compatibility/bootstrap vocabulary,
not final Koschei-native grammar.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from . import capabilities as _caps
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from .ast_nodes import CallExpression, Literal, MemberExpression, SourceLocation
from .type_system import NamedType

_MIN_BYTES = 1
_MAX_BYTES = 16 * 1024 * 1024
_MIN_DEADLINE_MS = 1
_MAX_DEADLINE_MS = 120_000

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None
_ORIGINAL_CAPS_INSPECT = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_VALIDATE = None


@dataclass(frozen=True, slots=True)
class PersistPolicy:
    path: str
    max_bytes: int
    deadline_ms: int


def _canonical_exact_path(raw: str) -> str | None:
    if "\x00" in raw:
        return None
    text = raw.strip()
    if not text or not os.path.isabs(text):
        return None
    canonical = os.path.normpath(text)
    if canonical == os.path.sep:
        return None
    name = os.path.basename(canonical)
    if not name or name in {".", ".."}:
        return None
    return canonical


def _literal_int(expression) -> int | None:
    if not isinstance(expression, Literal):
        return None
    value = expression.value
    if type(value) is not int:
        return None
    return value


def _policy_from_ast(arguments, location: SourceLocation) -> PersistPolicy:
    if len(arguments) != 3:
        raise _semantic.SemanticError(
            "KS2420",
            "PersistRoot.allow() exact_file + iki bütçe olmak üzere tam 3 argüman bekler.",
            location,
        )
    path_expression = arguments[0]
    if not isinstance(path_expression, Literal) or not isinstance(path_expression.value, str):
        raise _semantic.SemanticError(
            "KS2420",
            "PersistRoot.allow() v1 exact_file değeri statik String literal olmalıdır.",
            location,
        )
    canonical = _canonical_exact_path(path_expression.value)
    if canonical is None:
        raise _semantic.SemanticError(
            "KS2421",
            "PersistRoot.allow() v1 yalnızca exact absolute file path kabul eder.",
            location,
        )
    max_bytes = _literal_int(arguments[1])
    deadline_ms = _literal_int(arguments[2])
    if max_bytes is None or deadline_ms is None:
        raise _semantic.SemanticError(
            "KS2420",
            "PersistRoot.allow() v1 bütçeleri statik Int literal olmalıdır.",
            location,
        )
    if not _MIN_BYTES <= max_bytes <= _MAX_BYTES:
        raise _semantic.SemanticError(
            "KS2421",
            f"Persist max_bytes {_MIN_BYTES}..{_MAX_BYTES} aralığında olmalıdır.",
            location,
        )
    if not _MIN_DEADLINE_MS <= deadline_ms <= _MAX_DEADLINE_MS:
        raise _semantic.SemanticError(
            "KS2421",
            f"Persist deadline_ms {_MIN_DEADLINE_MS}..{_MAX_DEADLINE_MS} aralığında olmalıdır.",
            location,
        )
    return PersistPolicy(canonical, max_bytes, deadline_ms)


def _runtime_policy(path: Any, max_bytes: Any, deadline_ms: Any) -> PersistPolicy | _runtime.KsError:
    if not isinstance(path, str):
        return _runtime.KsError("KS2420: Persist exact_file String olmalıdır")
    canonical = _canonical_exact_path(path)
    if canonical is None:
        return _runtime.KsError("KS2421: Persist exact_file absolute regular-file hedefi olmalıdır")
    if type(max_bytes) is not int or type(deadline_ms) is not int:
        return _runtime.KsError("KS2420: Persist bütçeleri Int olmalıdır")
    if not _MIN_BYTES <= max_bytes <= _MAX_BYTES:
        return _runtime.KsError("KS2421: Persist max_bytes güvenlik sınırı dışında")
    if not _MIN_DEADLINE_MS <= deadline_ms <= _MAX_DEADLINE_MS:
        return _runtime.KsError("KS2421: Persist deadline_ms güvenlik sınırı dışında")
    return PersistPolicy(canonical, max_bytes, deadline_ms)


class PersistRoot(_runtime._NarrowedCapability):
    __slots__ = ()

    def allow(self, path: Any, max_bytes: Any, deadline_ms: Any):
        policy = _runtime_policy(path, max_bytes, deadline_ms)
        if isinstance(policy, _runtime.KsError):
            return policy
        return PersistCaps(policy)


class PersistCaps(_runtime._NarrowedCapability):
    __slots__ = ("policy",)

    def __init__(self, policy: PersistPolicy) -> None:
        self.policy = policy


_BaseSystemCaps = _runtime.SystemCaps


class SystemCaps(_BaseSystemCaps):
    __slots__ = ("persist",)

    def __init__(self) -> None:
        super().__init__()
        self.persist = PersistRoot()


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "PersistRoot":
        if method_name != "allow":
            raise _semantic.SemanticError(
                "KS2402",
                "PersistRoot doğrudan I/O yapamaz; önce exact object policy ile allow kullanın.",
                location,
            )
        values = argument_types or []
        if len(values) != 3:
            raise _semantic.SemanticError(
                "KS2420",
                f"PersistRoot.allow() 3 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(("String",), values[0], "Persist exact_file", location)
        self._require_assignable(("Int",), values[1], "Persist max_bytes", location)
        self._require_assignable(("Int",), values[2], "Persist deadline_ms", location)
        _policy_from_ast(arguments or [], location)
        self.capability_count += 1
        return "PersistCaps"

    if receiver_type == "PersistCaps":
        if method_name in _semantic.NARROWING_METHODS:
            raise _semantic.SemanticError(
                "KS2403",
                "PersistCaps zaten exact-object authority'dir; yeniden genişletilemez.",
                location,
            )
        raise _semantic.SemanticError(
            "KS2404",
            f"PersistCaps v1 '{method_name}' işlemi runtime persistence contract kurulmadan kullanılamaz.",
            location,
        )

    return _ORIGINAL_CHECK_METHOD_CALL(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _manifest_scope(arguments) -> str:
    if len(arguments) != 3:
        return _caps.DYNAMIC
    path_expression = arguments[0]
    if not isinstance(path_expression, Literal) or not isinstance(path_expression.value, str):
        return _caps.DYNAMIC
    canonical = _canonical_exact_path(path_expression.value)
    max_bytes = _literal_int(arguments[1])
    deadline_ms = _literal_int(arguments[2])
    if canonical is None or max_bytes is None or deadline_ms is None:
        return _caps.DYNAMIC
    return f"{canonical} | bytes={max_bytes} | deadline_ms={deadline_ms}"


def _inspect_manifest(expression, roots, bindings, manifest):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, MemberExpression)
        and expression.callee.member == "allow"
        and _caps._root_domain(expression.callee.object, roots) == "persist"
    ):
        manifest.grants.append(
            _caps.Grant(
                domain="persist",
                scope=_manifest_scope(expression.arguments),
                read_only=False,
                location=expression.location,
            )
        )
        return
    return _ORIGINAL_CAPS_INSPECT(expression, roots, bindings, manifest)


def _runtime_type_node(value):
    if isinstance(value, PersistRoot):
        return NamedType("PersistRoot")
    if isinstance(value, PersistCaps):
        return NamedType("PersistCaps")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _validate_capability_backend(self) -> None:
    for declaration in self.program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"PersistRoot", "PersistCaps"} for name in parameter.type_ref.names):
                raise _codegen.CodegenError(
                    "KS4001",
                    "Persist capability native ABI henüz mühürlenmedi; native build fail-closed durduruldu.",
                    parameter.location,
                )
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member == "persist":
                    raise _codegen.CodegenError(
                        "KS4001",
                        "Persist capability native ABI henüz mühürlenmedi; native build fail-closed durduruldu.",
                        expression.location,
                    )
    return _ORIGINAL_CODEGEN_VALIDATE(self)


def install_persistence_authority_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_CHECK_METHOD_CALL, _ORIGINAL_CAPS_INSPECT
    global _ORIGINAL_RUNTIME_TYPE_NODE, _ORIGINAL_CODEGEN_VALIDATE
    if _INSTALLED:
        return

    _semantic.CAPABILITY_MEMBERS["persist"] = "PersistRoot"
    _semantic.ROOT_METHODS["PersistRoot"] = {"allow": "PersistCaps"}
    _semantic.NARROWED_METHODS["PersistCaps"] = set()
    _semantic.CAPABILITY_TYPES.update({"PersistRoot", "PersistCaps"})
    _semantic.ROOT_CAPABILITY_TYPES.add("PersistRoot")

    _caps.TYPE_DOMAINS.update({"PersistRoot": "persist", "PersistCaps": "persist"})
    _caps.DOMAIN_TITLES["persist"] = "KALICI DURUM"
    if "persist" not in _caps.DOMAIN_ORDER:
        _caps.DOMAIN_ORDER = (*_caps.DOMAIN_ORDER, "persist")

    _runtime.PersistRoot = PersistRoot
    _runtime.PersistCaps = PersistCaps
    _runtime.SystemCaps = SystemCaps

    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call

    _ORIGINAL_CAPS_INSPECT = _caps._inspect
    _caps._inspect = _inspect_manifest

    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node

    _ORIGINAL_CODEGEN_VALIDATE = _codegen.GoCodegen._validate_capability_backend
    _codegen.GoCodegen._validate_capability_backend = _validate_capability_backend

    _INSTALLED = True

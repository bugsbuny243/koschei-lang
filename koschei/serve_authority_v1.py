"""Bootstrap authority envelope for future bounded HTTP ingress.

This slice deliberately creates *authority*, not a listener. A Koschei program may
narrow ``SystemCaps.serve`` to one exact loopback bind and four explicit budgets,
but ``ServeCaps`` exposes no serving operation yet. Native Go generation fails
closed for any program that uses this provisional authority until the same
listener contract exists in that backend.

The surface is compatibility vocabulary. It is not a claim that ``caps.serve`` /
``allow`` are the final Koschei-native grammar names.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Any

from . import capabilities as _caps
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from .ast_nodes import CallExpression, Literal, MemberExpression, SourceLocation
from .type_system import NamedType

_MIN_CONNECTIONS = 1
_MAX_CONNECTIONS = 4096
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
class ServePolicy:
    bind: str
    max_connections: int
    max_request_bytes: int
    max_response_bytes: int
    deadline_ms: int


def _parse_loopback_bind(raw: str) -> tuple[str, int] | None:
    text = raw.strip()
    if not text:
        return None

    host: str
    port_text: str
    if text.startswith("["):
        closing = text.find("]")
        if closing <= 1 or closing + 1 >= len(text) or text[closing + 1] != ":":
            return None
        host = text[1:closing]
        port_text = text[closing + 2 :]
    else:
        host, separator, port_text = text.rpartition(":")
        if not separator or not host:
            return None

    try:
        port = int(port_text, 10)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None

    if host.lower() == "localhost":
        return host.lower(), port
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if not address.is_loopback:
        return None
    return address.compressed, port


def _literal_int(expression) -> int | None:
    if not isinstance(expression, Literal):
        return None
    value = expression.value
    if type(value) is not int:
        return None
    return value


def _policy_from_ast(arguments, location: SourceLocation) -> ServePolicy:
    if len(arguments) != 5:
        raise _semantic.SemanticError(
            "KS2410",
            "ServeRoot.allow() bind + dört bütçe olmak üzere tam 5 argüman bekler.",
            location,
        )

    bind_expression = arguments[0]
    if not isinstance(bind_expression, Literal) or not isinstance(bind_expression.value, str):
        raise _semantic.SemanticError(
            "KS2410",
            "ServeRoot.allow() v1 bind adresi statik String literal olmalıdır.",
            location,
        )
    bind = bind_expression.value
    if _parse_loopback_bind(bind) is None:
        raise _semantic.SemanticError(
            "KS2411",
            "ServeRoot.allow() v1 yalnızca açık loopback host:port kabul eder; "
            "wildcard/public bind reddedildi.",
            location,
        )

    budgets = [_literal_int(item) for item in arguments[1:]]
    if any(item is None for item in budgets):
        raise _semantic.SemanticError(
            "KS2410",
            "ServeRoot.allow() v1 bütçeleri statik Int literal olmalıdır.",
            location,
        )
    max_connections, max_request_bytes, max_response_bytes, deadline_ms = budgets
    assert max_connections is not None
    assert max_request_bytes is not None
    assert max_response_bytes is not None
    assert deadline_ms is not None

    checks = (
        (
            "max_connections",
            max_connections,
            _MIN_CONNECTIONS,
            _MAX_CONNECTIONS,
        ),
        ("max_request_bytes", max_request_bytes, _MIN_BYTES, _MAX_BYTES),
        ("max_response_bytes", max_response_bytes, _MIN_BYTES, _MAX_BYTES),
        ("deadline_ms", deadline_ms, _MIN_DEADLINE_MS, _MAX_DEADLINE_MS),
    )
    for name, value, minimum, maximum in checks:
        if not minimum <= value <= maximum:
            raise _semantic.SemanticError(
                "KS2411",
                f"ServeRoot.allow() {name} {minimum}..{maximum} aralığında olmalıdır; "
                f"{value} reddedildi.",
                location,
            )

    return ServePolicy(
        bind=bind,
        max_connections=max_connections,
        max_request_bytes=max_request_bytes,
        max_response_bytes=max_response_bytes,
        deadline_ms=deadline_ms,
    )


def _runtime_policy(
    bind: Any,
    max_connections: Any,
    max_request_bytes: Any,
    max_response_bytes: Any,
    deadline_ms: Any,
) -> ServePolicy | _runtime.KsError:
    if not isinstance(bind, str):
        return _runtime.KsError("KS2410: Serve bind String olmalıdır")
    if _parse_loopback_bind(bind) is None:
        return _runtime.KsError(
            "KS2411: Serve v1 yalnızca açık loopback host:port kabul eder"
        )

    values = (
        max_connections,
        max_request_bytes,
        max_response_bytes,
        deadline_ms,
    )
    if any(type(value) is not int for value in values):
        return _runtime.KsError("KS2410: Serve bütçeleri Int olmalıdır")

    checks = (
        (max_connections, _MIN_CONNECTIONS, _MAX_CONNECTIONS, "max_connections"),
        (max_request_bytes, _MIN_BYTES, _MAX_BYTES, "max_request_bytes"),
        (max_response_bytes, _MIN_BYTES, _MAX_BYTES, "max_response_bytes"),
        (deadline_ms, _MIN_DEADLINE_MS, _MAX_DEADLINE_MS, "deadline_ms"),
    )
    for value, minimum, maximum, name in checks:
        if not minimum <= value <= maximum:
            return _runtime.KsError(
                f"KS2411: Serve {name} {minimum}..{maximum} aralığında olmalıdır"
            )

    return ServePolicy(
        bind=bind,
        max_connections=max_connections,
        max_request_bytes=max_request_bytes,
        max_response_bytes=max_response_bytes,
        deadline_ms=deadline_ms,
    )


class ServeRoot(_runtime._NarrowedCapability):
    __slots__ = ()

    def allow(
        self,
        bind: Any,
        max_connections: Any,
        max_request_bytes: Any,
        max_response_bytes: Any,
        deadline_ms: Any,
    ) -> "ServeCaps | _runtime.KsError":
        policy = _runtime_policy(
            bind,
            max_connections,
            max_request_bytes,
            max_response_bytes,
            deadline_ms,
        )
        if isinstance(policy, _runtime.KsError):
            return policy
        return ServeCaps(policy)


class ServeCaps(_runtime._NarrowedCapability):
    __slots__ = ("policy",)

    def __init__(self, policy: ServePolicy) -> None:
        self.policy = policy


class SystemCaps:
    __slots__ = ("net", "disk", "env", "process", "serve")

    def __init__(self) -> None:
        self.net = _runtime.NetRoot()
        self.disk = _runtime.DiskRoot()
        self.env = _runtime.EnvRoot()
        self.process = _runtime.ProcessRoot()
        self.serve = ServeRoot()


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "ServeRoot":
        if method_name != "allow":
            raise _semantic.SemanticError(
                "KS2402",
                "ServeRoot doğrudan işlem yapamaz; önce allow ile daraltın.",
                location,
            )
        values = argument_types or []
        if len(values) != 5:
            raise _semantic.SemanticError(
                "KS2410",
                f"ServeRoot.allow() 5 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(("String",), values[0], "Serve bind", location)
        for index, value in enumerate(values[1:], start=1):
            self._require_assignable(
                ("Int",),
                value,
                f"Serve bütçesi {index}",
                location,
            )
        _policy_from_ast(arguments or [], location)
        self.capability_count += 1
        return "ServeCaps"

    if receiver_type == "ServeCaps":
        if method_name in _semantic.NARROWING_METHODS:
            raise _semantic.SemanticError(
                "KS2403",
                "ServeCaps daraltılmış bir yetkidir; yeniden genişletilemez.",
                location,
            )
        raise _semantic.SemanticError(
            "KS2404",
            f"ServeCaps v1 '{method_name}' işlemine henüz izin vermez; listener ABI "
            "ayrı güvenlik kapısından geçmelidir.",
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


def _serve_manifest_scope(arguments) -> str:
    if len(arguments) != 5:
        return _caps.DYNAMIC
    bind_expression = arguments[0]
    if not isinstance(bind_expression, Literal) or not isinstance(bind_expression.value, str):
        return _caps.DYNAMIC
    budgets = [_literal_int(item) for item in arguments[1:]]
    if any(value is None for value in budgets):
        return _caps.DYNAMIC
    connections, request_bytes, response_bytes, deadline_ms = budgets
    return (
        f"{bind_expression.value} | connections={connections} | "
        f"request_bytes={request_bytes} | response_bytes={response_bytes} | "
        f"deadline_ms={deadline_ms}"
    )


def _inspect_manifest(expression, roots, bindings, manifest):
    if (
        isinstance(expression, CallExpression)
        and isinstance(expression.callee, MemberExpression)
        and expression.callee.member == "allow"
        and _caps._root_domain(expression.callee.object, roots) == "serve"
    ):
        manifest.grants.append(
            _caps.Grant(
                domain="serve",
                scope=_serve_manifest_scope(expression.arguments),
                read_only=False,
                location=expression.location,
            )
        )
        return
    return _ORIGINAL_CAPS_INSPECT(expression, roots, bindings, manifest)


def _runtime_type_node(value):
    if isinstance(value, ServeRoot):
        return NamedType("ServeRoot")
    if isinstance(value, ServeCaps):
        return NamedType("ServeCaps")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _validate_capability_backend(self) -> None:
    for declaration in self.program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"ServeRoot", "ServeCaps"} for name in parameter.type_ref.names):
                raise _codegen.CodegenError(
                    "KS4001",
                    "Serve capability native listener ABI henüz mühürlenmedi; native build "
                    "fail-closed durduruldu.",
                    parameter.location,
                )
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member == "serve":
                    raise _codegen.CodegenError(
                        "KS4001",
                        "Serve capability native listener ABI henüz mühürlenmedi; native build "
                        "fail-closed durduruldu.",
                        expression.location,
                    )
    return _ORIGINAL_CODEGEN_VALIDATE(self)


def install_serve_authority_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_CHECK_METHOD_CALL, _ORIGINAL_CAPS_INSPECT
    global _ORIGINAL_RUNTIME_TYPE_NODE, _ORIGINAL_CODEGEN_VALIDATE
    if _INSTALLED:
        return

    # Mutate shared registries in place so modules that imported these objects
    # earlier observe the new sensitive authority types too.
    _semantic.CAPABILITY_MEMBERS["serve"] = "ServeRoot"
    _semantic.ROOT_METHODS["ServeRoot"] = {"allow": "ServeCaps"}
    _semantic.NARROWED_METHODS["ServeCaps"] = set()
    _semantic.CAPABILITY_TYPES.update({"ServeRoot", "ServeCaps"})
    _semantic.ROOT_CAPABILITY_TYPES.add("ServeRoot")

    _caps.TYPE_DOMAINS.update({"ServeRoot": "serve", "ServeCaps": "serve"})
    _caps.DOMAIN_TITLES["serve"] = "HTTP SUNUCU"
    if "serve" not in _caps.DOMAIN_ORDER:
        _caps.DOMAIN_ORDER = (*_caps.DOMAIN_ORDER, "serve")

    _runtime.ServeRoot = ServeRoot
    _runtime.ServeCaps = ServeCaps
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

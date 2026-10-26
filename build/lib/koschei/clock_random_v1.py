"""Clock and random authority v1 (readiness gate G3).

Time and randomness are read only through narrowed capabilities::

    fn main(caps: SystemCaps) {
        let clock = caps.clock.allow(1000)
        let today = clock.now_ms() / 86400000
        let random = caps.random.allow(64)
        let token = random.hex(16) or return
        let die = random.below(6) or return
    }

``caps.clock.allow(resolution_ms)`` takes one static Int literal between 1 and
``MAX_RESOLUTION_MS`` (one day). ``ClockCaps.now_ms()`` is the wall clock in
milliseconds since 1970-01-01 UTC and ``monotonic_ms()`` the milliseconds since
an arbitrary start that never go backwards; both are rounded down to the
resolution. A coarse clock is weaker authority: code holding a one-second clock
cannot time anything finer.

``caps.random.allow(max_bytes)`` takes one static Int literal between 1 and
``MAX_RANDOM_BYTES``: the most randomness the token may ever produce.
``RandomCaps.hex(count)`` returns ``count`` fresh bytes (1..1024) as lowercase
hex; ``below(bound)`` returns a uniform Int in ``0..bound-1`` and costs eight
bytes of the budget. An argument out of range is KS3451, an exhausted budget
KS3450; neither draws or charges anything. Randomness comes only from the
operating system's cryptographically secure source (Python ``secrets``, Go
``crypto/rand``); Koschei implements no generator of its own.

Both domains reach no resource, so native binaries may carry them.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

from . import capabilities as _caps
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_executor_v1 as _mir_executor
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import _typed_expr
from . import _typed_ops
from .ast_nodes import Literal, MemberExpression, SourceLocation
from .type_system import ERROR, INT, STRING, NamedType, union_type

MIN_RESOLUTION_MS = 1
MAX_RESOLUTION_MS = 86_400_000
MIN_RANDOM_BYTES = 1
MAX_RANDOM_BYTES = 1 << 20
MAX_HEX_BYTES = 1024
BELOW_COST_BYTES = 8

CLOCK_ALLOW_TYPE_MESSAGE = "KS2440: caps.clock.allow() çözünürlüğü Int olmalıdır"
CLOCK_ALLOW_RANGE_MESSAGE = (
    f"KS2441: caps.clock.allow() çözünürlüğü {MIN_RESOLUTION_MS}..{MAX_RESOLUTION_MS} "
    "ms aralığında olmalıdır"
)
RANDOM_ALLOW_TYPE_MESSAGE = "KS2450: caps.random.allow() bütçesi Int olmalıdır"
RANDOM_ALLOW_RANGE_MESSAGE = (
    f"KS2451: caps.random.allow() bütçesi {MIN_RANDOM_BYTES}..{MAX_RANDOM_BYTES} "
    "bayt aralığında olmalıdır"
)
RANDOM_BUDGET_MESSAGE = (
    "KS3450: Rastgele sayı bütçesi tükendi: bu yetki en fazla {max_bytes} bayt üretebilir."
)
HEX_COUNT_MESSAGE = f"KS3451: random.hex() bayt sayısı 1..{MAX_HEX_BYTES} aralığında olmalıdır."
BELOW_BOUND_MESSAGE = "KS3451: random.below() üst sınırı en az 1 olmalıdır."

_MONOTONIC_ORIGIN_NS = time.monotonic_ns()

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_VALIDATE = None
_ORIGINAL_MEMBER = None
_ORIGINAL_METHOD_TYPE = None

_ALLOW_RULES = {
    # root type: (domain, label, minimum, maximum, shape code, range code)
    "ClockRoot": ("clock", "çözünürlüğü", MIN_RESOLUTION_MS, MAX_RESOLUTION_MS, "KS2440", "KS2441"),
    "RandomRoot": ("random", "bütçesi", MIN_RANDOM_BYTES, MAX_RANDOM_BYTES, "KS2450", "KS2451"),
}


def random_budget_message(max_bytes: int) -> str:
    return RANDOM_BUDGET_MESSAGE.format(max_bytes=max_bytes)


def _allowed_int(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _round_down(value: int, resolution: int) -> int:
    return value - value % resolution


def _random_failure() -> _runtime.KoscheiRuntimeError:
    return _runtime.KoscheiRuntimeError(
        "KS5002",
        "İşletim sisteminin güvenli rastgele kaynağı okunamadı; zayıf değer üretilmez.",
        SourceLocation(1, 1),
    )


# ---- runtime authority ------------------------------------------------------


class ClockRoot(_runtime._NarrowedCapability):
    __slots__ = ()

    def allow(self, resolution_ms: Any) -> "ClockCaps | _runtime.KsError":
        if type(resolution_ms) is not int:
            return _runtime.KsError(CLOCK_ALLOW_TYPE_MESSAGE)
        if not _allowed_int(resolution_ms, MIN_RESOLUTION_MS, MAX_RESOLUTION_MS):
            return _runtime.KsError(CLOCK_ALLOW_RANGE_MESSAGE)
        return ClockCaps(resolution_ms)


class ClockCaps(_runtime._NarrowedCapability):
    __slots__ = ("resolution_ms",)

    def __init__(self, resolution_ms: int) -> None:
        self.resolution_ms = resolution_ms

    def now_ms(self) -> int:
        return _round_down(time.time_ns() // 1_000_000, self.resolution_ms)

    def monotonic_ms(self) -> int:
        elapsed = (time.monotonic_ns() - _MONOTONIC_ORIGIN_NS) // 1_000_000
        return _round_down(elapsed, self.resolution_ms)


class RandomRoot(_runtime._NarrowedCapability):
    __slots__ = ()

    def allow(self, max_bytes: Any) -> "RandomCaps | _runtime.KsError":
        if type(max_bytes) is not int:
            return _runtime.KsError(RANDOM_ALLOW_TYPE_MESSAGE)
        if not _allowed_int(max_bytes, MIN_RANDOM_BYTES, MAX_RANDOM_BYTES):
            return _runtime.KsError(RANDOM_ALLOW_RANGE_MESSAGE)
        return RandomCaps(max_bytes)


class RandomCaps(_runtime._NarrowedCapability):
    __slots__ = ("max_bytes", "remaining")

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.remaining = max_bytes

    def _charge(self, cost: int) -> _runtime.KsError | None:
        if cost > self.remaining:
            return _runtime.KsError(random_budget_message(self.max_bytes))
        self.remaining -= cost
        return None

    def hex(self, count: Any) -> str | _runtime.KsError:
        if not _allowed_int(count, 1, MAX_HEX_BYTES):
            return _runtime.KsError(HEX_COUNT_MESSAGE)
        refused = self._charge(count)
        if refused is not None:
            return refused
        try:
            return secrets.token_hex(count)
        except OSError as error:
            raise _random_failure() from error

    def below(self, bound: Any) -> int | _runtime.KsError:
        if type(bound) is not int or bound < 1:
            return _runtime.KsError(BELOW_BOUND_MESSAGE)
        refused = self._charge(BELOW_COST_BYTES)
        if refused is not None:
            return refused
        try:
            return secrets.randbelow(bound)
        except OSError as error:
            raise _random_failure() from error


_BaseSystemCaps = _runtime.SystemCaps


class SystemCaps(_BaseSystemCaps):
    __slots__ = ("clock", "random")

    def __init__(self) -> None:
        super().__init__()
        self.clock = ClockRoot()
        self.random = RandomRoot()


_EDGES = {
    ClockRoot: {"allow"},
    ClockCaps: {"now_ms", "monotonic_ms"},
    RandomRoot: {"allow"},
    RandomCaps: {"hex", "below"},
}


def _member(self, receiver, name, location):
    # The checked-AST lane keeps a closed member allowlist; open exactly the
    # edges of these two authority graphs.
    if isinstance(receiver, SystemCaps) and name in {"clock", "random"}:
        return getattr(receiver, name)
    for receiver_type, names in _EDGES.items():
        if isinstance(receiver, receiver_type) and name in names:
            return _runtime._BoundMember(receiver, name, location)
    return _ORIGINAL_MEMBER(self, receiver, name, location)


# ---- checking ---------------------------------------------------------------


def _literal_int(arguments) -> int | None:
    if len(arguments) != 1:
        return None
    expression = arguments[0]
    if not isinstance(expression, Literal) or type(expression.value) is not int:
        return None
    return expression.value


def _check_allow(self, receiver_type, method_name, location, argument_types, arguments):
    domain, label, minimum, maximum, shape_code, range_code = _ALLOW_RULES[receiver_type]
    if method_name != "allow":
        raise _semantic.SemanticError(
            "KS2402",
            f"{receiver_type} doğrudan okuyamaz; önce caps.{domain}.allow() ile daraltın.",
            location,
        )
    values = argument_types or []
    if len(values) != 1:
        raise _semantic.SemanticError(
            shape_code,
            f"caps.{domain}.allow() 1 argüman bekler, {len(values)} verildi.",
            location,
        )
    self._require_assignable(("Int",), values[0], f"caps.{domain}.allow() {label}", location)
    value = _literal_int(arguments or [])
    if value is None:
        raise _semantic.SemanticError(
            shape_code,
            f"caps.{domain}.allow() {label} statik bir Int literal olmalıdır.",
            location,
        )
    if not minimum <= value <= maximum:
        raise _semantic.SemanticError(
            range_code,
            f"caps.{domain}.allow() {label} {minimum}..{maximum} aralığında olmalıdır; "
            f"{value} reddedildi.",
            location,
        )
    self.capability_count += 1
    return "ClockCaps" if domain == "clock" else "RandomCaps"


_OPERATIONS = {
    # capability type: {method: (argument count, legacy result type)}
    "ClockCaps": {"now_ms": (0, "Int"), "monotonic_ms": (0, "Int")},
    "RandomCaps": {"hex": (1, "String or Error"), "below": (1, "Int or Error")},
}


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type in _ALLOW_RULES:
        return _check_allow(self, receiver_type, method_name, location, argument_types, arguments)
    if receiver_type in _OPERATIONS:
        if method_name in _semantic.NARROWING_METHODS:
            raise _semantic.SemanticError(
                "KS2403",
                f"{receiver_type} daraltılmış bir yetkidir; yeniden genişletilemez.",
                location,
            )
        operation = _OPERATIONS[receiver_type].get(method_name)
        if operation is None:
            raise _semantic.SemanticError(
                "KS2404",
                f"{receiver_type} yetkisi '{method_name}' işlemine izin vermez.",
                location,
            )
        expected, result = operation
        values = argument_types or []
        if len(values) != expected:
            raise _semantic.SemanticError(
                "KS1301",
                f"{receiver_type}.{method_name}() {expected} argüman bekler, "
                f"{len(values)} verildi.",
                location,
            )
        for value in values:
            self._require_assignable(
                ("Int",), value, f"{receiver_type}.{method_name}() argümanı", location
            )
        return result

    return _ORIGINAL_CHECK_METHOD_CALL(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


_TYPED_RESULTS = {
    ("ClockCaps", "now_ms"): (0, INT),
    ("ClockCaps", "monotonic_ms"): (0, INT),
    ("RandomCaps", "hex"): (1, union_type(STRING, ERROR)),
    ("RandomCaps", "below"): (1, union_type(INT, ERROR)),
}


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType):
        typed = _TYPED_RESULTS.get((receiver.name, method))
        if typed is not None:
            expected, result = typed
            if len(arguments) != expected:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"{receiver.name}.{method}() {expected} argüman bekler, "
                    f"{len(arguments)} verildi.",
                    location,
                )
            for argument in arguments:
                _typed_ops.require_assignable(
                    INT, argument, f"{receiver.name}.{method}() argümanı", location
                )
            return result
    return _ORIGINAL_METHOD_TYPE(receiver, method, arguments, location)


def manifest_scope(domain: str, arguments) -> str:
    value = _literal_int(arguments)
    if value is None:
        return _caps.DYNAMIC
    if domain == "clock":
        return f"duvar saati + monoton saat | resolution_ms={value}"
    return f"işletim sistemi güvenli kaynağı | bytes={value}"


_RUNTIME_TYPES = (
    (ClockRoot, "ClockRoot"),
    (ClockCaps, "ClockCaps"),
    (RandomRoot, "RandomRoot"),
    (RandomCaps, "RandomCaps"),
)


def _runtime_type_node(value):
    for runtime_type, name in _RUNTIME_TYPES:
        if isinstance(value, runtime_type):
            return NamedType(name)
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _validate_capability_backend(self) -> None:
    # The legacy AST-Go backend has no clock or random runtime.
    names = {"ClockRoot", "ClockCaps", "RandomRoot", "RandomCaps"}
    for declaration in self.program.declarations:
        for parameter in declaration.parameters:
            if any(name in names for name in parameter.type_ref.names):
                raise _codegen.CodegenError(
                    "KS4001",
                    "Saat ve rastgele sayı yetkileri eski AST-Go backend'inde yok; MIR-Go kullanılır.",
                    parameter.location,
                )
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member in {
                    "clock",
                    "random",
                }:
                    raise _codegen.CodegenError(
                        "KS4001",
                        "Saat ve rastgele sayı yetkileri eski AST-Go backend'inde yok; MIR-Go kullanılır.",
                        expression.location,
                    )
    return _ORIGINAL_CODEGEN_VALIDATE(self)


def install_clock_random_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_CHECK_METHOD_CALL, _ORIGINAL_RUNTIME_TYPE_NODE
    global _ORIGINAL_CODEGEN_VALIDATE, _ORIGINAL_MEMBER, _ORIGINAL_METHOD_TYPE
    if _INSTALLED:
        return

    _runtime.ClockRoot = ClockRoot
    _runtime.ClockCaps = ClockCaps
    _runtime.RandomRoot = RandomRoot
    _runtime.RandomCaps = RandomCaps
    _runtime.SystemCaps = SystemCaps
    _mir_executor.SystemCaps = SystemCaps

    _ORIGINAL_MEMBER = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member

    _ORIGINAL_CHECK_METHOD_CALL = _semantic.SemanticChecker._check_method_call
    _semantic.SemanticChecker._check_method_call = _check_method_call

    _ORIGINAL_METHOD_TYPE = _typed_ops.method_type
    _typed_ops.method_type = _method_type
    _typed_expr.method_type = _method_type

    _ORIGINAL_RUNTIME_TYPE_NODE = _alignment._runtime_type_node
    _alignment._runtime_type_node = _runtime_type_node

    _ORIGINAL_CODEGEN_VALIDATE = _codegen.GoCodegen._validate_capability_backend
    _codegen.GoCodegen._validate_capability_backend = _validate_capability_backend

    _INSTALLED = True


__all__ = [
    "BELOW_BOUND_MESSAGE",
    "BELOW_COST_BYTES",
    "CLOCK_ALLOW_RANGE_MESSAGE",
    "CLOCK_ALLOW_TYPE_MESSAGE",
    "HEX_COUNT_MESSAGE",
    "MAX_HEX_BYTES",
    "MAX_RANDOM_BYTES",
    "MAX_RESOLUTION_MS",
    "MIN_RANDOM_BYTES",
    "MIN_RESOLUTION_MS",
    "RANDOM_ALLOW_RANGE_MESSAGE",
    "RANDOM_ALLOW_TYPE_MESSAGE",
    "RANDOM_BUDGET_MESSAGE",
    "ClockCaps",
    "ClockRoot",
    "RandomCaps",
    "RandomRoot",
    "install_clock_random_v1",
    "manifest_scope",
    "random_budget_message",
]

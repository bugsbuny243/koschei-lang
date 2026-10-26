"""Program input authority v1: command-line arguments and standard input.

A program reads what its invoker hands it only through a narrowed capability::

    fn main(caps: SystemCaps) {
        let input = caps.input.allow(65536)
        let args = input.args() or return
        let text = input.read_text() or return
    }

``caps.input.allow(max_bytes)`` takes one static Int literal between 1 and
``MAX_INPUT_BYTES``; ``ks caps`` shows it. ``InputCaps`` has two operations:

* ``args()`` returns the arguments after the program path as
  ``List<String> or Error``. An argument that is not valid UTF-8 is a KS3430
  Error value, never a silently replaced text.
* ``read_text()`` reads standard input to its end as ``String or Error``. More
  than ``max_bytes`` bytes is KS3431, bytes that are not UTF-8 are KS3430 and
  a read the operating system fails is KS3432. A closed standard input reads
  as empty. The bytes read are not given back, so a second call continues
  where the first stopped (after the end: ``""``).

Program input reaches no resource of its own: argv and stdin are data the
invoker already chose to give the process, which is why native binaries may
carry this capability while disk, network and environment stay blocked
(KS4004) until the native capability broker exists.
"""

from __future__ import annotations

from contextvars import ContextVar
import os
import sys
from typing import Any

from . import capabilities as _caps
from . import codegen_go as _codegen
from . import interpreter as _runtime
from . import mir_executor_v1 as _mir_executor
from . import runtime_alignment as _alignment
from . import semantic as _semantic
from . import _typed_expr
from . import _typed_ops
from .ast_nodes import Literal, MemberExpression
from .type_system import ERROR, STRING, NamedType, generic, union_type
from .value_budget_v1 import LIST_MESSAGE, MAX_LIST_ITEMS, MAX_STRING_BYTES, STRING_MESSAGE

MIN_INPUT_BYTES = 1
MAX_INPUT_BYTES = MAX_STRING_BYTES

# Error values, identical in every executor and in MIR-Go binaries.
NOT_TEXT_MESSAGE = "KS3430: Standart girdi geçerli UTF-8 metin değil."
BUDGET_MESSAGE = (
    "KS3431: Standart girdi bütçesi aşıldı: en fazla {max_bytes} bayt okunabilir."
)
UNAVAILABLE_MESSAGE = "KS3432: Standart girdi okunamadı."
ARGUMENT_MESSAGE = "KS3430: {index}. program argümanı geçerli UTF-8 metin değil."
ALLOW_TYPE_MESSAGE = "KS2430: caps.input.allow() bütçesi Int olmalıdır"
ALLOW_RANGE_MESSAGE = (
    f"KS2431: caps.input.allow() bütçesi {MIN_INPUT_BYTES}..{MAX_INPUT_BYTES} "
    "aralığında olmalıdır"
)

_INSTALLED = False
_ORIGINAL_CHECK_METHOD_CALL = None
_ORIGINAL_RUNTIME_TYPE_NODE = None
_ORIGINAL_CODEGEN_VALIDATE = None
_ORIGINAL_MEMBER = None
_ORIGINAL_EXECUTE_MAIN = None
_ORIGINAL_MIR_EXECUTE_MAIN = None
_ORIGINAL_METHOD_TYPE = None

# The arguments of the program being run. Each executor binds its own argv for
# the duration of `main`, so nested or concurrent runs never see each other's.
_PROGRAM_ARGUMENTS: ContextVar[tuple[str, ...]] = ContextVar(
    "koschei_program_arguments", default=()
)


def budget_message(max_bytes: int) -> str:
    return BUDGET_MESSAGE.format(max_bytes=max_bytes)


def _budget_error(max_bytes: Any) -> str | None:
    if type(max_bytes) is not int:
        return ALLOW_TYPE_MESSAGE
    if not MIN_INPUT_BYTES <= max_bytes <= MAX_INPUT_BYTES:
        return ALLOW_RANGE_MESSAGE
    return None


def program_arguments(raw: tuple[str, ...]) -> list[str] | _runtime.KsError:
    """Return the arguments as texts, or the Error value for the first non-text one."""

    if len(raw) > MAX_LIST_ITEMS:
        return _runtime.KsError(LIST_MESSAGE)
    texts: list[str] = []
    for index, argument in enumerate(raw, start=1):
        try:
            # os.fsencode recovers the bytes the operating system passed (Python
            # decodes argv with surrogateescape); only real UTF-8 is text.
            text = os.fsencode(argument).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return _runtime.KsError(ARGUMENT_MESSAGE.format(index=index))
        if len(text.encode("utf-8")) > MAX_STRING_BYTES:
            return _runtime.KsError(STRING_MESSAGE)
        texts.append(text)
    return texts


def read_standard_input(max_bytes: int) -> str | _runtime.KsError:
    """Read standard input to its end, at most ``max_bytes`` bytes of UTF-8."""

    data = read_standard_bytes(max_bytes)
    if isinstance(data, _runtime.KsError):
        return data
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        return _runtime.KsError(NOT_TEXT_MESSAGE)


def read_standard_bytes(max_bytes: int) -> "_runtime.Bytes | _runtime.KsError":
    """Read standard input to its end, at most ``max_bytes`` bytes."""

    if sys.stdin is None:
        # Python leaves sys.stdin unset when the process started with fd 0
        # closed. The Go runtime reopens a closed standard descriptor on
        # /dev/null, so in both executors a closed input is an empty one.
        return _runtime.Bytes()
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        return _runtime.KsError(UNAVAILABLE_MESSAGE)
    try:
        data = stream.read(max_bytes + 1)
    except (OSError, ValueError):
        return _runtime.KsError(UNAVAILABLE_MESSAGE)
    if data is None:
        return _runtime.KsError(UNAVAILABLE_MESSAGE)
    if len(data) > max_bytes:
        return _runtime.KsError(budget_message(max_bytes))
    return _runtime.Bytes(data)


# ---- runtime authority ------------------------------------------------------


class InputRoot(_runtime._NarrowedCapability):
    __slots__ = ("_arguments",)

    def __init__(self, arguments: tuple[str, ...] = ()) -> None:
        self._arguments = tuple(arguments)

    def allow(self, max_bytes: Any) -> "InputCaps | _runtime.KsError":
        error = _budget_error(max_bytes)
        if error is not None:
            return _runtime.KsError(error)
        return InputCaps(self._arguments, max_bytes)


class InputCaps(_runtime._NarrowedCapability):
    __slots__ = ("_arguments", "max_bytes")

    def __init__(self, arguments: tuple[str, ...], max_bytes: int) -> None:
        self._arguments = arguments
        self.max_bytes = max_bytes

    def args(self) -> list[str] | _runtime.KsError:
        return program_arguments(self._arguments)

    def read_text(self) -> str | _runtime.KsError:
        return read_standard_input(self.max_bytes)

    def read_bytes(self) -> "_runtime.Bytes | _runtime.KsError":
        return read_standard_bytes(self.max_bytes)


_BaseSystemCaps = _runtime.SystemCaps


class SystemCaps(_BaseSystemCaps):
    __slots__ = ("input",)

    def __init__(self) -> None:
        super().__init__()
        self.input = InputRoot(_PROGRAM_ARGUMENTS.get())


def _member(self, receiver, name, location):
    # The checked-AST lane keeps a closed member allowlist; open exactly the
    # four edges of this authority graph.
    if isinstance(receiver, SystemCaps) and name == "input":
        return receiver.input
    if isinstance(receiver, InputRoot) and name == "allow":
        return _runtime._BoundMember(receiver, name, location)
    if isinstance(receiver, InputCaps) and name in {"args", "read_text", "read_bytes"}:
        return _runtime._BoundMember(receiver, name, location)
    return _ORIGINAL_MEMBER(self, receiver, name, location)


def _execute_main(self):
    token = _PROGRAM_ARGUMENTS.set(tuple(self.argv))
    try:
        return _ORIGINAL_EXECUTE_MAIN(self)
    finally:
        _PROGRAM_ARGUMENTS.reset(token)


def _mir_execute_main(self):
    token = _PROGRAM_ARGUMENTS.set(tuple(self.argv))
    try:
        return _ORIGINAL_MIR_EXECUTE_MAIN(self)
    finally:
        _PROGRAM_ARGUMENTS.reset(token)


# ---- checking ---------------------------------------------------------------


def _literal_budget(arguments) -> int | None:
    if len(arguments) != 1:
        return None
    expression = arguments[0]
    if not isinstance(expression, Literal) or type(expression.value) is not int:
        return None
    return expression.value


def _check_method_call(
    self,
    receiver_type,
    method_name,
    location,
    argument_types=None,
    arguments=None,
):
    if receiver_type == "InputRoot":
        if method_name != "allow":
            raise _semantic.SemanticError(
                "KS2402",
                "InputRoot doğrudan girdi okuyamaz; önce bir bayt bütçesiyle allow kullanın.",
                location,
            )
        values = argument_types or []
        if len(values) != 1:
            raise _semantic.SemanticError(
                "KS2430",
                f"caps.input.allow() 1 argüman bekler, {len(values)} verildi.",
                location,
            )
        self._require_assignable(("Int",), values[0], "Program girdisi bütçesi", location)
        budget = _literal_budget(arguments or [])
        if budget is None:
            raise _semantic.SemanticError(
                "KS2430",
                "caps.input.allow() bütçesi statik bir Int literal olmalıdır.",
                location,
            )
        if not MIN_INPUT_BYTES <= budget <= MAX_INPUT_BYTES:
            raise _semantic.SemanticError(
                "KS2431",
                f"caps.input.allow() bütçesi {MIN_INPUT_BYTES}..{MAX_INPUT_BYTES} "
                f"aralığında olmalıdır; {budget} reddedildi.",
                location,
            )
        self.capability_count += 1
        return "InputCaps"

    if receiver_type == "InputCaps":
        if method_name in _semantic.NARROWING_METHODS:
            raise _semantic.SemanticError(
                "KS2403",
                "InputCaps daraltılmış bir yetkidir; yeniden genişletilemez.",
                location,
            )
        if method_name not in {"args", "read_text", "read_bytes"}:
            raise _semantic.SemanticError(
                "KS2404",
                f"InputCaps yetkisi '{method_name}' işlemine izin vermez.",
                location,
            )
        values = argument_types or []
        if values:
            raise _semantic.SemanticError(
                "KS1301",
                f"InputCaps.{method_name}() 0 argüman bekler, {len(values)} verildi.",
                location,
            )
        return {
            "args": "List or Error",
            "read_text": "String or Error",
            "read_bytes": "Bytes or Error",
        }[method_name]

    return _ORIGINAL_CHECK_METHOD_CALL(
        self,
        receiver_type,
        method_name,
        location,
        argument_types,
        arguments,
    )


def _method_type(receiver, method, arguments, location):
    if isinstance(receiver, NamedType) and receiver.name == "InputCaps":
        if method in {"args", "read_text", "read_bytes"}:
            if arguments:
                raise _semantic.SemanticError(
                    "KS1301",
                    f"InputCaps.{method}() 0 argüman bekler, {len(arguments)} verildi.",
                    location,
                )
            if method == "args":
                return union_type(generic("List", STRING), ERROR)
            if method == "read_bytes":
                return union_type(NamedType("Bytes"), ERROR)
            return union_type(STRING, ERROR)
    return _ORIGINAL_METHOD_TYPE(receiver, method, arguments, location)


def manifest_scope(arguments) -> str:
    budget = _literal_budget(arguments)
    if budget is None:
        return _caps.DYNAMIC
    return f"argümanlar + standart girdi | stdin_bytes={budget}"


def _runtime_type_node(value):
    if isinstance(value, InputRoot):
        return NamedType("InputRoot")
    if isinstance(value, InputCaps):
        return NamedType("InputCaps")
    return _ORIGINAL_RUNTIME_TYPE_NODE(value)


def _validate_capability_backend(self) -> None:
    # The legacy AST-Go backend has no program input runtime; it must never
    # emit a binary that silently reads nothing.
    for declaration in self.program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"InputRoot", "InputCaps"} for name in parameter.type_ref.names):
                raise _codegen.CodegenError(
                    "KS4001",
                    "Program girdisi yetkisi eski AST-Go backend'inde yok; MIR-Go kullanılır.",
                    parameter.location,
                )
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member == "input":
                    raise _codegen.CodegenError(
                        "KS4001",
                        "Program girdisi yetkisi eski AST-Go backend'inde yok; MIR-Go kullanılır.",
                        expression.location,
                    )
    return _ORIGINAL_CODEGEN_VALIDATE(self)


def install_program_input_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_CHECK_METHOD_CALL
    global _ORIGINAL_RUNTIME_TYPE_NODE, _ORIGINAL_CODEGEN_VALIDATE, _ORIGINAL_MEMBER
    global _ORIGINAL_EXECUTE_MAIN, _ORIGINAL_MIR_EXECUTE_MAIN, _ORIGINAL_METHOD_TYPE
    if _INSTALLED:
        return

    # The canonical contract, semantic.py and capabilities.py name the domain
    # statically; the runtime classes bind it here.
    _runtime.InputRoot = InputRoot
    _runtime.InputCaps = InputCaps
    _runtime.SystemCaps = SystemCaps
    _mir_executor.SystemCaps = SystemCaps

    _ORIGINAL_MEMBER = _runtime.Interpreter._member
    _runtime.Interpreter._member = _member
    _ORIGINAL_EXECUTE_MAIN = _runtime.Interpreter._execute_main
    _runtime.Interpreter._execute_main = _execute_main
    _ORIGINAL_MIR_EXECUTE_MAIN = _mir_executor.MirExecutorV1.execute_main
    _mir_executor.MirExecutorV1.execute_main = _mir_execute_main

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
    "ALLOW_RANGE_MESSAGE",
    "ALLOW_TYPE_MESSAGE",
    "ARGUMENT_MESSAGE",
    "BUDGET_MESSAGE",
    "MAX_INPUT_BYTES",
    "MIN_INPUT_BYTES",
    "NOT_TEXT_MESSAGE",
    "UNAVAILABLE_MESSAGE",
    "InputCaps",
    "InputRoot",
    "budget_message",
    "install_program_input_v1",
    "manifest_scope",
    "program_arguments",
    "read_standard_input",
]

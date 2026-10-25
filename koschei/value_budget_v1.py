"""Titan: the value size budget of Koschei programs v1.

No String may hold more than ``MAX_STRING_BYTES`` bytes of UTF-8 and no List
more than ``MAX_LIST_ITEMS`` items. An operation that would build a larger
value produces a ``KS3502`` Error value instead, the same way Int overflow
produces ``KS3501``: the Error flows, arithmetic propagates it and the ``or``
forms catch it. Every executor stops at the same operation with the same
message: the checked-AST interpreter, the canonical MIR executor, the direct
MIR runtime and MIR-Go binaries (``mir_go_runtime_v2``).

Operations that could turn a small input into a large value check before they
build anything: ``String.join`` (a long separator repeated between many
items), ``String.split`` (many pieces from one String) and ``List.push``.
String ``+`` and interpolation check their result; their transient size is
bounded by values that already exist.

Values that enter from outside obey the same bound: ``disk.read`` reads at
most one character past the budget and returns ``KS3502`` for a larger file.
HTTP responses already have a smaller bound (``http_response_budget_v1``).

The bound applies to each value. Total live memory is still bounded only by
the host: ``ks run`` reports host memory exhaustion as a ``KS3502`` runtime
stop instead of a Python traceback.

This module imports no runtime at load time, so the runtimes can use its
constants; ``install_value_budget_v1`` imports them when it runs.
"""

from __future__ import annotations

from typing import Any

CODE = "KS3502"
MAX_STRING_BYTES = 1 << 24
MAX_LIST_ITEMS = 1 << 20
STRING_MESSAGE = (
    f"{CODE}: Bellek bütçesi aşıldı: bir String en fazla {MAX_STRING_BYTES} "
    "bayt UTF-8 olabilir."
)
LIST_MESSAGE = (
    f"{CODE}: Bellek bütçesi aşıldı: bir List en fazla {MAX_LIST_ITEMS} öğe olabilir."
)
HOST_MESSAGE = (
    "Bellek bütçesi tükendi: host belleği programın değerlerine yetmedi; "
    "program durduruldu."
)

_INSTALLED = False


def _utf8_bytes(text: str) -> int:
    return len(text) if text.isascii() else len(text.encode("utf-8"))


def fits_texts(texts: list[str], extra_chars: int = 0, extra_bytes: int = 0) -> bool:
    """Whether the concatenation of ``texts`` stays within the String budget.

    A code point takes at most four UTF-8 bytes, so most inputs are decided
    from character counts without encoding anything.
    """

    if (sum(len(text) for text in texts) + extra_chars) * 4 <= MAX_STRING_BYTES:
        return True
    return sum(_utf8_bytes(text) for text in texts) + extra_bytes <= MAX_STRING_BYTES


def join_fits(separator: str, items: list[str]) -> bool:
    gaps = max(len(items) - 1, 0)
    return fits_texts(
        items,
        extra_chars=len(separator) * gaps,
        extra_bytes=_utf8_bytes(separator) * gaps,
    )


def split_fits(receiver: str, separator: str) -> bool:
    return receiver.count(separator) + 1 <= MAX_LIST_ITEMS


def oversize_message(value: Any) -> str | None:
    """The KS3502 message for a String or List value over budget, if any."""

    if isinstance(value, str):
        return None if fits_texts([value]) else STRING_MESSAGE
    if isinstance(value, (list, tuple)) and len(value) > MAX_LIST_ITEMS:
        return LIST_MESSAGE
    return None


# ---- checked-AST interpreter and canonical MIR executor -------------------


def _budget(value: Any) -> Any:
    from .interpreter import KsError

    message = oversize_message(value)
    return value if message is None else KsError(message)


def _member_precheck(member: Any, arguments: list[Any]) -> str | None:
    receiver = member.receiver
    name = member.name
    if isinstance(receiver, str) and len(arguments) == 1:
        argument = arguments[0]
        if name == "join" and isinstance(argument, list):
            if all(isinstance(item, str) for item in argument) and not join_fits(
                receiver, argument
            ):
                return STRING_MESSAGE
        if name == "split" and isinstance(argument, str) and argument:
            if not split_fits(receiver, argument):
                return LIST_MESSAGE
    if isinstance(receiver, list) and name == "push" and len(arguments) == 1:
        if len(receiver) + 1 > MAX_LIST_ITEMS:
            return LIST_MESSAGE
    return None


def install_value_budget_v1() -> None:
    """Install the member and host-memory parts of the budget.

    String ``+`` and interpolation are checked inline in each executor
    (``interpreter``, ``runtime_alignment``, ``mir_executor_v1``,
    ``mir_native_runtime``, ``mir_go_runtime_v2``). Members are wrapped here,
    after the other runtime installers, so the check sees their final
    behavior instead of an intermediate layer.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from . import interpreter as _runtime
    from . import runtime_budget

    # The canonical MIR executor reaches String/List members through the
    # runtime primitive facade, which delegates to this method.
    original_member = _runtime.Interpreter._invoke_member

    def interpreter_member(self, member, arguments):
        message = _member_precheck(member, arguments)
        if message is not None:
            return _runtime.KsError(message)
        return _budget(original_member(self, member, arguments))

    _runtime.Interpreter._invoke_member = interpreter_member

    original_run = runtime_budget.run_mir_with_budget

    def run_mir_with_budget(mir_graph, argv=None, **budgets):
        try:
            return original_run(mir_graph, argv, **budgets)
        except MemoryError:
            # The failing frames are gone by now, so reporting needs no memory
            # from the exhausted program.
            raise host_memory_error() from None

    runtime_budget.run_mir_with_budget = run_mir_with_budget
    _INSTALLED = True


def host_memory_error():
    """The runtime stop `ks run` reports when the host runs out of memory."""

    from .ast_nodes import SourceLocation
    from .interpreter import KoscheiRuntimeError

    return KoscheiRuntimeError(CODE, HOST_MESSAGE, SourceLocation(1, 1))


__all__ = [
    "CODE",
    "LIST_MESSAGE",
    "MAX_LIST_ITEMS",
    "MAX_STRING_BYTES",
    "STRING_MESSAGE",
    "host_memory_error",
    "install_value_budget_v1",
    "join_fits",
    "oversize_message",
    "split_fits",
]

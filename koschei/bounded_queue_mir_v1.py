"""Direct-MIR adapter for bounded queue/backpressure primitives."""

from __future__ import annotations

from . import mir_native_runtime as _mir
from . import runtime_alignment as _alignment
from .bounded_queue import BoundedQueueError, BoundedQueueValue
from .type_system import render_type

_BUILTINS = frozenset(
    {
        "bounded_queue",
        "queue_try_send",
        "queue_try_recv",
        "queue_len",
        "queue_capacity",
    }
)
_INSTALLED = False
_ORIGINAL_INVOKE = None
_ORIGINAL_TO_STRING = None


def _invoke(self, callee, arguments):
    if not (isinstance(callee, _mir._BuiltinRef) and callee.name in _BUILTINS):
        return _ORIGINAL_INVOKE(self, callee, arguments)

    expected = {
        "bounded_queue": 2,
        "queue_try_send": 2,
        "queue_try_recv": 1,
        "queue_len": 1,
        "queue_capacity": 1,
    }[callee.name]
    if len(arguments) != expected:
        raise _mir.MirNativeRuntimeError(
            f"{callee.name} expects {expected} arguments"
        )

    if callee.name == "bounded_queue":
        capacity, witness = arguments
        try:
            return BoundedQueueValue(capacity, _alignment._runtime_type_node(witness))
        except BoundedQueueError as error:
            return _mir._ErrorValue(str(error))

    queue = arguments[0]
    if not isinstance(queue, BoundedQueueValue):
        return _mir._ErrorValue(f"KS3902: {callee.name} expects BoundedQueue")
    if callee.name == "queue_try_send":
        value = arguments[1]
        if not _alignment._matches_node(value, queue.item_type):
            return _mir._ErrorValue(
                "KS3904: bounded-queue runtime item type mismatch: expected "
                + render_type(queue.item_type)
            )
        return queue.try_send(value)
    if callee.name == "queue_try_recv":
        ok, value = queue.try_recv()
        return value if ok else _mir._ErrorValue("KS3903: bounded queue is empty")
    if callee.name == "queue_len":
        return queue.length
    return queue.capacity


def _to_string(value):
    if isinstance(value, BoundedQueueValue):
        return str(value)
    return _ORIGINAL_TO_STRING(value)


def install_bounded_queue_mir_v1() -> None:
    global _INSTALLED, _ORIGINAL_INVOKE, _ORIGINAL_TO_STRING
    if _INSTALLED:
        return
    _mir._BUILTINS = frozenset(set(_mir._BUILTINS) | set(_BUILTINS))
    _ORIGINAL_INVOKE = _mir._MirExecutor._invoke
    _mir._MirExecutor._invoke = _invoke
    _ORIGINAL_TO_STRING = _mir._to_string
    _mir._to_string = _to_string
    _INSTALLED = True

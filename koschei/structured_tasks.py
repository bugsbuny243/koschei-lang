"""Deterministic cooperative task-scope storage for Koschei.

Task Scope v1 is deliberately not a thread pool. Spawn records work in fixed
storage; join executes every recorded child in spawn order and closes the scope.
No child begins background execution before join, so dropping an unjoined scope
cannot leave a detached running task behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_TASK_CAPACITY = 1
MAX_TASK_CAPACITY = 4096
TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"


class StructuredTaskError(ValueError):
    pass


@dataclass(slots=True)
class TaskRecord:
    worker: Any
    argument: Any
    state: str = TASK_PENDING
    failure: Any = None


class TaskScopeValue:
    """One fixed-size structured task scope."""

    __slots__ = (
        "capacity",
        "_slots",
        "_count",
        "_terminal",
        "closed",
        "join_result",
    )

    def __init__(self, capacity: int) -> None:
        if type(capacity) is not int:
            raise StructuredTaskError("KS3911: task scope capacity must be Int")
        if not MIN_TASK_CAPACITY <= capacity <= MAX_TASK_CAPACITY:
            raise StructuredTaskError(
                "KS3911: task scope capacity must be between "
                f"{MIN_TASK_CAPACITY} and {MAX_TASK_CAPACITY}"
            )
        self.capacity = capacity
        self._slots: list[TaskRecord | None] = [None] * capacity
        self._count = 0
        self._terminal = 0
        self.closed = False
        self.join_result: Any = None

    @property
    def count(self) -> int:
        return self._count

    @property
    def pending(self) -> int:
        return self._count - self._terminal

    def spawn(self, worker: Any, argument: Any) -> int:
        if self.closed:
            raise StructuredTaskError("KS3913: task scope is already closed")
        if self._count >= self.capacity:
            raise StructuredTaskError("KS3912: task scope capacity is exhausted")
        task_id = self._count
        self._slots[task_id] = TaskRecord(worker=worker, argument=argument)
        self._count += 1
        return task_id

    def records(self) -> tuple[TaskRecord, ...]:
        result: list[TaskRecord] = []
        for index in range(self._count):
            record = self._slots[index]
            if record is None:
                raise StructuredTaskError(
                    "KS3915: task scope contains an impossible empty occupied slot"
                )
            result.append(record)
        return tuple(result)

    def mark_terminal(self, record: TaskRecord, failure: Any = None) -> None:
        record.failure = failure
        record.state = TASK_FAILED if failure is not None else TASK_DONE
        self._terminal += 1

    def __str__(self) -> str:
        return (
            "TaskScope("
            f"tasks={self._count}, pending={self.pending}, "
            f"capacity={self.capacity}, closed={'true' if self.closed else 'false'}"
            ")"
        )

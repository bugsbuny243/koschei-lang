"""Fixed-capacity FIFO storage for Koschei backpressure primitives."""

from __future__ import annotations

import threading
from typing import Any

MIN_QUEUE_CAPACITY = 1
MAX_QUEUE_CAPACITY = 65_536


class BoundedQueueError(ValueError):
    pass


class BoundedQueueValue:
    """A physically bounded, race-safe ring buffer.

    The buffer is allocated exactly once at construction. Enqueue never grows an
    underlying Python list and dequeue clears the released slot so references do
    not stay live for the lifetime of the queue. Every mutable ring-state access
    is serialized by the queue-owned lock; immutable capacity/item_type may be
    read without it.
    """

    __slots__ = (
        "capacity",
        "item_type",
        "_buffer",
        "_head",
        "_tail",
        "_count",
        "_lock",
    )

    def __init__(self, capacity: int, item_type: Any) -> None:
        if type(capacity) is not int:
            raise BoundedQueueError("KS3901: queue capacity must be Int")
        if not MIN_QUEUE_CAPACITY <= capacity <= MAX_QUEUE_CAPACITY:
            raise BoundedQueueError(
                "KS3901: queue capacity must be between "
                f"{MIN_QUEUE_CAPACITY} and {MAX_QUEUE_CAPACITY}"
            )
        self.capacity = capacity
        self.item_type = item_type
        self._buffer: list[Any | None] = [None] * capacity
        self._head = 0
        self._tail = 0
        self._count = 0
        self._lock = threading.Lock()

    @property
    def length(self) -> int:
        with self._lock:
            return self._count

    @property
    def is_full(self) -> bool:
        with self._lock:
            return self._count == self.capacity

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return self._count == 0

    def try_send(self, value: Any) -> bool:
        with self._lock:
            if self._count == self.capacity:
                return False
            self._buffer[self._tail] = value
            self._tail = (self._tail + 1) % self.capacity
            self._count += 1
            return True

    def try_recv(self) -> tuple[bool, Any]:
        with self._lock:
            if self._count == 0:
                return False, None
            value = self._buffer[self._head]
            self._buffer[self._head] = None
            self._head = (self._head + 1) % self.capacity
            self._count -= 1
            return True, value

    def snapshot_items(self) -> tuple[Any, ...]:
        """Return the currently occupied FIFO items under one lock acquisition."""

        with self._lock:
            return tuple(
                self._buffer[(self._head + offset) % self.capacity]
                for offset in range(self._count)
            )

    def __str__(self) -> str:
        with self._lock:
            return f"BoundedQueue(len={self._count}, capacity={self.capacity})"

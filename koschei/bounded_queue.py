"""Fixed-capacity FIFO storage for Koschei backpressure primitives."""

from __future__ import annotations

from typing import Any

MIN_QUEUE_CAPACITY = 1
MAX_QUEUE_CAPACITY = 65_536


class BoundedQueueError(ValueError):
    pass


class BoundedQueueValue:
    """A physically bounded ring buffer.

    The buffer is allocated exactly once at construction. Enqueue never grows an
    underlying Python list and dequeue clears the released slot so references do
    not stay live for the lifetime of the queue.
    """

    __slots__ = ("capacity", "item_type", "_buffer", "_head", "_tail", "_count")

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

    @property
    def length(self) -> int:
        return self._count

    @property
    def is_full(self) -> bool:
        return self._count == self.capacity

    @property
    def is_empty(self) -> bool:
        return self._count == 0

    def try_send(self, value: Any) -> bool:
        if self._count == self.capacity:
            return False
        self._buffer[self._tail] = value
        self._tail = (self._tail + 1) % self.capacity
        self._count += 1
        return True

    def try_recv(self) -> tuple[bool, Any]:
        if self._count == 0:
            return False, None
        value = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) % self.capacity
        self._count -= 1
        return True, value

    def __str__(self) -> str:
        return f"BoundedQueue(len={self._count}, capacity={self.capacity})"

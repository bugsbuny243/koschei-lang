"""Bounded immutable collection primitives for Koschei stdlib v1.

These helpers are deliberately pure and authority-free. They enforce explicit
work/item budgets so collection operations cannot become unbounded ambient
resource sinks.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, Iterator, Mapping, TypeVar

T = TypeVar("T")
U = TypeVar("U")
K = TypeVar("K")
V = TypeVar("V")

class CollectionBudgetError(ValueError): pass

@dataclass(frozen=True, slots=True)
class CollectionBudgetV1:
    max_items: int = 10000
    max_work: int = 100000
    def __post_init__(self) -> None:
        if self.max_items < 0 or self.max_work < 0:
            raise CollectionBudgetError("collection budgets must be non-negative")

@dataclass(frozen=True, slots=True)
class KList(Generic[T]):
    _items: tuple[T, ...]

    @classmethod
    def from_iterable(cls, values: Iterable[T], *, budget: CollectionBudgetV1) -> "KList[T]":
        items = tuple(values)
        if len(items) > budget.max_items:
            raise CollectionBudgetError("item budget exceeded")
        return cls(items)

    def __iter__(self) -> Iterator[T]: return iter(self._items)
    def __len__(self) -> int: return len(self._items)
    def get(self, index: int) -> T | None:
        return self._items[index] if 0 <= index < len(self._items) else None
    def push(self, value: T, *, budget: CollectionBudgetV1) -> "KList[T]":
        if len(self._items) + 1 > budget.max_items:
            raise CollectionBudgetError("item budget exceeded")
        return KList(self._items + (value,))
    def take(self, count: int) -> "KList[T]":
        return KList(self._items[:max(0, count)])
    def drop(self, count: int) -> "KList[T]":
        return KList(self._items[max(0, count):])
    def concat(self, other: "KList[T]", *, budget: CollectionBudgetV1) -> "KList[T]":
        if len(self._items) + len(other._items) > budget.max_items:
            raise CollectionBudgetError("item budget exceeded")
        return KList(self._items + other._items)
    def map(self, fn: Callable[[T], U], *, budget: CollectionBudgetV1) -> "KList[U]":
        if len(self._items) > budget.max_work:
            raise CollectionBudgetError("work budget exceeded")
        return KList(tuple(fn(v) for v in self._items))
    def filter(self, fn: Callable[[T], bool], *, budget: CollectionBudgetV1) -> "KList[T]":
        if len(self._items) > budget.max_work:
            raise CollectionBudgetError("work budget exceeded")
        out = tuple(v for v in self._items if fn(v))
        if len(out) > budget.max_items:
            raise CollectionBudgetError("item budget exceeded")
        return KList(out)
    def fold(self, initial: U, fn: Callable[[U, T], U], *, budget: CollectionBudgetV1) -> U:
        if len(self._items) > budget.max_work:
            raise CollectionBudgetError("work budget exceeded")
        acc = initial
        for v in self._items: acc = fn(acc, v)
        return acc

@dataclass(frozen=True, slots=True)
class KMap(Generic[K,V]):
    _entries: tuple[tuple[K,V], ...]

    @classmethod
    def from_mapping(cls, values: Mapping[K,V], *, budget: CollectionBudgetV1) -> "KMap[K,V]":
        if len(values) > budget.max_items:
            raise CollectionBudgetError("entry budget exceeded")
        return cls(tuple(values.items()))

    def __len__(self) -> int: return len(self._entries)
    def get(self, key: K) -> V | None:
        for k,v in self._entries:
            if k == key: return v
        return None
    def contains(self, key: K) -> bool:
        return any(k == key for k,_ in self._entries)
    def set(self, key: K, value: V, *, budget: CollectionBudgetV1) -> "KMap[K,V]":
        out = []
        replaced = False
        for k,v in self._entries:
            if k == key:
                out.append((key,value)); replaced = True
            else: out.append((k,v))
        if not replaced: out.append((key,value))
        if len(out) > budget.max_items:
            raise CollectionBudgetError("entry budget exceeded")
        return KMap(tuple(out))
    def remove(self, key: K) -> "KMap[K,V]":
        return KMap(tuple((k,v) for k,v in self._entries if k != key))
    def keys(self) -> KList[K]: return KList(tuple(k for k,_ in self._entries))
    def values(self) -> KList[V]: return KList(tuple(v for _,v in self._entries))
    def entries(self) -> KList[tuple[K,V]]: return KList(self._entries)

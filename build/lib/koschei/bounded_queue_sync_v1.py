"""Race-free synchronization bridge for BoundedQueue v1.

The queue ABI is installed before structured tasks. This layer is deliberately
late-bound so the existing public ABI does not change: it hardens the Python
ring buffer through ``BoundedQueueValue`` itself and rewrites the generated Go
queue storage to use a queue-owned ``sync.Mutex``. Any runtime layout drift fails
closed instead of silently emitting an unsynchronized queue.
"""

from __future__ import annotations

from . import codegen_go as _codegen

_INSTALLED = False
_ORIGINAL_GENERATE = None


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"BoundedQueue Go {label} layout changed; sync patch failed closed.")
    return text.replace(old, new, 1)


def _patch_runtime_prelude() -> None:
    prelude = _codegen.RUNTIME_PRELUDE

    prelude = _replace_once(
        prelude,
        "type KsBoundedQueue struct {\n\tCapacity int64\n",
        "type KsBoundedQueue struct {\n\tMu sync.Mutex\n\tCapacity int64\n",
        "struct",
    )

    prelude = _replace_once(
        prelude,
        '''func (q *KsBoundedQueue) String() string {
\treturn fmt.Sprintf("BoundedQueue(len=%d, capacity=%d)", q.Count, q.Capacity)
}
''',
        '''func (q *KsBoundedQueue) String() string {
\tq.Mu.Lock()
\tdefer q.Mu.Unlock()
\treturn fmt.Sprintf("BoundedQueue(len=%d, capacity=%d)", q.Count, q.Capacity)
}
''',
        "String",
    )

    prelude = _replace_once(
        prelude,
        '''\tif ksQueueTypeTag(value) != queue.ItemTag {
\t\treturn ksErrorf("KS3904: bounded-queue runtime item type mismatch")
\t}
\tif queue.Count == queue.Capacity {
''',
        '''\tif ksQueueTypeTag(value) != queue.ItemTag {
\t\treturn ksErrorf("KS3904: bounded-queue runtime item type mismatch")
\t}
\tqueue.Mu.Lock()
\tdefer queue.Mu.Unlock()
\tif queue.Count == queue.Capacity {
''',
        "send",
    )

    prelude = _replace_once(
        prelude,
        '''\tif !ok {
\t\treturn ksErrorf("KS3902: queue_try_recv expects BoundedQueue")
\t}
\tif queue.Count == 0 {
''',
        '''\tif !ok {
\t\treturn ksErrorf("KS3902: queue_try_recv expects BoundedQueue")
\t}
\tqueue.Mu.Lock()
\tdefer queue.Mu.Unlock()
\tif queue.Count == 0 {
''',
        "receive",
    )

    prelude = _replace_once(
        prelude,
        '''\tif !ok {
\t\treturn ksErrorf("KS3902: queue_len expects BoundedQueue")
\t}
\treturn queue.Count
''',
        '''\tif !ok {
\t\treturn ksErrorf("KS3902: queue_len expects BoundedQueue")
\t}
\tqueue.Mu.Lock()
\tdefer queue.Mu.Unlock()
\treturn queue.Count
''',
        "length",
    )

    _codegen.RUNTIME_PRELUDE = prelude


def _generate_with_sync_import(self) -> str:
    source = _ORIGINAL_GENERATE(self)
    if '\t"sync"\n' in source:
        return source
    marker = '\t"strings"\n'
    if marker not in source:
        raise RuntimeError("Go import layout changed; BoundedQueue sync import failed closed.")
    return source.replace(marker, marker + '\t"sync"\n', 1)


def install_bounded_queue_sync_v1() -> None:
    global _INSTALLED, _ORIGINAL_GENERATE
    if _INSTALLED:
        return

    _patch_runtime_prelude()
    _ORIGINAL_GENERATE = _codegen.GoCodegen.generate
    _codegen.GoCodegen.generate = _generate_with_sync_import
    _INSTALLED = True

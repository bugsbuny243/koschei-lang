# Koschei Task Cancellation & Send Safety v1

Status: deterministic pending-task cancellation and future-parallel ownership boundary. This is **not** yet a parallel executor.

Structured Task Scope v1 made task lifetime explicit. This gate adds two contracts needed before a real parallel backend can exist safely:

1. pending work can be cancelled deterministically;
2. arbitrary mutable aliases cannot cross the task boundary.

## Cancellation ABI

```ks
let id = task_spawn(scope, worker, value) or return
let cancelled = task_cancel(scope, id) or false
let cancelled_count = task_cancel_all(scope) or 0
```

`task_cancel(scope, id) -> Bool or Error`:

- `true`: a pending task became permanently cancelled;
- `false`: that task was already cancelled or was no longer pending;
- `KS3916`: the id does not belong to the scope;
- `KS3913`: the scope is already closed/joining.

Cancellation never reuses a task id. A cancelled slot remains terminal in the same fixed task table.

`task_cancel_all(scope) -> Int or Error` cancels every currently pending child and returns the number newly cancelled. Calling it again before join returns `0`.

## Join interaction

A cancelled child is terminal before join. `task_join_all`:

- closes the scope;
- skips every cancelled slot without invoking its worker;
- executes remaining pending workers in their original spawn order;
- drives all remaining children terminal;
- leaves `task_pending(scope)` at zero.

There is no race between cancellation and execution in this cooperative v1 scheduler because no worker begins before join. A future parallel scheduler will need an explicit running-task cancellation protocol rather than silently changing these semantics.

## Share-safe task arguments

Task arguments are now deliberately narrower than ordinary Koschei function arguments.

Allowed in v1:

- `Bool`
- `Int`
- `Float`
- `String`
- `BoundedQueue<Bool>`
- `BoundedQueue<Int>`
- `BoundedQueue<Float>`
- `BoundedQueue<String>`

Rejected with `KS3917`:

- `List<T>`
- `Map<K,V>`
- arbitrary structs/enums
- nested or mutable-item bounded queues such as `BoundedQueue<List<Int>>`
- other values that do not have an explicit share-safe contract

Capabilities remain a separate stronger prohibition and continue to fail as `KS3914`.

This restriction is intentionally conservative. It prevents the cooperative API from establishing source programs that would later contain implicit shared mutable aliases if the same task contract were backed by real parallel execution.

## Why BoundedQueue is the communication path

A bounded queue already has:

- explicit finite capacity;
- explicit full/empty behavior;
- no silent buffer growth;
- FIFO semantics;
- capability-free item types.

Task communication therefore flows through a resource-bounded primitive rather than sharing arbitrary mutable containers. Before a true parallel executor is enabled, BoundedQueue itself must gain and prove a race-free synchronization/ownership implementation.

## Backend parity

Cancellation and send-safety checks are wired through:

- structural Typed HIR;
- legacy semantic compatibility for cancellation calls;
- tree interpreter;
- sealed-MIR runtime;
- generated Go runtime.

The reference workload cancels the first of two queue-writing workers. The cancelled worker must never write; the second worker must still execute, and interpreter/native output must remain byte-identical.

## Next gate

The next runtime gate is **race-free BoundedQueue synchronization**. Only after the shared communication primitive is safe under simultaneous producer/consumer access should Koschei consider placing structured workers onto real goroutines/threads. Task lifetime, cancellation, authority restrictions, and share-safe argument rules must remain unchanged when that executor arrives.

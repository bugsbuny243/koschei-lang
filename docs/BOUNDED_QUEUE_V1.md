# Koschei Bounded Queue v1

Status: deterministic backpressure primitive. This is **not** yet a thread, async scheduler, or structured-concurrency claim.

Large services need a way to bound work before they add concurrency. An unbounded message queue can turn a temporary producer/consumer imbalance into process-wide memory exhaustion. Koschei therefore starts its concurrency foundation with a queue whose capacity is explicit and physically bounded.

## ABI

```ks
let queue = bounded_queue(1024, 0) or return

let accepted = queue_try_send(queue, 42)
let value = queue_try_recv(queue) or -1
let used = queue_len(queue)
let limit = queue_capacity(queue)
```

`bounded_queue(capacity, witness)` uses the second argument only as a **type witness**. It is not inserted into the queue. In the example above the resulting static type is `BoundedQueue<Int>`.

The witness exists because Koschei generic inference requires type parameters to be proven from inputs; v1 does not invent a hidden dynamic type for a return-only `T`. A future general explicit-generic-call syntax may provide a cleaner `bounded_queue<Int>(1024)` surface without weakening this contract.

## Capacity contract

Capacity must be an `Int` in `1..65536`. Construction outside that range returns `Error` (`KS3901`).

Both the interpreter and generated Go runtime allocate one fixed ring buffer of exactly `capacity` slots. `queue_try_send` does not append to a growable backing list/slice. `queue_try_recv` clears the released slot so consumed objects are not retained by the queue indefinitely.

The 65536 ceiling is a v1 per-queue resource budget, not a throughput benchmark.

## Backpressure contract

`queue_try_send(queue, item) -> Bool` is non-blocking:

- `true`: item was accepted;
- `false`: queue was full and **nothing was dropped or overwritten**.

Full is therefore normal, explicit backpressure rather than an exception or hidden wait.

`queue_try_recv(queue) -> T or Error` is also non-blocking:

- an item is returned in FIFO order when available;
- empty returns `KS3903` and must be handled with Koschei's normal `or` policy.

There is no hidden sleep, scheduler, retry loop, blocking syscall, unbounded spill buffer, or disk/network authority in this primitive.

## Type and capability integrity

`BoundedQueue<T>` is a real generic type. `queue_try_send` requires the sent value to be assignable to the queue's `T` at compile time.

Capability types cannot be used as `T`, directly or through a generic argument. The runtime also refuses capability values and performs a defensive item-type check based on the constructor witness. Queue creation/import does not grant any capability.

## Determinism

For a single queue and one execution order, operations are deterministic:

- FIFO ordering;
- fixed capacity;
- full send returns `false` without mutation;
- empty receive returns the named error;
- interpreter and native Go backend must produce byte-identical observable output for the reference workload.

## Deliberate boundary

This v1 primitive does **not** run operations concurrently. It establishes the bounded communication contract needed before task scheduling exists.

The next concurrency gate is structured task scope: spawned work must have a lexical lifetime, cannot detach silently, must join/cancel deterministically at the scope boundary, and will communicate through bounded channels rather than ambient unbounded queues.

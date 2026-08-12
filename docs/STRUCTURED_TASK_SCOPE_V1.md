# Koschei Structured Task Scope v1

Status: deterministic cooperative task lifetime. This is **not** yet parallel threads, async I/O, or a preemptive scheduler.

Bounded Queue v1 established explicit backpressure. Task Scope v1 establishes the next invariant: work cannot silently outlive the scope that owns it.

## ABI

```ks
fn worker(queue: BoundedQueue<Int>) {
    queue_try_send(queue, 42)
}

fn main() {
    let queue = bounded_queue(8, 0) or return
    let scope = task_scope(4) or return

    let task = task_spawn(scope, worker, queue) or return
    println(task)
    task_join_all(scope) or return
}
```

Additional inspection:

```ks
task_pending(scope)
task_capacity(scope)
task_closed(scope)
```

## v1 worker contract

A child worker must be:

- a direct local named function, not an alias or closure;
- different from `main`;
- exactly unary;
- `Void` returning;
- capability-free in its parameter and supplied argument;
- unable to receive a `TaskScope` control handle, directly or nested in a structural type.

The structural Typed HIR checker validates the worker declaration and supplied argument type before legacy compatibility checking. Native runtime defenses repeat the unary/Void/capability constraints where possible.

Return values are forbidden rather than silently discarded. Later result-bearing tasks need an explicit typed result contract.

## Structured lifetime

`task_spawn` records a child in the owning scope's fixed task table. It does **not** start a background thread or detached coroutine.

`task_join_all`:

1. closes the scope before any child begins;
2. executes every recorded child in deterministic spawn order;
3. marks each child terminal;
4. keeps the first language-level child failure;
5. continues processing the remaining recorded children;
6. returns the first failure after the scope has drained, or `Void` on success.

Calling join again is idempotent: the stored join result is returned and children are not rerun. Once join begins, `task_spawn` can never extend that scope.

If user code simply drops an unjoined scope, pending task descriptions are discarded and **no task was ever running in the background**. This v1 design therefore cannot create a silently detached running task.

## Resource bound

Task scope capacity is fixed at construction in `1..4096`.

Interpreter and Go runtime allocate exactly `capacity` task slots once. Spawn does not append or grow the task table. Exceeding capacity returns `KS3912`.

This is a per-scope safety budget, not a throughput benchmark.

## Communication and backpressure

Task Scope v1 is designed to compose with `BoundedQueue<T>`. Children may receive a bounded queue as their ordinary argument and communicate through it. Queue capacity/backpressure remains explicit and deterministic.

Task arguments cannot carry capability values in v1. Concurrency must not accidentally become an authority-propagation mechanism.

## Determinism and backend parity

The v1 scheduler is cooperative and serial by definition. Spawn order is execution order. The same task graph therefore has one deterministic observable schedule in the interpreter, direct MIR runtime, and generated Go backend.

The reference workload requires interpreter/native byte-identical output.

## Why real parallelism is deliberately later

A real parallel backend cannot merely place these workers on goroutines or OS threads. Shared mutable values such as `BoundedQueue<T>` currently have deterministic single-scheduler semantics; parallel execution would require a proven ownership/synchronization model, cancellation rules, fairness/resource budgets, and race-free queue implementation.

The next concurrency gate is therefore to specify ownership and cancellation semantics, then add an async/parallel executor underneath the structured lifetime contract without weakening it.

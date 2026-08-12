# Deterministic Parallelism v1

Koschei does not make scheduler order part of program meaning.

The first real native-parallel primitive is `parallel_map(values, worker, max_workers)`.
The Go backend executes work through a bounded goroutine pool while committing every
result into the original input index. The interpreter may execute the same contract
sequentially; observable output must remain identical.

## v1 contract

- input: concrete `List<Bool|Int|Float|String>`
- worker: direct local named function
- worker shape: exactly one scalar parameter and one scalar result
- worker body: leaf/pure; no named/builtin calls, stdout, capability use, task/queue use,
  recursion, imported module calls, or nested callbacks
- worker budget: integer `1..64`
- native worker count: `min(max_workers, len(values))`
- storage: one fixed result slot and one fixed failure slot per input element
- result order: exact input order, independent of scheduler order
- failure order: first failure by lowest input index, independent of completion order
- capability values never cross this boundary
- raw non-scalar runtime results fail closed

## Why existing task_join_all is not silently parallelized

Structured Task Scope currently permits bounded queues as task arguments. Multiple
workers writing one queue would make arrival order depend on host scheduling. Turning
that API parallel without a new ordering contract would weaken Koschei's deterministic
execution model. `task_join_all` therefore remains cooperative in v1.

## Native runtime proof

The test suite generates the real Go runtime, runs `go test -race`, verifies actual
worker overlap with an atomic peak-concurrency counter, exercises a generated Koschei
worker under concurrency, and checks result-index order and call-depth cleanup.

## Next gates

1. deterministic indexed task results for general Structured Task Scope
2. cancellation propagation into running native workers
3. deterministic message sequencing for multi-producer channels
4. bounded executor resource accounting in MIR and build manifests
5. benchmark and starvation/fairness corpus before higher worker ceilings

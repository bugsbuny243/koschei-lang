# Koschei Workspaces v1

Status: large-codebase foundation. This is not a production-scale or Alibaba-scale readiness claim.

Koschei Workspace v1 lets one repository contain many Koschei projects and gives the repository one deterministic dependency graph, workspace-wide compiler/capability gates, declared package imports, and one SHA-256-bound workspace lock.

The goal is to make large codebases decomposable without weakening the security boundary that already exists for a single Koschei project.

## Manifest

A workspace root contains `koschei.workspace.toml`:

```toml
schema_version = "koschei.workspace/v1"

[workspace]
members = [
  "libs/domain",
  "services/catalog",
  "services/orders",
]

[dependencies]
domain = []
catalog = ["domain"]
orders = ["catalog"]
```

Every member is still an ordinary Koschei project with its own `koschei.toml` and entry source. Package names must remain unique across the workspace.

## Declared package imports

A workspace member may import another package only when that package is a **direct dependency** in the workspace manifest.

`services/catalog/src/main.ks` below is a workspace-context snippet: the generic single-file documentation verifier intentionally has no workspace resolver.

<!-- verify: skip -->
```ks
import domain

fn sellable(stock: Int) -> Bool {
    return domain.stock_ok(stock)
}
```

`services/orders/src/main.ks` is likewise verified by the checked-in commerce workspace and workspace test suite rather than the sibling-only single-file verifier.

<!-- verify: skip -->
```ks
import catalog

fn main() {
    println("orders:{catalog.sellable(2)}")
}
```

With the manifest above, `orders` may import `catalog`. It may **not** import `domain` merely because `catalog` depends on `domain`; transitive visibility is not ambient authority.

Resolution is deliberately narrow:

1. a sibling `name.ks` inside the current package remains a normal local module;
2. if no local module exists, `name` may resolve to the entrypoint of a workspace package listed as a direct dependency of the importing package;
3. if a local module and a declared dependency have the same name, Koschei rejects the import instead of allowing shadowing;
4. if `name` identifies another workspace package but it is not a direct dependency, Koschei rejects the import;
5. arbitrary parent-directory search, undeclared package discovery, and remote registry fallback do not exist in this version.

Ordinary non-workspace `ks` programs keep the existing sibling-module resolver. Workspace package lookup is activated only by the workspace toolchain.

Most importantly, a dependency edge and an `import` still grant **no disk, network, environment, or process authority**. Capability arguments must be explicitly present in the source call graph exactly as before.

## Check the complete monorepo

```sh
ks-workspace check .
```

Workspace checking resolves the dependency DAG deterministically and invokes the existing Koschei module/type/capability checker for every member using the declared package resolver. A failure in a local module or imported package fails the workspace command.

Independent packages with equal dependency readiness are ordered lexicographically, so the same manifest produces the same build order.

## Workspace capability policy

```sh
ks-workspace caps .
ks-workspace caps . --deny net
ks-workspace caps . --deny disk
```

The report aggregates the capability domains requested by every member while retaining per-member evidence. Imported dependency code remains visible to capability analysis. `--deny` is a CI gate: if any checked member graph requests a denied domain, the command exits with code 2.

A dependency edge does not grant capability authority. Declaring `orders = ["catalog"]` does not give `orders` the disk, network, environment, or process authority held by `catalog`.

## Lock the complete workspace

```sh
ks-workspace lock create .
ks-workspace lock verify .
```

`koschei.workspace.lock.json` binds:

- the exact workspace manifest SHA-256;
- deterministic dependency build order;
- every member name, path, version, entry and declared workspace dependencies;
- every member `koschei.toml` SHA-256;
- every member's `koschei.module-lock.v1` graph digest;
- one canonical workspace digest over the complete graph.

For a package-local graph, the existing member module-lock identity is preserved. When a member imports another workspace package, its module lock is rooted at the workspace and therefore binds the workspace-relative source paths, import edges, and SHA-256 bytes of the imported package graph as well. A dependency source change invalidates the workspace lock.

Lock parsing rejects duplicate JSON members, unknown fields, malformed digests, non-canonical dependency lists, forged build order and digest tampering. Lock creation is no-replace unless `--force` is explicit.

## Fail-closed path and graph rules

Workspace v1 rejects:

- absolute, parent-traversal and non-portable member paths;
- symlinks in member paths or member project manifests;
- duplicate member paths or package names;
- ambiguous/nested member ownership when package imports are resolved;
- dependencies on unknown packages;
- self-dependencies and dependency cycles;
- undeclared direct package imports;
- local-module/package-name shadowing;
- unsupported manifest fields or schemas.

The dependency sorter is a deterministic heap-based Kahn traversal with `O((V + E) log V)` ordering cost rather than repeated full-graph scans.

Resource limits are explicit:

- workspace manifest: at most 8 MiB;
- members: at most 100,000;
- dependency edges: at most 1,000,000.

These are parser/orchestration safety budgets, not claims that current compiler throughput has been benchmarked at those maxima.

## Commerce reference

`examples/commerce_workspace/` contains three packages:

```text
libs/domain
services/catalog
services/orders
```

The declared dependency and source-import chain is:

```text
domain <- catalog <- orders
```

`catalog` calls the public `domain.stock_ok` function. `orders` calls `catalog.sellable`. `orders` intentionally does not receive implicit access to `domain`.

Run the repository-wide proof with:

```sh
ks-workspace check examples/commerce_workspace
ks-workspace caps examples/commerce_workspace
ks-workspace lock create examples/commerce_workspace
ks-workspace lock verify examples/commerce_workspace
```

## Deliberate current boundary

Workspace package imports are now available to **check, capability analysis and workspace locking**. The ordinary `ks run` / `ks build` commands do not yet receive workspace package context, so this change does not claim workspace-native execution/build support.

The next large-project gate is a workspace-aware build target that compiles a selected package with its locked declared dependencies and proves interpreter/native output parity. After that, incremental compilation/cache identity can be layered on top of the same package graph.

Remote package registries are also still absent. No package is downloaded or trusted merely because its name appears in a manifest.

## Large-system direction

Workspaces solve repository decomposition, package visibility and source integrity, not the whole distributed-systems problem. Production-scale service systems still require separately proven concurrency/backpressure, server/network resource bounds, durable storage and recovery, package distribution, observability, incremental builds and performance gates.

Koschei will add those capabilities as independently testable language/runtime contracts rather than claiming scale because a monorepo manifest exists.

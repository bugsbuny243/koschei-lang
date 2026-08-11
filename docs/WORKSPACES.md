# Koschei Workspaces v1

Status: large-codebase foundation. This is not a production-scale or Alibaba-scale readiness claim.

Koschei Workspace v1 lets one repository contain many independent Koschei projects and gives the repository one deterministic dependency graph, one workspace-wide compiler check, one capability view, and one SHA-256-bound workspace lock.

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
orders = ["catalog", "domain"]
```

Every member is still an ordinary Koschei project with its own `koschei.toml` and entry source. Package names must remain unique across the workspace.

## Check the complete monorepo

```sh
ks-workspace check .
```

Workspace checking resolves the dependency DAG deterministically and invokes the existing Koschei module/type/capability checker for every member. A failure in any member fails the workspace command.

Independent packages with equal dependency readiness are ordered lexicographically, so the same manifest produces the same build order.

## Workspace capability policy

```sh
ks-workspace caps .
ks-workspace caps . --deny net
ks-workspace caps . --deny disk
```

The report aggregates the capability domains requested by every member while retaining per-member evidence. `--deny` is a CI gate: if any member requests a denied domain, the command exits with code 2.

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
- every member's existing `koschei.module-lock.v1` digest;
- one canonical workspace digest over the complete graph.

The nested module-lock digest means source byte drift or local import-topology drift inside one package also invalidates the workspace lock.

Lock parsing rejects duplicate JSON members, unknown fields, malformed digests, non-canonical dependency lists, forged build order and digest tampering. Lock creation is no-replace unless `--force` is explicit.

## Fail-closed path and graph rules

Workspace v1 rejects:

- absolute, parent-traversal and non-portable member paths;
- symlinks in member paths or member project manifests;
- duplicate member paths or package names;
- dependencies on unknown packages;
- self-dependencies and dependency cycles;
- unsupported manifest fields or schemas.

The dependency sorter is a deterministic heap-based Kahn traversal with `O((V + E) log V)` ordering cost rather than repeated full-graph scans.

Resource limits are explicit:

- workspace manifest: at most 8 MiB;
- members: at most 100,000;
- dependency edges: at most 1,000,000.

These are parser/orchestration safety budgets, not claims that current compiler throughput has been benchmarked at those maxima.

## Commerce reference

`examples/commerce_workspace/` contains three independent packages:

```text
libs/domain
services/catalog
services/orders
```

The declared workspace order is:

```text
domain -> catalog -> orders
```

Each package is independently checkable today. The workspace coordinates their build/check order and locks their identities as one repository.

## Deliberate v1 boundary

Workspace dependency edges are **not yet source-level cross-package imports**. Existing Koschei `import` continues to resolve sibling modules inside one project/module graph.

Workspace v1 deliberately does not make an undeclared package visible to another package, does not search arbitrary parent directories, does not download remote packages, and does not invent capability inheritance across a dependency edge.

The next package-system gate is an explicit cross-package resolver in which a source import may target only a declared workspace dependency and the resolved package identity must be bound by the workspace lock. That feature must preserve interpreter/native parity and the rule that dependency code receives no ambient authority.

## Large-system direction

Workspaces solve repository decomposition and integrity, not the whole distributed-systems problem. Production-scale service systems still require separately proven concurrency/backpressure, server/network resource bounds, durable storage and recovery, package distribution, observability, incremental builds and performance gates.

Koschei will add those capabilities as independently testable language/runtime contracts rather than claiming scale because a monorepo manifest exists.

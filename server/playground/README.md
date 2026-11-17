# Koschei Playground

A web page where anyone can write a Koschei program and run it on the server, with no install.

## How untrusted code is contained

1. **Language policy.** Before anything runs, `ks caps --json --deny disk --deny net --deny env --deny process --deny serve --deny persist --deny input` type-checks the program and reads its capability manifest. A program that requests any of those domains, even narrowed (`caps.disk.allow_read_only("/etc")`), is rejected with exit code 2, and none of its code executes. Only pure computation, clock and random get through.
2. **Process sandbox.** Each check or run happens in a child process in a fresh temporary directory. The child has an empty environment and limits on CPU (5 s), memory (512 MB), file size and open files. It also has a 10 s wall-clock timeout and a 200,000-step interpreter budget. The hosted Docker image **requires bubblewrap**: the child is additionally confined in separate user, PID, network, IPC, mount and UTS namespaces with only read-only host /usr, a writable /work bound to its fresh workdir, a private 16 MiB /tmp, minimal /dev, and /proc. Nested user namespace creation is disabled. The host /etc, /root, /home, /opt and original /tmp are not mounted. Both the `ks caps` check and `ks run` use the same confined launcher.
3. **Service limits.**
   - Source size is capped at 16 KB.
   - Returned output is capped at 16 KB per stream. Child stdout/stderr are first spooled to anonymous files bounded by the child file-size limit (1 MiB each), so the HTTP server does not buffer untrusted output in RAM before truncation.
   - Each client is limited to 30 requests per minute.
   - The container runs as a non-root user.

## Run locally

```sh
pip install -e .
python server/playground/app.py      # http://localhost:8080
```

## Hosted Docker deployment (reference, not yet production-certified)

This reference profile is designed for a dedicated Linux host with cgroup v2
and support for unprivileged user, mount and network namespaces.

```sh
docker compose -f server/playground/compose.security.yaml config --quiet
docker compose -f server/playground/compose.security.yaml up --build
```

The profile publishes only `127.0.0.1:8080`. A trusted reverse proxy with
per-user/request limits and appropriate TLS is required before public access.

The Compose service specifies **aggregate kernel-enforced limits** for the
whole container: at most 1536 MiB of memory, 2 CPU cores of quota, and 128
PIDs. It also uses a read-only root filesystem, drops all Linux capabilities,
sets `no-new-privileges`, keeps Docker's default seccomp filtering, and gives
the service a 64 MiB `/tmp` tmpfs. At most two evaluation requests may run
simultaneously. Each untrusted execution retains its separate, smaller CPU,
address-space, output and wall-clock limits.

### Required kernel admission checks

The Dockerfile sets `KOSCHEI_REQUIRE_CONTAINER_LIMITS=1` and
`KOSCHEI_UNTRUSTED_SANDBOX=bwrap`. On startup, the server refuses to listen
unless it observes all of the following in its **live environment**:

- `/proc/self/status`: `Seccomp: 2` (filtered) and `NoNewPrivs: 1`
- cgroup v2 `memory.max` is finite and no more than 1536 MiB
- cgroup v2 `pids.max` is finite and no more than 128
- cgroup v2 `cpu.max` is finite and no more than two cores
- `bubblewrap` can launch Python in a private mount and network namespace,
  with a minimal filesystem and no visible `/etc/passwd`

The kernel-admission gate checks only that a seccomp filter is active, **not
the individual permitted syscalls**. It does not prove that a Docker host's
profile is sufficiently restrictive. The namespace startup probe is also not
an independent security audit.

### When startup fails

Many default container providers block the nested user/mount namespaces
required by bubblewrap. The correct result is to **refuse startup**, not to
disable security. Do **not** use `--privileged`, `seccomp:unconfined`, a
disabled `no-new-privileges` flag, or
`KOSCHEI_UNTRUSTED_SANDBOX=off` on a public service.

Moving the same Compose service to a dedicated host is **not sufficient**.
Docker's [default seccomp policy](https://docs.docker.com/engine/security/seccomp/)
restricts namespace-related `clone`/`unshare` operations and mounting. These
can conflict with bubblewrap even when the host kernel enables user namespaces.
The generic bubblewrap error does not identify whether seccomp, AppArmor/SELinux,
or kernel namespace policy caused this particular denial. `Seccomp: 2` proves
only that a filter is active; it does not identify its rules.

The live probe now prints a bounded `HOST_SECURITY` JSON record before admission:
allowlisted process security fields, namespace sysctls and cgroup limits only.
Absent controls are unknown, not a pass. It never dumps environment variables.
The live CI job saves this evidence with the candidate SHA even on failure;
the command's failing exit status is preserved through the log capture.

The host operator must inspect the effective syscall and LSM policies together
with this receipt. If the required launcher operations are denied, select a
separately isolated worker architecture and audit its boundary before deployment.
This repository does not yet provide a verified replacement worker. Do not
blindly allow namespace/mount syscalls, add `CAP_SYS_ADMIN`, or disable LSM
protections to make this configuration pass. Issue #389 remains open until
the full positive live acceptance test passes under the reviewed policy.
The previous `docker run -p ...` quickstart is not a production deployment:
it does not set the required cgroups and no-new-privileges flags and is
expected to fail startup.

Local `python server/playground/app.py` still defaults to resource-limited
development mode without OS namespace/cgroup gates. **Use only with trusted
local code**.

### Verified incompatibility: GitHub-hosted Docker

On 15 November 2026 the [live integration attempt](https://github.com/bugsbuny243/koschei-lang/actions/runs/43721126775) built the hardened Docker image and passed the cgroup/seccomp preflight, but refused startup at the bubblewrap namespace preflight:

```text
bwrap: No permissions to create new namespace, likely because the kernel
does not allow non-privileged user namespaces.
```

**This is a real deployment compatibility blocker** for the tested Docker
runner, not evidence that the Playground is safely executable there.
The service correctly fails closed, and the positive live acceptance job
remains red. Do not disable `no-new-privileges` / seccomp, run privileged,
or switch `KOSCHEI_UNTRUSTED_SANDBOX=off` to make the job green.

Use a dedicated host that supports the required isolation or a separately
sandboxed worker. That host must rerun the **same positive acceptance
checks** and provide a successful cgroup/namespace/API runtime receipt.
The static test and image-build workflow passing alone is not sufficient.

### Validation before enabling public access

```sh
python -m pytest -q \
  tests/test_playground_container_limits_v1.py \
  tests/test_playground_namespace_confinement_v1.py \
  tests/test_playground_output_capture_v1.py \
  tests/test_playground_server.py
docker compose -f server/playground/compose.security.yaml config --quiet
```

In addition to these unit/configuration checks, a compatible Linux runtime
must pass real boot, cgroup, no-network, filesystem isolation and output-limit
integration tests; the hosted API must not become available if any gate fails.
Review the runtime's actual Docker seccomp policy and deploy independent
ingress-level anti-abuse limits. No public-production readiness claim is made
by passing the static tests alone.

## API

### Website-only operation while execution is unavailable

Set `KOSCHEI_PLAYGROUND_MODE=disabled` explicitly to serve the product site
without accepting code execution. Restart the process after changing it.
In this mode:

- `/`, the documentation pages and discovery files remain available.
- `/play` and `/play/` show a temporary-unavailability page with HTTP 503.
- `/api/evaluate` rejects both `check` and `run` with HTTP 503 and
  `error: evaluation_disabled`, before reading the body or invoking the compiler.
- `/health` returns `ok: true, evaluation_enabled: false`. This is website
  health, **not** proof that an execution worker is ready.
- Execution-only namespace and cgroup admission checks are not run because
  no evaluation is accepted. External container/host controls still apply.

The default is `enabled`, preserving the existing execution startup gates.
Unknown mode values abort startup; an execution startup failure never switches
automatically into website-only mode. This setting is separate from
`KOSCHEI_UNTRUSTED_SANDBOX`: disabling the sandbox is not an alternative.

This is the first step toward separating website hosting from an isolated
execution worker. It does **not** implement a remote worker or solve #389.
Before adding a worker, require a reviewed isolation policy and successful
live acceptance evidence for its exact release, authenticated private transport,
bounded queues and deadlines, and no local-execution fallback when it fails.
Keep online evaluation disabled until that path is implemented and verified.

For an approved website-only deployment, set the environment variable on the
hosting service. Do not claim deployment success solely from `/health`; also
check the homepage, `/play` and an evaluation POST for the responses above.
Re-enabling execution requires the existing live isolation release gates.

### Evaluation responses

`POST /api/evaluate` with `{"source": "...", "action": "run" | "check"}` returns:

- `stage`: `policy`, `check` or `run`
- `manifest`: the capability manifest
- `policy`: the output of the policy and check step
- `run`: the program's output, when it ran

`GET /health` returns `{"ok": true, "evaluation_enabled": true}` in enabled mode.

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

### Why not Docker (diagnosed, 16 November 2026)

The namespace refusal seen on GitHub-hosted Docker was reproduced on a host
**without AppArmor** (kernel 6.18, Docker 29, same bubblewrap flags, uid
10001, `cap-drop ALL`, `no-new-privileges`):

| Configuration | Result |
|---|---|
| Docker default seccomp | `bwrap: No permissions to create new namespace` (identical) |
| Same, seccomp disabled (diagnosis only) | `bwrap: Can't mount proc on /newroot/proc: Operation not permitted` |
| Same host, no container, unprivileged user | works |

So the failure does not need AppArmor: Docker's default seccomp profile
refuses unprivileged `CLONE_NEWUSER`, and even without it Docker's masked
`/proc` prevents the fresh procfs a PID namespace needs. Making bubblewrap
work in Docker means weakening the container. The supported deployment is
therefore the VM worker below, not this Compose profile.

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

This mode keeps the website independent of execution availability. The proposed
remote worker below does **not** solve host incompatibility (#389). Keep online
evaluation disabled until a separate worker passes live isolation acceptance.

For an approved website-only deployment, set the environment variable on the
hosting service. Do not claim deployment success solely from `/health`; also
check the homepage, `/play` and an evaluation POST for the responses above.
Re-enabling execution requires the existing live isolation release gates.

### Remote worker on a dedicated VM

The frontend supports `KOSCHEI_PLAYGROUND_MODE=remote`. It sends evaluations to
one operator-configured HTTPS origin (`KOSCHEI_WORKER_URL`), authenticated with
`KOSCHEI_WORKER_TOKEN` (64 hex characters) and verified against
`KOSCHEI_WORKER_CA_FILE` or, on platforms that only offer variables, `KOSCHEI_WORKER_CA_PEM` (the worker's private CA; hostname checked). There is
no redirect following, no proxy discovery, no retry and **no local execution
fallback**. One deadline (25 s) covers DNS, connection, TLS, sending and the
whole response; DNS and connection setup run on a bounded pool of four.
Responses are capped at 128 KiB and validated.

If the worker is unreachable when the frontend starts, the website still starts:
`/health` reports `"evaluation_enabled": false`, `/play` and `/api/evaluate`
answer 503, and a background check enables evaluation once the worker passes
an authenticated readiness check (every 30 s). A bad URL, token or CA file
still stops startup. Every request has a 15 s deadline to arrive in full.

The worker (`server/playground/worker.py`) runs as a **systemd service directly
on a Linux VM** (Ubuntu 24.04 tested), never in Docker:

```sh
sudo server/playground/vm/install.sh /path/to/koschei-lang <worker-dns-name> 0.0.0.0:8443 <ingress>
```

`<ingress>` is who may open a connection: one or more CIDRs, or the single
word `any`. `install.sh` creates the `koschei-worker` account, a venv in
`/opt/koschei-worker`, a private CA and server certificate (`vm/make-certs.sh`;
the chain must pass `openssl verify -x509_strict`, because the frontend
verifies with strict X.509 rules on every Python version), a random token,
the units `vm/koschei-worker.socket` and `vm/koschei-worker.service`, and
`/etc/koschei-worker/frontend.env` (root only) with the three values the
frontend needs: `KOSCHEI_WORKER_URL`, `KOSCHEI_WORKER_TOKEN`,
`KOSCHEI_WORKER_CA_PEM`.

#### Ingress and egress are separate

systemd's `IPAddressAllow=` applies in both directions. Allowing the
frontend's address on the service would also let the worker connect *to*
that address, and allowing `any` would remove the egress block entirely.
So the two directions live in different units:

| Unit | Filter | Governs |
| --- | --- | --- |
| `koschei-worker.socket` | `IPAddressDeny=any` + `IPAddressAllow=<ingress>` | the listening socket and every accepted connection (they inherit its cgroup) |
| `koschei-worker.service` | `IPAddressDeny=any` + `IPAddressAllow=localhost` | every socket the worker process opens itself |
| each sandboxed program | own empty network namespace (`bwrap --unshare-net`) | only `lo` exists; nothing is routable |

`install.sh` refuses to finish unless `systemctl show` reports a
loopback-only allowlist and `IPAddressDeny=0.0.0.0/0 ::/0` for the service,
and it deletes the `peer.conf` drop-in of older installs (which put the
frontend range on the service).

#### When Railway's outbound address changes

Railway does not give a service a fixed outbound address unless static
egress IPs are bought for it. Two supported settings:

- **`any` (default for Railway today).** Anyone can reach the TLS port; that
  is all they get. Every request must present the 256-bit token, the frontend
  pins the worker's private CA and checks the hostname, and an unauthenticated
  client is answered 401 before anything runs. The worker's own egress stays
  blocked (verified by `connectivity.py` with ingress `any`). Only the TLS
  port is exposed; nothing else on the VM listens publicly by this install.
- **Static egress IPs**, when available: rerun `install.sh` with those
  addresses, or change them live without restarting the worker:
  `systemctl set-property koschei-worker.socket IPAddressAllow= IPAddressAllow=<cidr>...`

A changing address never needs the service filter touched; never widen
`IPAddressAllow` on the service to reach the frontend.

The socket unit owns the port, so the port stays open while the worker
restarts; connections wait in the backlog and the frontend's 25 s deadline
turns a worker that does not come up into a 503. A worker that fails its
preflight never serves a request (verified by `degrade.sh`). Not yet
verified: how the socket unit behaves once the service hits systemd's start
limit. Stopping the worker on purpose means stopping both:
`systemctl stop koschei-worker.socket koschei-worker.service` (verified:
the frontend then answers 503 in about 20 ms and the site stays up).

The unit `vm/koschei-worker.service`:

- **Limits**: `MemoryMax=1G`, `CPUQuota=100%`, `TasksMax=96` on the service's own
  cgroup; per program 5 s CPU, 10 s wall, 512 MiB address space, 1 MiB files,
  64 open files, 16 KiB output, 200 000 interpreter steps.
- **Privileges**: `NoNewPrivileges`, empty capability sets, `SystemCallFilter=
  @system-service @mount` minus swap/reboot/raw-io/module/debug/clock groups,
  `RestrictNamespaces=user mnt pid net ipc uts`.
- **Files**: `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`,
  `PrivateDevices`. Each program sees only `/usr`, the read-only venv, a
  private `/work` and a 16 MiB `/tmp`.
- **Secrets**: the token and TLS key arrive through `LoadCredential=`, never in
  the environment, and are invisible inside sandboxes.
- **Network**: the worker serves TLS itself on the socket passed by
  `koschei-worker.socket`; the service has `IPAddressDeny=any` with loopback
  only, so it can make no outbound connection (see the table above).
- **AppArmor** (Ubuntu 24.04 restricts unprivileged user namespaces):
  `vm/koschei-bwrap.apparmor` grants `userns` to one copy of bubblewrap,
  `/opt/koschei-worker/bin/bwrap`, executable only by the worker account. The
  host-wide restriction stays on.
- Not set, on purpose: `ProtectKernelTunables`, `ProtectKernelLogs`,
  `ProtectProc`, `ProtectHostname`. They put locked mounts over `/proc`, and
  the kernel then refuses each sandbox's procfs.

The worker checks itself on the live process: `Seccomp=2`, `NoNewPrivs=1`, and
finite `memory.max`, `pids.max` and `cpu.max` on **its own cgroup** (resolved
from `/proc/self/cgroup`; on a VM that is
`/system.slice/koschei-worker.service`, not the mount root). The unit's
`ExecStartPre` runs `runtime_security_probe.py` with the same confinement, and
the worker does not start unless all of these pass: namespaces, filesystem,
loopback network, PID namespace, hidden credentials, memory, CPU and file-size
limits, a real Koschei run and a capability denial. The network check runs a
program inside the sandbox that must see only `lo` and fail to reach public
IPv4/IPv6 addresses, UDP DNS, name resolution, `169.254.169.254`, RFC 1918 and
CGNAT ranges, the VM's own address and its default gateway. After adopting
the listening socket, the worker also proves that a sandboxed program inherits
no open descriptor (so it cannot accept connections on the worker's port).

Tests on a real VM (`vm/test/`, run by the `Playground Live Isolation
Acceptance` workflow on a GitHub Ubuntu 24.04 runner):

- `acceptance.py`: black-box over TLS: allowed program, disk/network denied before
  running, output limit, runaway program, missing/wrong token, malformed
  request, capacity (503).
- `degrade.sh`: removing the PID, memory or CPU limit, user namespaces, seccomp
  and no-new-privileges, or the AppArmor grant each stops the worker.
- `connectivity.py`: the real frontend (`app.py`, remote mode) in its own
  network namespace, reaching the worker from a non-loopback address:
  authorized frontend runs a program; wrong token, a foreign CA, public CAs
  only and a wrong hostname all give 503 while the site stays up; an address
  outside the ingress list is dropped; with ingress `any` the worker's cgroup
  still cannot reach a public IP, the frontend's private network, the gateway
  or metadata; the worker stopped gives a fast 503 with the site up, and
  evaluation recovers when it returns.
- `emulation.conf` is for an emulated (QEMU/TCG) test VM only. It raises the
  time limits by about 20x, so never install it on a real worker.

### Evaluation responses

`POST /api/evaluate` with `{"source": "...", "action": "run" | "check"}` returns:

- `stage`: `policy`, `check` or `run`
- `manifest`: the capability manifest
- `policy`: the output of the policy and check step
- `run`: the program's output, when it ran

`GET /health` returns `{"ok": true, "evaluation_enabled": true}` in enabled mode.

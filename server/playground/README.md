# Koschei Playground

A web page where anyone can write a Koschei program and run it on the server, with no install.

## How untrusted code is contained

1. **Language policy.** Before anything runs, `ks caps --json --deny disk --deny net --deny env --deny process --deny serve --deny persist --deny input` type-checks the program and reads its capability manifest. A program that requests any of those domains, even narrowed (`caps.disk.allow_read_only("/etc")`), is rejected with exit code 2, and none of its code executes. Only pure computation, clock and random get through.
2. **Process sandbox.** Each check or run happens in a child process in a fresh temporary directory. The child has an empty environment and limits on CPU (5 s), memory (512 MB), file size and open files. It also has a 10 s wall-clock timeout and a 200,000-step interpreter budget. The hosted Docker image **requires bubblewrap**: the child is additionally confined in separate user, PID, network, IPC, mount and UTS namespaces with only read-only host /usr, a writable /work bound to its fresh workdir, a private /tmp, minimal /dev, and /proc. The host /etc, /root, /home, /opt and original /tmp are not mounted. Both the `ks caps` check and `ks run` use the same confined launcher.
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

## Docker

```sh
docker build -f server/playground/Dockerfile -t koschei-playground .
docker run -p 8080:8080 koschei-playground
```

## Isolation requirements and limitations

- The Docker image sets `KOSCHEI_UNTRUSTED_SANDBOX=bwrap` and installs `bubblewrap`. It refuses to serve if a startup probe cannot establish a private mount and network namespace or cannot run Python in the limited root. **It never silently falls back to unrestricted Python.**
- The host must support unprivileged user namespaces and compatible mount operations. Some container providers (including default container-seccomp configurations) block this. **If the service fails to start, do not use `--privileged`, disable all container seccomp protections, or set the sandbox mode to `off` as a production workaround.** Choose a runtime offering verified namespace isolation, or use a separately isolated worker.
- Local `python server/playground/app.py` defaults to `KOSCHEI_UNTRUSTED_SANDBOX=off`, intended **only for trusted local development**. To test OS isolation explicitly, install bubblewrap, use an installed Python toolchain under `/usr`, and set `KOSCHEI_UNTRUSTED_SANDBOX=bwrap`; unsupported hosts fail closed.
- These namespace boundaries do not replace syscall filtering (seccomp), cgroup CPU/memory/PID quotas, a hardened container profile, or trusted ingress-level rate limiting. Those are remaining public deployment requirements. The startup probe is a sanity check, **not a security audit**.
- The standard `docker run` example below is only a quick launch attempt: it will fail closed if the container runtime does not permit the required namespaces. A working, verified deployment profile is required before public launch.

## API

`POST /api/evaluate` with `{"source": "...", "action": "run" | "check"}` returns:

- `stage`: `policy`, `check` or `run`
- `manifest`: the capability manifest
- `policy`: the output of the policy and check step
- `run`: the program's output, when it ran

`GET /health` returns `{"ok": true}`.

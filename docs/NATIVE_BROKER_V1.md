# Koschei Native Capability Broker v1

Status: **disk (read, write, delete), environment, network and the loopback
server in native binaries on linux/amd64; readiness gate G2.** Processes,
`persist` and the one-shot `serve.exchange` still fail closed (`KS4004`). The
network rules are in [`NET_V1.md`](NET_V1.md), the server's in
[`SERVE_KNOWHERE_V1.md`](SERVE_KNOWHERE_V1.md).

## Why

A native binary that opened files itself would carry the authority inside
the same process as the program: a bug in generated code or the runtime could
reach anything the user can reach. The broker separates the two.

## How a binary runs

```
user ──▶ broker (holds the environment, the cwd, the right to open files)
              │  socketpair, descriptor 3
              ▼
          worker (runs the program; empty environment; seccomp-confined)
```

1. The process the user started is the **broker**. It creates a socket pair
   and starts itself again as the **worker** with only
   `KOSCHEI_NATIVE_WORKER=v1` in its environment and the socket as
   descriptor 3. Standard input, output and error are inherited.
2. Before any program code runs, the worker checks that descriptor 3 is a
   socket, sets `no_new_privs` and installs a seccomp filter on all threads.
   The filter is an **allow list** (`native_broker_v1.ALLOWED_SYSCALLS_AMD64`):
   the calls the Go runtime and the program need, measured by tracing
   confined workers, and none that names a path, opens a descriptor to the
   outside, creates a process or reaches another process:
   `read`, `write`, `close`, `fstat`, `lseek`, memory management (`mmap`,
   `munmap`, `mprotect`, `mremap`, `madvise`, `brk`), signal handling of the
   process itself, `futex`, `sched_yield`, sleeping, clocks, `getrandom`,
   `epoll`, `eventfd2`, `pipe2`, `fcntl`, `uname`, `getrlimit`, `getpid`,
   `gettid`, `exit`/`exit_group`, and glibc's per-thread `set_tid_address`,
   `set_robust_list` and `rseq`. Three are checked by argument: `clone` only
   creates threads (`CLONE_THREAD`), `kill`/`tgkill` only signal the worker
   itself, `prlimit64` only reads or sets the worker's own limits. `clone3`
   fails with `ENOSYS`, so callers fall back to `clone`. Every other call fails with
   `EPERM`; a foreign architecture or the x32 ABI kills the worker.
3. Every `DiskReadCaps` and `DiskCaps` operation, every `EnvCaps.get`,
   every `NetCaps.get` and every `ServeCaps.accept`/`reply` is a request on the
   socket; the broker answers with the value or the Error text. A malformed
   request ends the conversation and the worker stops.
4. The broker exits with the worker's status.

## Same answers as `ks run`

The broker applies the interpreter's rules exactly; both were tightened to
rules that do not depend on the host:

- The scope root is resolved with `realpath` and opened once, when the token
  is narrowed. Paths go through `abspath` and `relpath`; `..` cannot leave
  the scope; every component is opened with `O_NOFOLLOW` relative to the
  previous one; symlinks are refused (`KS3405`).
- Errors name the errno symbolically and repeat the program's path
  (`Dosya okunamadı: ENOENT: root/missing`), instead of the host's
  `[Errno 2] No such file or directory: '...'`.
- `read` returns the file's bytes as text: no newline translation (the
  interpreter used to turn `\r\n` into `\n`), the 16 MiB budget first, then
  strict UTF-8. `read_bytes` returns them as `Bytes`.
- `list` returns UTF-8 names sorted by code point; a name that is not UTF-8,
  or more than 1,048,576 entries, is an Error value.
- `env.get` refuses a value that is not UTF-8.
- A path containing NUL is outside every scope.
- `write` / `write_file` replace a file atomically: the bytes go to a
  temporary `.ks-write-<random>.tmp` in the same directory, are synced, and
  are renamed over the target, which keeps its permission bits (a new file
  gets `0600`). A symlink, a directory, a missing parent or the scope root
  itself is refused with the same Error text as `ks run`.
- A disk token that the program drops hands its scope back: the worker's
  garbage collector finalizes it and the broker closes the scope's
  descriptor once no token uses it, as `ks run` closes a dropped token's
  descriptor. Narrowing again to the same directory shares one scope; when
  scopes come within 32 of the descriptor limit, the worker collects before
  the broker opens another.
- `delete` removes a file, a symlink (not its target) or an empty directory;
  the scope root cannot be deleted. A token from `allow_read_only` cannot
  write or delete, in the broker as well as in the checker.

## Limits

- Confinement is implemented for linux/amd64 only; other targets refuse to
  run such a binary (`KS4001`).
- A new Go release may need a system call that is not listed; the worker
  then gets `EPERM` from it, and the binary fails rather than gaining
  authority. The tracing tests below catch this.
- Processes, `persist` and `serve.exchange` are still refused by `ks build`.

## Evidence

`tests/test_native_broker_v1.py`: 23 disk and environment cases print the
same bytes from `ks run` and the binary (traversal, `..`, symlinked files,
directories and scope roots, missing scopes, non-UTF-8 content, names and
values, listings); the worker process reports `Seccomp: 2`,
`NoNewPrivs: 1` and an environment of only the marker; a probe built from
the same runtime shows `open`, `socket`, `exec`, `fork` and `mkdir` refused
after confinement, and so are calls nobody listed (`newfstatat` on a path,
`ioctl(TIOCSTI)`, `ptrace`), a raw `clone` without `CLONE_THREAD`, and
`kill`, `tgkill` and `prlimit64` aimed at the broker, while `kill` and
`prlimit64` on the worker itself pass and `clone3` is `ENOSYS`; a write/delete program (new files, replacement with the
mode kept, symlinked targets and parents, directories, missing parents, the
scope root, paths outside the scope) prints the same bytes and leaves the
same tree, modes included, with no temporary file left behind; processes
stay refused with a G2 reason. Network evidence: `tests/test_native_net_v1.py`.

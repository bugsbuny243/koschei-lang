# Koschei Native Capability Broker v1

Status: **disk (read, write, delete) and environment in native binaries on
linux/amd64; first two steps of readiness gate G2.** The network still fails
closed (`KS4004`).

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
   A foreign architecture or the x32 ABI kills it; these calls fail with
   `EPERM`: `open`, `openat`, `openat2`, `creat`, `socket`, `socketpair`,
   `connect`, `bind`, `listen`, `accept`, `accept4`, `execve`, `execveat`,
   `fork`, `vfork`, every call that creates, renames, links, removes or
   changes a file system entry or its mode/owner, `truncate`, `ftruncate`,
   `chdir`, `fchdir`, `chroot`, `pivot_root`, `mount`, `umount2`, `ptrace`,
   `process_vm_readv/writev`, `kill`, `setuid`, `setgid`,
   `name_to_handle_at`, `open_by_handle_at`, `io_uring_setup`, `bpf`,
   `perf_event_open`, `userfaultfd`, `keyctl`, `add_key`, `request_key`.
3. Every `DiskReadCaps` and `DiskCaps` operation and every `EnvCaps.get` is a request on the
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
- `delete` removes a file, a symlink (not its target) or an empty directory;
  the scope root cannot be deleted. A token from `allow_read_only` cannot
  write or delete, in the broker as well as in the checker.

## Limits

- Confinement is implemented for linux/amd64 only; other targets refuse to
  run such a binary (`KS4001`).
- The filter is a deny list of resource system calls, not an allow list.
- The network, processes, `persist` and `serve` are still refused by
  `ks build`.

## Evidence

`tests/test_native_broker_v1.py`: 23 disk and environment cases print the
same bytes from `ks run` and the binary (traversal, `..`, symlinked files,
directories and scope roots, missing scopes, non-UTF-8 content, names and
values, listings); the worker process reports `Seccomp: 2`,
`NoNewPrivs: 1` and an environment of only the marker; a probe built from
the same runtime shows `open`, `socket`, `exec`, `fork` and `mkdir` refused
after confinement; a write/delete program (new files, replacement with the
mode kept, symlinked targets and parents, directories, missing parents, the
scope root, paths outside the scope) prints the same bytes and leaves the
same tree, modes included, with no temporary file left behind; the network
stays refused with a G2 reason.

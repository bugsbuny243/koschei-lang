# P0.1 — CAPABILITY_RUNTIME host symbol inventory

**Source:** `koschei/codegen_go.py` on main, `CAPABILITY_RUNTIME` embedded Go template only.

**Method:** deterministic text extraction of qualified selectors `syscall|os|io|http|net|filepath|exec|runtime` within this template. Line numbers are relative to the Go template, not the Python source. Containing functions are lexical approximations, not a Go AST or call graph. Type names, constants and functions are intentionally mixed and **must not be called 30 syscalls**.

**Measured in this template:** 611 lines; 71 selector occurrences; 30 distinct selectors. This does not replace the v25 56-ambient-symbol whole-generated-output baseline.

## Distinct selectors

- `filepath.Abs`
- `filepath.Clean`
- `filepath.EvalSymlinks`
- `filepath.IsAbs`
- `filepath.Join`
- `filepath.Rel`
- `http.Client`
- `http.MethodGet`
- `http.NewRequest`
- `http.Request`
- `io.ReadAll`
- `os.LookupEnv`
- `os.Lstat`
- `os.NewFile`
- `os.PathSeparator`
- `os.Remove`
- `runtime.GOOS`
- `syscall.Close`
- `syscall.Dup`
- `syscall.ELOOP`
- `syscall.ENOTDIR`
- `syscall.O_CLOEXEC`
- `syscall.O_CREAT`
- `syscall.O_DIRECTORY`
- `syscall.O_NOFOLLOW`
- `syscall.O_RDONLY`
- `syscall.O_TRUNC`
- `syscall.O_WRONLY`
- `syscall.Open`
- `syscall.Openat`

## All observed selector occurrences

| Template line | Lexical containing function | Selector |
|---:|---|---|
| 152 | `ksNetGet` | `http.Client` |
| 154 | `ksNetGet` | `http.Request` |
| 154 | `ksNetGet` | `http.Request` |
| 165 | `ksNetGet` | `http.NewRequest` |
| 165 | `ksNetGet` | `http.MethodGet` |
| 178 | `ksNetGet` | `io.ReadAll` |
| 187 | `ksNewDiskCapability` | `filepath.Abs` |
| 192 | `ksNewDiskCapability` | `filepath.EvalSymlinks` |
| 196 | `ksNewDiskCapability` | `filepath.Clean` |
| 197 | `ksNewDiskCapability` | `runtime.GOOS` |
| 201 | `ksNewDiskCapability` | `syscall.Open` |
| 203 | `ksNewDiskCapability` | `syscall.O_RDONLY` |
| 203 | `ksNewDiskCapability` | `syscall.O_DIRECTORY` |
| 203 | `ksNewDiskCapability` | `syscall.O_NOFOLLOW` |
| 203 | `ksNewDiskCapability` | `syscall.O_CLOEXEC` |
| 226 | `parts` | `filepath.Abs` |
| 230 | `parts` | `filepath.Rel` |
| 230 | `parts` | `filepath.Clean` |
| 237 | `parts` | `os.PathSeparator` |
| 238 | `parts` | `filepath.IsAbs` |
| 241 | `parts` | `filepath.Clean` |
| 241 | `parts` | `os.PathSeparator` |
| 257 | `rootDuplicate` | `syscall.Dup` |
| 270 | `parent` | `syscall.Openat` |
| 273 | `parent` | `syscall.O_RDONLY` |
| 273 | `parent` | `syscall.O_DIRECTORY` |
| 273 | `parent` | `syscall.O_NOFOLLOW` |
| 273 | `parent` | `syscall.O_CLOEXEC` |
| 276 | `parent` | `syscall.Close` |
| 278 | `parent` | `syscall.ELOOP` |
| 278 | `parent` | `syscall.ENOTDIR` |
| 300 | `read` | `syscall.Close` |
| 301 | `read` | `syscall.Openat` |
| 303 | `read` | `syscall.O_RDONLY` |
| 303 | `read` | `syscall.O_NOFOLLOW` |
| 303 | `read` | `syscall.O_CLOEXEC` |
| 307 | `read` | `syscall.ELOOP` |
| 312 | `read` | `os.NewFile` |
| 314 | `read` | `syscall.Close` |
| 318 | `read` | `io.ReadAll` |
| 338 | `list` | `syscall.Close` |
| 340 | `list` | `syscall.Openat` |
| 342 | `list` | `syscall.O_RDONLY` |
| 342 | `list` | `syscall.O_DIRECTORY` |
| 342 | `list` | `syscall.O_NOFOLLOW` |
| 342 | `list` | `syscall.O_CLOEXEC` |
| 346 | `list` | `syscall.ELOOP` |
| 346 | `list` | `syscall.ENOTDIR` |
| 355 | `list` | `os.NewFile` |
| 357 | `list` | `syscall.Close` |
| 384 | `write` | `syscall.Close` |
| 385 | `write` | `syscall.Openat` |
| 387 | `write` | `syscall.O_WRONLY` |
| 387 | `write` | `syscall.O_CREAT` |
| 387 | `write` | `syscall.O_TRUNC` |
| 387 | `write` | `syscall.O_NOFOLLOW` |
| 387 | `write` | `syscall.O_CLOEXEC` |
| 391 | `write` | `syscall.ELOOP` |
| 396 | `write` | `os.NewFile` |
| 398 | `write` | `syscall.Close` |
| 423 | `delete` | `syscall.Close` |
| 424 | `delete` | `syscall.Openat` |
| 426 | `delete` | `syscall.O_RDONLY` |
| 426 | `delete` | `syscall.O_NOFOLLOW` |
| 426 | `delete` | `syscall.O_CLOEXEC` |
| 430 | `delete` | `syscall.ELOOP` |
| 435 | `delete` | `syscall.Close` |
| 436 | `delete` | `filepath.Join` |
| 437 | `delete` | `os.Lstat` |
| 440 | `delete` | `os.Remove` |
| 528 | `ksCallMethod` | `os.LookupEnv` |

## §12 / acceptance

- **PROTECTS AGAINST:** None directly; this is an inventory, not an enforcement path.
- **DOES NOT PROTECT:** Host compromise, unguarded calls, unused code in binaries, runtime escape, or broad imports.
- **ASSUMPTIONS:** Main source is the intended template; extraction does not resolve Go type semantics or reachability.
- **FAILURE MODE:** A call exists outside the template, generated code changes, or lexical function attribution is wrong.

**A/B:** Preparatory B measurement only; measured blast-radius reduction: none. **Syntax change:** no. **Runtime counterpart:** not yet tested. **P-level:** P0.1; no new Python modules. **Acceptance:** open until generated fixture and compiled binary are inspected. **Tests executed:** 0; real failures and infrastructure failures unmeasured.

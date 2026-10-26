"""Linux native-Go implementation for bounded exact-object persistence v1.

This adapter mirrors the interpreter's authority and commit protocol without
falling back to broad path-based disk helpers. The exact parent directory is
anchored in a descriptor when PersistRoot is narrowed. Load/commit operate only
against that descriptor plus the sealed basename.

The deadline remains the same cooperative sequence deadline used by the
interpreter: checks surround syscalls but do not claim safe kernel-syscall
preemption. Stdlib promotion therefore remains separate from native source parity.
"""

from __future__ import annotations

import sys

from . import codegen_go as _codegen
from . import persistence_authority_v1 as _authority
from .ast_nodes import MemberExpression, SourceLocation

_INSTALLED = False
_ORIGINAL_VALIDATE = None
_ORIGINAL_GENERATE = None


_GO_PERSIST_HELPERS = r'''
const ksPersistMaxBytes int64 = 16 * 1024 * 1024
const ksPersistMaxDeadlineMs int64 = 120000
const ksPersistChunkBytes int = 64 * 1024

type ksPersistRoot struct{}

type ksPersistPolicy struct {
	path       string
	maxBytes   int64
	deadlineMs int64
}

type ksPersistCaps struct {
	policy   ksPersistPolicy
	parentFD int
	name     string
}

func ksPersistContract(message string) *KsError {
	return &KsError{Message: "KS3420: " + message}
}

func ksPersistBudget(message string) *KsError {
	return &KsError{Message: "KS3421: " + message}
}

func ksPersistDeadline(message string) *KsError {
	return &KsError{Message: "KS3422: " + message}
}

func ksPersistUncertain(message string) *KsError {
	return &KsError{Message: "KS3423: " + message}
}

func ksPersistIO(message string) *KsError {
	return &KsError{Message: "KS3424: " + message}
}

func ksPersistIntArgument(method string, arguments []any, index int) (int64, *KsError) {
	if index >= len(arguments) {
		return 0, &KsError{Message: "KS1301: Eksik Int metot argümanı: " + method}
	}
	value, ok := arguments[index].(int64)
	if !ok {
		return 0, &KsError{Message: "KS2420: Persist bütçeleri Int olmalıdır"}
	}
	return value, nil
}

func ksPersistCanonicalPath(raw string) (string, bool) {
	if strings.IndexByte(raw, 0) >= 0 {
		return "", false
	}
	text := strings.TrimSpace(raw)
	if text == "" || !filepath.IsAbs(text) {
		return "", false
	}
	canonical := filepath.Clean(text)
	if canonical == string(os.PathSeparator) {
		return "", false
	}
	name := filepath.Base(canonical)
	if name == "" || name == "." || name == ".." {
		return "", false
	}
	return canonical, true
}

func ksPersistOpenParent(path string) (int, string, *KsError) {
	if runtime.GOOS != "linux" {
		return -1, "", ksPersistIO("native persistence descriptor ABI yalnızca Linux hedefinde desteklenir")
	}
	canonical, ok := ksPersistCanonicalPath(path)
	if !ok {
		return -1, "", &KsError{Message: "KS2421: Persist exact_file absolute regular-file hedefi olmalıdır"}
	}
	parent := filepath.Dir(canonical)
	name := filepath.Base(canonical)

	current, err := syscall.Open(
		string(os.PathSeparator),
		syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		return -1, "", ksPersistIO("persistence root descriptor açılamadı: " + err.Error())
	}

	trimmed := strings.TrimPrefix(parent, string(os.PathSeparator))
	if trimmed == "" {
		return current, name, nil
	}
	for _, component := range strings.Split(trimmed, string(os.PathSeparator)) {
		if component == "" || component == "." || component == ".." {
			_ = syscall.Close(current)
			return -1, "", ksPersistContract("persistence parent canonical component geçersiz")
		}
		next, err := syscall.Openat(
			current,
			component,
			syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
			0,
		)
		if err != nil {
			_ = syscall.Close(current)
			return -1, "", ksPersistIO("persistence parent component açılamadı: " + err.Error())
		}
		_ = syscall.Close(current)
		current = next
	}
	return current, name, nil
}

func ksPersistAllow(arguments []any) any {
	if failure := ksMethodArity("allow", arguments, 3); failure != nil {
		return failure
	}
	path, failure := ksStringArgument("allow", arguments, 0)
	if failure != nil {
		return failure
	}
	maxBytes, failure := ksPersistIntArgument("allow", arguments, 1)
	if failure != nil { return failure }
	deadlineMs, failure := ksPersistIntArgument("allow", arguments, 2)
	if failure != nil { return failure }

	canonical, ok := ksPersistCanonicalPath(path)
	if !ok {
		return ksErrorf("KS2421: Persist exact_file absolute regular-file hedefi olmalıdır")
	}
	if maxBytes < 1 || maxBytes > ksPersistMaxBytes {
		return ksErrorf("KS2421: Persist max_bytes güvenlik sınırı dışında")
	}
	if deadlineMs < 1 || deadlineMs > ksPersistMaxDeadlineMs {
		return ksErrorf("KS2421: Persist deadline_ms güvenlik sınırı dışında")
	}

	parentFD, name, openFailure := ksPersistOpenParent(canonical)
	if openFailure != nil {
		return openFailure
	}
	capability := &ksPersistCaps{
		policy: ksPersistPolicy{
			path: canonical,
			maxBytes: maxBytes,
			deadlineMs: deadlineMs,
		},
		parentFD: parentFD,
		name: name,
	}
	runtime.SetFinalizer(capability, func(item *ksPersistCaps) {
		if item.parentFD >= 0 {
			_ = syscall.Close(item.parentFD)
			item.parentFD = -1
		}
	})
	return capability
}

func ksPersistDupParent(capability *ksPersistCaps) (int, *KsError) {
	if capability == nil || capability.parentFD < 0 {
		return -1, ksPersistIO("persistence parent descriptor is unavailable")
	}
	fd, err := syscall.Dup(capability.parentFD)
	if err != nil {
		return -1, ksPersistIO("persistence parent descriptor duplication failed: " + err.Error())
	}
	return fd, nil
}

func ksPersistExpired(deadline time.Time, stage string) *KsError {
	if time.Now().After(deadline) {
		return ksPersistDeadline("persistence sequence deadline exceeded at " + stage)
	}
	return nil
}

func ksPersistTargetShape(parentFD int, name string) *KsError {
	fd, err := syscall.Openat(
		parentFD,
		name,
		syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		if errors.Is(err, syscall.ENOENT) {
			return nil
		}
		if errors.Is(err, syscall.ELOOP) {
			return ksPersistContract("persistence target may not be a symbolic link")
		}
		return ksPersistIO("target metadata open failed: " + err.Error())
	}
	defer syscall.Close(fd)
	var info syscall.Stat_t
	if err := syscall.Fstat(fd, &info); err != nil {
		return ksPersistIO("target metadata read failed: " + err.Error())
	}
	if info.Mode&syscall.S_IFMT != syscall.S_IFREG {
		return ksPersistContract("persistence target must be a regular file when it exists")
	}
	return nil
}

func ksPersistLoad(capability *ksPersistCaps) any {
	deadline := time.Now().Add(time.Duration(capability.policy.deadlineMs) * time.Millisecond)
	if failure := ksPersistExpired(deadline, "load-start"); failure != nil { return failure }

	parentFD, failure := ksPersistDupParent(capability)
	if failure != nil { return failure }
	defer syscall.Close(parentFD)

	if shapeFailure := ksPersistTargetShape(parentFD, capability.name); shapeFailure != nil {
		return shapeFailure
	}
	if failure := ksPersistExpired(deadline, "load-open"); failure != nil { return failure }
	fd, err := syscall.Openat(
		parentFD,
		capability.name,
		syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
		0,
	)
	if err != nil {
		if errors.Is(err, syscall.ELOOP) {
			return ksPersistContract("persistence target may not be a symbolic link")
		}
		if errors.Is(err, syscall.ENOENT) {
			return ksPersistIO("persistence state object does not exist")
		}
		return ksPersistIO("persistence state open failed: " + err.Error())
	}
	defer syscall.Close(fd)

	var info syscall.Stat_t
	if err := syscall.Fstat(fd, &info); err != nil {
		return ksPersistIO("persistence state stat failed: " + err.Error())
	}
	if info.Mode&syscall.S_IFMT != syscall.S_IFREG {
		return ksPersistContract("opened persistence target is not a regular file")
	}
	if info.Size > capability.policy.maxBytes {
		return ksPersistBudget("persisted state exceeds max_bytes")
	}

	buffer := make([]byte, 0, int(min(capability.policy.maxBytes, int64(4096))))
	chunk := make([]byte, ksPersistChunkBytes)
	for {
		if failure := ksPersistExpired(deadline, "load-read"); failure != nil { return failure }
		remaining := capability.policy.maxBytes + 1 - int64(len(buffer))
		if remaining <= 0 {
			return ksPersistBudget("persisted state exceeds max_bytes")
		}
		readSize := len(chunk)
		if int64(readSize) > remaining { readSize = int(remaining) }
		n, err := syscall.Read(fd, chunk[:readSize])
		if failure := ksPersistExpired(deadline, "load-read-complete"); failure != nil { return failure }
		if n > 0 {
			buffer = append(buffer, chunk[:n]...)
			if int64(len(buffer)) > capability.policy.maxBytes {
				return ksPersistBudget("persisted state exceeds max_bytes")
			}
		}
		if err != nil {
			return ksPersistIO("persistence state read failed: " + err.Error())
		}
		if n == 0 { break }
	}
	if !utf8.Valid(buffer) {
		return ksPersistContract("persisted state is not valid UTF-8")
	}
	return string(buffer)
}

func ksPersistTempName() (string, *KsError) {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return "", ksPersistIO("persistence temp randomness failed: " + err.Error())
	}
	return ".koschei-persist-" + hex.EncodeToString(raw), nil
}

func ksPersistCommit(capability *ksPersistCaps, value any) any {
	payload, ok := value.(string)
	if !ok {
		return ksPersistContract("PersistCaps.commit() value must be String")
	}
	encoded := []byte(payload)
	if !utf8.Valid(encoded) {
		return ksPersistContract("PersistCaps.commit() value is not valid UTF-8")
	}
	if int64(len(encoded)) > capability.policy.maxBytes {
		return ksPersistBudget("commit payload exceeds max_bytes")
	}

	deadline := time.Now().Add(time.Duration(capability.policy.deadlineMs) * time.Millisecond)
	if failure := ksPersistExpired(deadline, "commit-start"); failure != nil { return failure }

	parentFD, failure := ksPersistDupParent(capability)
	if failure != nil { return failure }
	defer syscall.Close(parentFD)
	if shapeFailure := ksPersistTargetShape(parentFD, capability.name); shapeFailure != nil {
		return shapeFailure
	}

	tempFD := -1
	tempName := ""
	replaced := false
	defer func() {
		if tempFD >= 0 { _ = syscall.Close(tempFD) }
		if tempName != "" && !replaced { _ = syscall.Unlinkat(parentFD, tempName) }
	}()

	for attempt := 0; attempt < 16; attempt++ {
		if failure := ksPersistExpired(deadline, "temp-create"); failure != nil { return failure }
		candidate, randomFailure := ksPersistTempName()
		if randomFailure != nil { return randomFailure }
		fd, err := syscall.Openat(
			parentFD,
			candidate,
			syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,
			0600,
		)
		if err == nil {
			tempFD = fd
			tempName = candidate
			break
		}
		if errors.Is(err, syscall.EEXIST) { continue }
		return ksPersistIO("persistence temp create failed: " + err.Error())
	}
	if tempFD < 0 || tempName == "" {
		return ksPersistIO("persistence temp name allocation exhausted")
	}

	for offset := 0; offset < len(encoded); {
		if failure := ksPersistExpired(deadline, "temp-write"); failure != nil { return failure }
		end := offset + ksPersistChunkBytes
		if end > len(encoded) { end = len(encoded) }
		n, err := syscall.Write(tempFD, encoded[offset:end])
		if failure := ksPersistExpired(deadline, "temp-write-complete"); failure != nil { return failure }
		if err != nil {
			return ksPersistIO("persistence temp write failed: " + err.Error())
		}
		if n <= 0 {
			return ksPersistIO("persistence temp write made no progress")
		}
		offset += n
	}

	if failure := ksPersistExpired(deadline, "temp-fsync"); failure != nil { return failure }
	if err := syscall.Fsync(tempFD); err != nil {
		return ksPersistIO("persistence temp fsync failed: " + err.Error())
	}
	if failure := ksPersistExpired(deadline, "temp-fsync-complete"); failure != nil { return failure }
	if err := syscall.Close(tempFD); err != nil {
		return ksPersistIO("persistence temp close failed: " + err.Error())
	}
	tempFD = -1

	if failure := ksPersistExpired(deadline, "atomic-replace"); failure != nil { return failure }
	if err := syscall.Renameat(parentFD, tempName, parentFD, capability.name); err != nil {
		return ksPersistIO("persistence atomic replace failed: " + err.Error())
	}
	replaced = true
	tempName = ""

	if time.Now().After(deadline) {
		return ksPersistUncertain("state was atomically replaced but directory durability was not confirmed before deadline")
	}
	if err := syscall.Fsync(parentFD); err != nil {
		return ksPersistUncertain("state was atomically replaced but directory fsync failed: " + err.Error())
	}
	if time.Now().After(deadline) {
		return ksPersistUncertain("state was atomically replaced but durability confirmation exceeded deadline")
	}
	return ksUnit
}

'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        if new in source:
            return source
        raise RuntimeError(f"Persist Go runtime layout changed at {label}; patch failed closed.")
    return source.replace(old, new, 1)


def _patch_capability_runtime() -> None:
    source = _codegen.CAPABILITY_RUNTIME

    source = _replace_once(
        source,
        '''type ksSystemCaps struct {
\tnet     *ksNetRoot
\tdisk    *ksDiskRoot
\tenv     *ksEnvRoot
\tprocess *ksProcessRoot
\tserve   *ksServeRoot
}''',
        '''type ksSystemCaps struct {
\tnet     *ksNetRoot
\tdisk    *ksDiskRoot
\tenv     *ksEnvRoot
\tprocess *ksProcessRoot
\tserve   *ksServeRoot
\tpersist *ksPersistRoot
}''',
        "SystemCaps persistence field",
    )

    source = _replace_once(
        source,
        '''\tcase *ksSystemCaps, *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps, *ksProcessCaps, *ksServeCaps:''',
        '''\tcase *ksSystemCaps, *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot, *ksPersistRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps, *ksProcessCaps, *ksServeCaps, *ksPersistCaps:''',
        "capability containment",
    )

    source = _replace_once(
        source,
        '''\t\tserve:   &ksServeRoot{},
\t}''',
        '''\t\tserve:   &ksServeRoot{},
\t\tpersist: &ksPersistRoot{},
\t}''',
        "SystemCaps persistence constructor",
    )

    source = _replace_once(
        source,
        '''\t\tcase "serve":
\t\t\treturn item.serve
\t\t}''',
        '''\t\tcase "serve":
\t\t\treturn item.serve
\t\tcase "persist":
\t\t\treturn item.persist
\t\t}''',
        "SystemCaps persistence member",
    )

    anchor = "func ksCallMethod(receiver any, method string, arguments ...any) any {"
    if "func ksPersistCommit(" not in source:
        source = _replace_once(
            source,
            anchor,
            _GO_PERSIST_HELPERS.replace("\\t", "\t") + anchor,
            "persistence helper insertion",
        )

    source = _replace_once(
        source,
        '''\tswitch item := receiver.(type) {
\tcase *ksServeRoot:''',
        '''\tswitch item := receiver.(type) {
\tcase *ksPersistRoot:
\t\tif method != "allow" {
\t\t\treturn ksErrorf("KS2402: PersistRoot önce exact object policy ile allow kullanmalıdır.")
\t\t}
\t\treturn ksPersistAllow(arguments)
\tcase *ksPersistCaps:
\t\tswitch method {
\t\tcase "load":
\t\t\tif failure := ksMethodArity(method, arguments, 0); failure != nil { return failure }
\t\t\treturn ksPersistLoad(item)
\t\tcase "commit":
\t\t\tif failure := ksMethodArity(method, arguments, 1); failure != nil { return failure }
\t\t\treturn ksPersistCommit(item, arguments[0])
\t\tdefault:
\t\t\treturn ksErrorf("KS2404: PersistCaps yetkisi '" + method + "' işlemine izin vermez.")
\t\t}
\tcase *ksServeRoot:''',
        "persistence method dispatch",
    )

    source = _replace_once(
        source,
        '''\tcase *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps,
\t\t*ksProcessCaps, *ksServeCaps, *ksResponse:''',
        '''\tcase *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot, *ksPersistRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps,
\t\t*ksProcessCaps, *ksServeCaps, *ksPersistCaps, *ksResponse:''',
        "dynamic persistence method dispatch",
    )

    _codegen.CAPABILITY_RUNTIME = source


def _uses_persistence(program) -> bool:
    for declaration in program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"PersistRoot", "PersistCaps"} for name in parameter.type_ref.names):
                return True
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member in {
                    "persist",
                    "load",
                    "commit",
                }:
                    return True
    return False


def _validate_capability_backend(self) -> None:
    if not _uses_persistence(self.program):
        return _ORIGINAL_VALIDATE(self)
    if not sys.platform.startswith("linux"):
        raise _codegen.CodegenError(
            "KS4001",
            "Native bounded persistence v1 şu anda yalnızca Linux descriptor-relative hedefinde desteklenir.",
            SourceLocation(1, 1),
        )
    # Skip persistence_authority_v1's intentional pre-native rejection, while
    # retaining the full Serve/Disk/backend validator chain that existed before it.
    return _authority._ORIGINAL_CODEGEN_VALIDATE(self)


def _generate_with_persistence_imports(self) -> str:
    source = _ORIGINAL_GENERATE(self)
    imports = (
        ('\t"crypto/rand"\n', '\t"errors"\n'),
        ('\t"encoding/hex"\n', '\t"errors"\n'),
    )
    for wanted, marker in imports:
        if wanted in source:
            continue
        if marker not in source:
            raise RuntimeError("Go errors import missing; persistence import patch failed closed.")
        source = source.replace(marker, wanted + marker, 1)
    return source


def install_persistence_native_go_v1() -> None:
    global _INSTALLED, _ORIGINAL_VALIDATE, _ORIGINAL_GENERATE
    if _INSTALLED:
        return

    _codegen.NATIVE_CAPABILITY_METHODS.update({"load", "commit"})
    _patch_capability_runtime()

    _ORIGINAL_VALIDATE = _codegen.GoCodegen._validate_capability_backend
    _codegen.GoCodegen._validate_capability_backend = _validate_capability_backend

    _ORIGINAL_GENERATE = _codegen.GoCodegen.generate
    _codegen.GoCodegen.generate = _generate_with_persistence_imports

    _INSTALLED = True

"""PersistCaps for native binaries, through the capability broker.

The confined worker cannot open files, so ``PersistRoot.allow``, ``load`` and
``commit`` are broker requests. The broker runs the exact-object persistence
protocol of the earlier AST-Go backend: the parent directory is anchored by
descriptor when the token is narrowed, the final object must be a regular file
with one name, commits write a fresh 0600 temporary beside it, fsync it,
rename it over the target and fsync the directory, and errors carry the same
KS342x codes and messages as the interpreter (docs/BOUNDED_PERSISTENCE_*.md).

That protocol's Go source is taken from ``codegen_go.CAPABILITY_RUNTIME``
after the persistence integrity patches are installed, so this backend and the
reviewed Go implementation cannot drift apart: if the layout changes, building
the runtime fails instead of emitting a different protocol.

Linux only, like the broker's confinement.
"""

from __future__ import annotations

import re

PERSIST_IMPORTS = ("errors", "path/filepath", "unicode/utf8")

# Declarations taken verbatim from the patched AST-Go runtime.
_TAKEN = (
    "const ksPersistMaxBytes",
    "const ksPersistMaxDeadlineMs",
    "const ksPersistChunkBytes",
    "const ksPersistOPath",
    "type ksPersistPolicy",
    "type ksPersistCaps",
    "func ksPersistContract",
    "func ksPersistBudget",
    "func ksPersistDeadline",
    "func ksPersistUncertain",
    "func ksPersistIO",
    "func ksPersistCanonicalPath",
    "func ksPersistDupParent",
    "func ksPersistExpired",
    "func ksPersistTargetShape",
    "func ksPersistLoad",
    "func ksPersistTempName",
    "func ksPersistCommit",
)


def _declarations(source: str) -> dict[str, str]:
    """Split Go source into top-level declarations keyed by their first words."""

    found: dict[str, str] = {}
    starts = [match.start() for match in re.finditer(r"^(?:func|const|type|var) ", source, re.M)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(source)
        chunk = source[start:end]
        # Drop trailing comment lines that belong to the next declaration.
        lines = chunk.rstrip().split("\n")
        while lines and lines[-1].startswith("//"):
            lines.pop()
        chunk = "\n".join(lines).rstrip() + "\n"
        head = re.match(r"(func|const|type|var) (\w+)", chunk)
        if head:
            found[f"{head.group(1)} {head.group(2)}"] = chunk
    return found


def _protocol_source() -> str:
    import koschei  # noqa: F401  (installs the persistence patches)
    from . import codegen_go

    declarations = _declarations(codegen_go.CAPABILITY_RUNTIME)
    missing = [name for name in _TAKEN if name not in declarations]
    if missing:
        raise RuntimeError(
            "native persistence: the AST-Go persistence runtime changed layout "
            f"(missing {', '.join(missing)}); refusing to build a different protocol"
        )
    shape = declarations["func ksPersistTargetShape"]
    regular = (
        "\tif info.Mode&syscall.S_IFMT != syscall.S_IFREG {\n"
        '\t\treturn ksPersistContract("persistence target must be a regular file when it exists")'
    )
    if shape.count(regular) != 1:
        raise RuntimeError("native persistence: ksPersistTargetShape changed layout")
    # O_PATH|O_NOFOLLOW opens a symlink itself instead of failing with ELOOP,
    # so name the symlink case the way the interpreter does (lstat first).
    declarations["func ksPersistTargetShape"] = shape.replace(
        regular,
        "\tif info.Mode&syscall.S_IFMT == syscall.S_IFLNK {\n"
        '\t\treturn ksPersistContract("persistence target may not be a symbolic link")\n'
        "\t}\n" + regular,
    )
    return "\n".join(declarations[name] for name in _TAKEN)


_SHIMS = r'''
// The protocol below reports errors as *KsError and success as ksUnit, the
// AST-Go backend's types; the broker turns them into frames.
type KsError struct {
	Message string
}

type ksUnitValue struct{}

var ksUnit = ksUnitValue{}
'''

_WORKER = r'''
// ---- native persistence (native_persist_v1): worker side --------------

func _ksCapsPersist(receiver any) any {
	if _, ok := receiver.(_ksSystemCaps); !ok {
		_ksAbort("KS5002", "SystemCaps.persist receiver drifted")
	}
	return _ksPersistRoot{}
}

// persistence_authority_v1._runtime_policy, in the same order.
func _ksPersistAllow(receiver any, path any, maxBytes any, deadlineMs any) any {
	if _, ok := receiver.(_ksPersistRoot); !ok {
		_ksAbort("KS5002", "PersistRoot receiver drifted")
	}
	text, ok := path.(string)
	if !ok {
		return _ksError{message: "KS2420: Persist exact_file String olmalıdır"}
	}
	canonical, ok := ksPersistCanonicalPath(text)
	if !ok {
		return _ksError{message: "KS2421: Persist exact_file absolute regular-file hedefi olmalıdır"}
	}
	budget, okBytes := maxBytes.(int64)
	deadline, okDeadline := deadlineMs.(int64)
	if !okBytes || !okDeadline {
		return _ksError{message: "KS2420: Persist bütçeleri Int olmalıdır"}
	}
	if budget < 1 || budget > ksPersistMaxBytes {
		return _ksError{message: "KS2421: Persist max_bytes güvenlik sınırı dışında"}
	}
	if deadline < 1 || deadline > ksPersistMaxDeadlineMs {
		return _ksError{message: "KS2421: Persist deadline_ms güvenlik sınırı dışında"}
	}
	_, answer := _ksAsk("persist_open", canonical, strconv.FormatInt(budget, 10), strconv.FormatInt(deadline, 10))
	token := &_ksPersistCaps{handle: answer[0]}
	runtime.SetFinalizer(token, func(token *_ksPersistCaps) { _ksQueueRelease("persist_release", token.handle) })
	return token
}

func _ksPersistHandleOf(receiver any) string {
	token, ok := receiver.(*_ksPersistCaps)
	if !ok {
		_ksAbort("KS5002", "PersistCaps receiver drifted")
	}
	return token.handle
}

func _ksPersistLoad(receiver any) any {
	done, answer := _ksAsk("persist_load", _ksPersistHandleOf(receiver))
	runtime.KeepAlive(receiver)
	if !done {
		return _ksError{message: answer[0]}
	}
	return answer[0]
}

func _ksPersistCommit(receiver any, value any) any {
	text, ok := value.(string)
	if !ok {
		_ksAbort("KS5002", "PersistCaps.commit value drifted")
	}
	done, answer := _ksAsk("persist_commit", _ksPersistHandleOf(receiver), text)
	runtime.KeepAlive(receiver)
	if !done {
		return _ksError{message: answer[0]}
	}
	return _ksUnit{}
}

// ---- native persistence: broker side ----------------------------------

var _ksPersistTokens = map[string]*ksPersistCaps{}
var _ksPersistNext = 0

// bounded_persistence_v1._open_exact_parent: open "/" and then each parent
// component with O_DIRECTORY|O_NOFOLLOW. A failure is reported the way the
// interpreter reports Python's OSError: "[Errno N] Strerror: 'component'".
func _ksPersistOpenParentLikePython(path string) (int, string, string) {
	parent, name := filepath.Dir(path), filepath.Base(path)
	flags := syscall.O_RDONLY | syscall.O_DIRECTORY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC
	fail := func(err error, component string) (int, string, string) {
		code := _ksAsErrno(err)
		text := code.Error()
		if text != "" {
			text = strings.ToUpper(text[:1]) + text[1:]
		}
		quoted := "'" + component + "'"
		if strings.Contains(component, "'") && !strings.Contains(component, "\"") {
			quoted = "\"" + component + "\""
		}
		return -1, name, "KS3424: persistence parent could not be anchored: [Errno " +
			strconv.Itoa(int(code)) + "] " + text + ": " + quoted
	}
	current, err := syscall.Open("/", flags, 0)
	if err != nil {
		return fail(err, "/")
	}
	for _, component := range strings.Split(parent, "/") {
		if component == "" {
			continue
		}
		next, err := syscall.Openat(current, component, flags, 0)
		_ = syscall.Close(current)
		if err != nil {
			return fail(err, component)
		}
		current = next
	}
	return current, name, ""
}

func _ksPersistAnswer(result any) []string {
	switch value := result.(type) {
	case *KsError:
		return []string{"error", value.Message}
	case string:
		return []string{"ok", value}
	case ksUnitValue:
		return []string{"ok"}
	}
	return []string{"error", "KS3424: persistence returned an unexpected value"}
}

// Runs on the broker goroutine only; requests arrive one at a time.
func _ksBrokerPersistServe(request []string) ([]string, bool) {
	switch {
	case request[0] == "persist_open" && len(request) == 4:
		budget, errBytes := strconv.ParseInt(request[2], 10, 64)
		deadline, errDeadline := strconv.ParseInt(request[3], 10, 64)
		canonical, ok := ksPersistCanonicalPath(request[1])
		if errBytes != nil || errDeadline != nil || !ok || canonical != request[1] ||
			budget < 1 || budget > ksPersistMaxBytes || deadline < 1 || deadline > ksPersistMaxDeadlineMs {
			return nil, false
		}
		parentFD, name, failure := _ksPersistOpenParentLikePython(canonical)
		token := &ksPersistCaps{
			policy:   ksPersistPolicy{path: canonical, maxBytes: budget, deadlineMs: deadline},
			parentFD: parentFD,
			name:     name,
		}
		if failure != "" {
			token.parentFD = -1
			token.name = filepath.Base(canonical)
			token.openError = failure
		}
		_ksPersistNext++
		handle := strconv.Itoa(_ksPersistNext)
		_ksPersistTokens[handle] = token
		return []string{"ok", handle}, true
	case request[0] == "persist_release" && len(request) == 2:
		token, ok := _ksPersistTokens[request[1]]
		if !ok {
			return nil, false
		}
		if token.parentFD >= 0 {
			_ = syscall.Close(token.parentFD)
		}
		delete(_ksPersistTokens, request[1])
		return []string{"ok"}, true
	case request[0] == "persist_load" && len(request) == 2:
		token, ok := _ksPersistTokens[request[1]]
		if !ok {
			return nil, false
		}
		return _ksPersistAnswer(ksPersistLoad(token)), true
	case request[0] == "persist_commit" && len(request) == 3:
		token, ok := _ksPersistTokens[request[1]]
		if !ok {
			return nil, false
		}
		return _ksPersistAnswer(ksPersistCommit(token, request[2])), true
	}
	return nil, false
}

func init() {
	_ksBrokerPersist = _ksBrokerPersistServe
}
'''


def persist_runtime() -> str:
    return _SHIMS + "\n" + _protocol_source() + "\n" + _WORKER

"""Native capability broker v1 (readiness gate G2, first step).

A native binary that uses read-only disk or environment authority runs as two
processes:

* the **broker** is the process the user started. It keeps the authority: the
  environment, the current directory and the right to open files. It starts
  the worker, answers its requests and exits with the worker's status.
* the **worker** runs the program. It starts with an empty environment, checks
  that descriptor 3 is its socket to the broker, and before any program code
  runs it confines itself with a seccomp allow list (``no_new_privs``, all
  threads, :data:`ALLOWED_SYSCALLS_AMD64`): opening files, sockets, ``exec``,
  ``fork``, writing to the file system, ``ptrace``, signalling other processes
  and every call not listed fail with ``EPERM``. Every disk read, directory listing and environment lookup is a
  request to the broker.

The broker applies exactly the interpreter's rules (``interpreter.py``): the
scope root is resolved with Python's ``realpath`` and opened once when the
token is narrowed; a path is made absolute and relative with Python's
``abspath``/``relpath``; every component is opened with ``O_NOFOLLOW``
relative to the previous one, ``..`` cannot leave the scope, symlinks are
refused (``KS3405``), errors name the errno symbolically, a file holds at most
16 MiB, text must be UTF-8 and directory names must be UTF-8.

Confinement is implemented for ``linux/amd64``; any other target refuses to
build such a program. Disk writes and the network stay closed (``KS4004``).
"""

from __future__ import annotations

from .interpreter import DISK_ERRNO_NAMES
from .value_budget_v1 import BYTES_MESSAGE, LIST_MESSAGE, MAX_LIST_ITEMS, MAX_STRING_BYTES, STRING_MESSAGE

# x86-64 system calls the worker may make once confined: what the Go runtime
# and the program need, nothing that names a path, opens a descriptor to the
# outside, creates a process or reaches another process. Every other call
# fails with EPERM (clone3 with ENOSYS, so callers fall back to clone); a
# foreign architecture or the x32 ABI kills the worker.
ALLOWED_SYSCALLS_AMD64 = {
    "read": 0, "write": 1, "close": 3, "fstat": 5, "lseek": 8, "mmap": 9, "mprotect": 10,
    "munmap": 11, "brk": 12, "rt_sigaction": 13, "rt_sigprocmask": 14, "rt_sigreturn": 15,
    "readv": 19, "writev": 20, "sched_yield": 24, "mremap": 25, "madvise": 28,
    "nanosleep": 35, "getpid": 39, "exit": 60, "uname": 63, "fcntl": 72,
    "gettimeofday": 96, "getrlimit": 97, "sigaltstack": 131, "gettid": 186, "time": 201,
    "futex": 202, "sched_getaffinity": 204, "restart_syscall": 219, "clock_gettime": 228,
    "clock_getres": 229, "clock_nanosleep": 230, "exit_group": 231, "epoll_wait": 232,
    "epoll_ctl": 233, "epoll_pwait": 281, "eventfd2": 290, "epoll_create1": 291,
    "pipe2": 293, "getrandom": 318, "epoll_pwait2": 441,
    # glibc's per-thread setup, for binaries that link it (cgo's resolver).
    "set_tid_address": 218, "set_robust_list": 273, "rseq": 334,
}
# Allowed only with a checked first argument.
CLONE_SYSCALL = 56  # threads only: CLONE_THREAD must be set (no fork)
CLONE_THREAD = 0x10000
SELF_SIGNAL_SYSCALLS = {"kill": 62, "tgkill": 234}  # only the worker's own pid
PRLIMIT_SYSCALL = 302  # only pid 0, the worker itself
CLONE3_SYSCALL = 435

_RET_KILL = 0x80000000
_RET_ALLOW = 0x7FFF0000
_RET_EPERM = 0x00050000 | 1
_RET_ENOSYS = 0x00050000 | 38
_AUDIT_ARCH_X86_64 = 0xC000003E
_LD_ABS = 0x20  # BPF_LD | BPF_W | BPF_ABS
_JEQ = 0x15  # BPF_JMP | BPF_JEQ | BPF_K
_JGE = 0x35  # BPF_JMP | BPF_JGE | BPF_K
_JSET = 0x45  # BPF_JMP | BPF_JSET | BPF_K
_RET = 0x06  # BPF_RET | BPF_K
_NR, _ARCH, _ARG0 = 0, 4, 16  # struct seccomp_data offsets (low half of args[0])


def seccomp_filter() -> tuple[list[tuple[int, int, int, int]], list[int]]:
    """The worker's filter as (code, jt, jf, k) and the indices whose k is the pid."""

    program: list[tuple[int, object, object, int]] = []
    pid_slots: list[int] = []

    def emit(code: int, k: int, jt: object = 0, jf: object = 0) -> int:
        program.append((code, jt, jf, k))
        return len(program) - 1

    emit(_LD_ABS, _ARCH)
    emit(_JEQ, _AUDIT_ARCH_X86_64, 0, "kill")
    emit(_LD_ABS, _NR)
    emit(_JGE, 0x40000000, "kill", 0)
    for number in sorted(ALLOWED_SYSCALLS_AMD64.values()):
        emit(_JEQ, number, "allow", 0)
    emit(_JEQ, CLONE3_SYSCALL, "enosys", 0)
    emit(_JEQ, CLONE_SYSCALL, 0, "not_clone")
    emit(_LD_ABS, _ARG0)
    emit(_JSET, CLONE_THREAD, "allow", "eperm")
    labels = {"not_clone": len(program)}
    emit(_JEQ, PRLIMIT_SYSCALL, 0, "not_prlimit")
    emit(_LD_ABS, _ARG0)
    emit(_JEQ, 0, "allow", "eperm")
    labels["not_prlimit"] = len(program)
    signals = sorted(SELF_SIGNAL_SYSCALLS.values())
    emit(_JEQ, signals[0], "self", 0)
    emit(_JEQ, signals[1], "self", "eperm")
    labels["self"] = len(program)
    emit(_LD_ABS, _ARG0)
    pid_slots.append(emit(_JEQ, 0, "allow", "eperm"))
    labels["eperm"] = emit(_RET, _RET_EPERM)
    labels["allow"] = emit(_RET, _RET_ALLOW)
    labels["enosys"] = emit(_RET, _RET_ENOSYS)
    labels["kill"] = emit(_RET, _RET_KILL)

    resolved = []
    for index, (code, jt, jf, k) in enumerate(program):
        def target(value: object) -> int:
            if isinstance(value, int):
                return value
            offset = labels[value] - index - 1
            assert 0 <= offset <= 255, (value, offset)
            return offset
        resolved.append((code, target(jt), target(jf), k))
    return resolved, pid_slots


def _filter_source() -> tuple[str, str]:
    program, pid_slots = seccomp_filter()
    lines = ",\n".join(
        f"\t\t{{Code: 0x{code:02x}, Jt: {jt}, Jf: {jf}, K: 0x{k:x}}}" for code, jt, jf, k in program
    )
    return lines, ", ".join(str(slot) for slot in pid_slots)


WORKER_ENV = "KOSCHEI_NATIVE_WORKER=v1"

# Messages, identical to interpreter.py.
REJECT_MESSAGE = "KS3402: Disk kapsamı dışında erişim reddedildi: "
SYMLINK_MESSAGE = (
    "KS3402: Disk kapsamı sembolik bağ üzerinden aşılamaz; "
    "KS3405: Kapsam içinde sembolik bağ takip edilmez: "
)
READ_PREFIX = "Dosya okunamadı: "
ROOT_READ_MESSAGE = "Dosya okunamadı: kapsam kökü bir dizindir: "
NOT_TEXT_PREFIX = "Dosya okunamadı: geçerli UTF-8 metin değil: "
LIST_PREFIX = "Dizin listelenemedi: "
WRITE_PREFIX = "Dosya yazılamadı: "
ROOT_WRITE_MESSAGE = "Dosya yazılamadı: kapsam kökü bir dizindir: "
DELETE_PREFIX = "Dosya silinemedi: "
ROOT_DELETE_MESSAGE = "Dosya silinemedi: kapsam kökü silinemez: "
LIST_NAME_PREFIX = "Dizin listelenemedi: geçerli UTF-8 olmayan dosya adı: "
ENV_MISSING_PREFIX = "Ortam değişkeni bulunamadı: "
ENV_NOT_TEXT_PREFIX = "Ortam değişkeni geçerli UTF-8 metin değil: "


def _go(value: str) -> str:
    from .mir_go_native import _go_string

    return _go_string(value)


def broker_runtime() -> str:
    errnos = "\n".join(
        f"\tsyscall.Errno({code}): {_go(name)}," for code, name in sorted(DISK_ERRNO_NAMES.items())
    )
    filter_lines, pid_slots = _filter_source()
    return _BROKER_RUNTIME.format(
        errnos=errnos,
        filter_lines=filter_lines,
        pid_slots=pid_slots,
        worker_env=_go(WORKER_ENV),
        max_bytes=MAX_STRING_BYTES,
        max_items=MAX_LIST_ITEMS,
        bytes_message=_go(BYTES_MESSAGE),
        string_message=_go(STRING_MESSAGE),
        list_message=_go(LIST_MESSAGE),
        reject=_go(REJECT_MESSAGE),
        symlink=_go(SYMLINK_MESSAGE),
        read_prefix=_go(READ_PREFIX),
        root_read=_go(ROOT_READ_MESSAGE),
        not_text=_go(NOT_TEXT_PREFIX),
        list_prefix=_go(LIST_PREFIX),
        write_prefix=_go(WRITE_PREFIX),
        root_write=_go(ROOT_WRITE_MESSAGE),
        delete_prefix=_go(DELETE_PREFIX),
        root_delete=_go(ROOT_DELETE_MESSAGE),
        list_name=_go(LIST_NAME_PREFIX),
        env_missing=_go(ENV_MISSING_PREFIX),
        env_not_text=_go(ENV_NOT_TEXT_PREFIX),
    )


BROKER_IMPORTS = ("crypto/rand", "encoding/hex", "os/exec", "runtime", "sort", "syscall", "unsafe")

_BROKER_RUNTIME = r'''
// ---- native capability broker (native_broker_v1) ----------------------

const _ksBrokerMaxField = {max_bytes} + 1

var _ksErrnoNames = map[syscall.Errno]string{{
{errnos}
}}

var _ksBroker *os.File

// Set by native_net_v1 when the program uses the network.
var _ksBrokerNet func([]string) ([]string, bool)

// Set by native_serve_v1 when the program serves requests.
var _ksBrokerServers func([]string) ([]string, bool)

// Entry: the process the user started becomes the broker; the worker runs
// the program confined.
func _ksBrokerEntry(run func()) {{
	if os.Getenv("KOSCHEI_NATIVE_WORKER") == "v1" {{
		_ksWorkerStart()
		run()
		os.Exit(0)
	}}
	_ksBrokerServe()
}}

// ---- framing: u32 count, then u32 length + bytes per field --------------

func _ksWriteFrame(file *os.File, fields []string) error {{
	size := 4
	for _, field := range fields {{
		size += 4 + len(field)
	}}
	out := make([]byte, 0, size)
	out = append(out, byte(len(fields)>>24), byte(len(fields)>>16), byte(len(fields)>>8), byte(len(fields)))
	for _, field := range fields {{
		n := len(field)
		out = append(out, byte(n>>24), byte(n>>16), byte(n>>8), byte(n))
		out = append(out, field...)
	}}
	_, err := file.Write(out)
	return err
}}

func _ksReadFull(file *os.File, buffer []byte) error {{
	for read := 0; read < len(buffer); {{
		n, err := file.Read(buffer[read:])
		if n == 0 && err != nil {{
			return err
		}}
		read += n
	}}
	return nil
}}

func _ksReadU32(file *os.File) (int, error) {{
	var raw [4]byte
	if err := _ksReadFull(file, raw[:]); err != nil {{
		return 0, err
	}}
	return int(raw[0])<<24 | int(raw[1])<<16 | int(raw[2])<<8 | int(raw[3]), nil
}}

func _ksReadFrame(file *os.File, maxFields int, maxTotal int) ([]string, error) {{
	count, err := _ksReadU32(file)
	if err != nil {{
		return nil, err
	}}
	if count > maxFields {{
		return nil, syscall.EINVAL
	}}
	fields := make([]string, 0, count)
	total := 0
	for index := 0; index < count; index++ {{
		n, err := _ksReadU32(file)
		if err != nil {{
			return nil, err
		}}
		total += n
		if n > _ksBrokerMaxField || total > maxTotal {{
			return nil, syscall.EINVAL
		}}
		buffer := make([]byte, n)
		if err := _ksReadFull(file, buffer); err != nil {{
			return nil, err
		}}
		fields = append(fields, string(buffer))
	}}
	return fields, nil
}}

// ---- worker side --------------------------------------------------------

func _ksWorkerStart() {{
	var info syscall.Stat_t
	if err := syscall.Fstat(3, &info); err != nil || info.Mode&syscall.S_IFMT != syscall.S_IFSOCK {{
		_ksAbort("KS5002", "native worker started without its broker")
	}}
	// The worker dies with its broker: PR_SET_PDEATHSIG, then make sure the
	// broker (the peer of descriptor 3) had not already gone.
	if _, _, errno := syscall.RawSyscall(syscall.SYS_PRCTL, syscall.PR_SET_PDEATHSIG, uintptr(syscall.SIGKILL), 0); errno != 0 {{
		_ksAbort("KS5002", "native worker could not bind its lifetime to the broker")
	}}
	if peer, err := syscall.GetsockoptUcred(3, syscall.SOL_SOCKET, syscall.SO_PEERCRED); err != nil || int(peer.Pid) != os.Getppid() {{
		os.Exit(1)
	}}
	syscall.CloseOnExec(3)
	_ksBroker = os.NewFile(3, "koschei-broker")
	_ksConfine()
}}

func _ksConfine() {{
	if runtime.GOOS != "linux" || runtime.GOARCH != "amd64" {{
		_ksAbort("KS4001", "native capability confinement is implemented for linux/amd64 only")
	}}
	// An allow list (native_broker_v1.seccomp_filter); kill and tgkill
	// may only signal this process.
	filter := []syscall.SockFilter{{
{filter_lines},
	}}
	for _, slot := range []int{{{pid_slots}}} {{
		filter[slot].K = uint32(os.Getpid())
	}}
	if _, _, errno := syscall.RawSyscall(syscall.SYS_PRCTL, 38, 1, 0); errno != 0 {{
		_ksAbort("KS5002", "native worker could not set no_new_privs")
	}}
	program := syscall.SockFprog{{Len: uint16(len(filter)), Filter: &filter[0]}}
	// seccomp(SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_TSYNC, &program)
	if result, _, errno := syscall.RawSyscall(317, 1, 1, uintptr(unsafe.Pointer(&program))); errno != 0 || result != 0 {{
		_ksAbort("KS5002", "native worker could not confine itself")
	}}
}}

func _ksAsk(fields ...string) (bool, []string) {{
	if _ksBroker == nil {{
		_ksAbort("KS5002", "native broker is not connected")
	}}
	if err := _ksWriteFrame(_ksBroker, fields); err != nil {{
		_ksAbort("KS5002", "native broker request failed")
	}}
	answer, err := _ksReadFrame(_ksBroker, _ksMaxListItems+2, 2*_ksBrokerMaxField+64*_ksMaxListItems)
	if err != nil || len(answer) == 0 {{
		_ksAbort("KS5002", "native broker answer failed")
	}}
	return answer[0] == "ok", answer[1:]
}}

func _ksCapsDisk(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.disk receiver drifted")
	}}
	return _ksDiskRoot{{}}
}}

func _ksCapsEnv(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.env receiver drifted")
	}}
	return _ksEnvRoot{{}}
}}

func _ksDiskAllowReadOnly(receiver any, prefix any) any {{
	if _, ok := receiver.(_ksDiskRoot); !ok {{
		_ksAbort("KS5002", "DiskRoot receiver drifted")
	}}
	text, ok := prefix.(string)
	if !ok {{
		_ksAbort("KS5002", "DiskRoot.allow_read_only prefix drifted")
	}}
	_, answer := _ksAsk("scope", text)
	return _ksDiskReadCaps{{scope: answer[0]}}
}}

func _ksDiskAllow(receiver any, prefix any) any {{
	if _, ok := receiver.(_ksDiskRoot); !ok {{
		_ksAbort("KS5002", "DiskRoot receiver drifted")
	}}
	text, ok := prefix.(string)
	if !ok {{
		_ksAbort("KS5002", "DiskRoot.allow prefix drifted")
	}}
	_, answer := _ksAsk("scope_rw", text)
	return _ksDiskCaps{{scope: answer[0]}}
}}

func _ksDiskScopeOf(receiver any) _ksDiskReadCaps {{
	switch disk := receiver.(type) {{
	case _ksDiskReadCaps:
		return disk
	case _ksDiskCaps:
		return _ksDiskReadCaps{{scope: disk.scope}}
	}}
	_ksAbort("KS5002", "disk receiver drifted")
	return _ksDiskReadCaps{{}}
}}

func _ksDiskWritableOf(receiver any) _ksDiskCaps {{
	disk, ok := receiver.(_ksDiskCaps)
	if !ok {{
		_ksAbort("KS5002", "DiskCaps receiver drifted")
	}}
	return disk
}}

func _ksDiskWrite(receiver any, path any, value any) any {{
	text, ok := value.(string)
	if !ok {{
		_ksAbort("KS5002", "disk write value drifted")
	}}
	done, answer := _ksAsk("write", _ksDiskWritableOf(receiver).scope, _ksDiskPath(path), text)
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	return _ksUnit{{}}
}}

func _ksDiskDelete(receiver any, path any) any {{
	done, answer := _ksAsk("delete", _ksDiskWritableOf(receiver).scope, _ksDiskPath(path))
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	return _ksUnit{{}}
}}

func _ksDiskPath(path any) string {{
	text, ok := path.(string)
	if !ok {{
		_ksAbort("KS5002", "disk path drifted")
	}}
	return text
}}

func _ksDiskReadBytes(receiver any, path any) any {{
	ok, answer := _ksAsk("read", _ksDiskScopeOf(receiver).scope, _ksDiskPath(path))
	if !ok {{
		return _ksError{{message: answer[0]}}
	}}
	return _ksBytes{{data: answer[0]}}
}}

func _ksDiskReadText(receiver any, path any) any {{
	text := _ksDiskPath(path)
	ok, answer := _ksAsk("read", _ksDiskScopeOf(receiver).scope, text)
	if !ok {{
		if answer[0] == {bytes_message} {{
			return _ksError{{message: {string_message}}}
		}}
		return _ksError{{message: answer[0]}}
	}}
	if !utf8.ValidString(answer[0]) {{
		return _ksError{{message: {not_text} + text}}
	}}
	return answer[0]
}}

func _ksDiskList(receiver any, path any) any {{
	ok, answer := _ksAsk("list", _ksDiskScopeOf(receiver).scope, _ksDiskPath(path))
	if !ok {{
		return _ksError{{message: answer[0]}}
	}}
	items := make([]any, len(answer))
	for index, name := range answer {{
		items[index] = name
	}}
	return items
}}

func _ksEnvAllow(receiver any, name any) any {{
	if _, ok := receiver.(_ksEnvRoot); !ok {{
		_ksAbort("KS5002", "EnvRoot receiver drifted")
	}}
	text, ok := name.(string)
	if !ok {{
		_ksAbort("KS5002", "EnvRoot.allow name drifted")
	}}
	return _ksEnvCaps{{name: text}}
}}

func _ksEnvGet(receiver any) any {{
	env, ok := receiver.(_ksEnvCaps)
	if !ok {{
		_ksAbort("KS5002", "EnvCaps receiver drifted")
	}}
	found, answer := _ksAsk("env", env.name)
	if !found {{
		return _ksError{{message: answer[0]}}
	}}
	return answer[0]
}}

// ---- broker side ----------------------------------------------------------

type _ksScope struct {{
	prefix   string
	root     int
	rootErr  syscall.Errno
	writable bool
}}

func _ksBrokerServe() {{
	pair, err := syscall.Socketpair(syscall.AF_UNIX, syscall.SOCK_STREAM|syscall.SOCK_CLOEXEC, 0)
	if err != nil {{
		_ksAbort("KS5002", "native broker could not create its channel")
	}}
	brokerSide := os.NewFile(uintptr(pair[0]), "koschei-broker")
	workerSide := os.NewFile(uintptr(pair[1]), "koschei-worker")
	command := exec.Command("/proc/self/exe", os.Args[1:]...)
	command.Args[0] = os.Args[0]
	command.Stdin, command.Stdout, command.Stderr = os.Stdin, os.Stdout, os.Stderr
	command.ExtraFiles = []*os.File{{workerSide}}
	command.Env = []string{{{worker_env}}}
	if err := command.Start(); err != nil {{
		_ksAbort("KS5002", "native broker could not start the worker")
	}}
	workerSide.Close()
	go _ksBrokerLoop(brokerSide)
	err = command.Wait()
	if exit, ok := err.(*exec.ExitError); ok {{
		if status, ok := exit.Sys().(syscall.WaitStatus); ok && status.Signaled() {{
			fmt.Fprintln(os.Stderr, "KOSCHEI RUNTIME ERROR: KS5002: native worker was stopped by signal "+strconv.Itoa(int(status.Signal())))
			os.Exit(1)
		}}
		os.Exit(exit.ExitCode())
	}}
	if err != nil {{
		_ksAbort("KS5002", "native worker failed")
	}}
	os.Exit(0)
}}

func _ksBrokerLoop(channel *os.File) {{
	// Any malformed request ends the conversation: the worker sees the
	// channel close and stops instead of waiting.
	defer channel.Close()
	scopes := []*_ksScope{{nil}}
	for {{
		request, err := _ksReadFrame(channel, 6, _ksBrokerMaxField+(1<<18))
		if err != nil || len(request) == 0 {{
			return
		}}
		var answer []string
		switch {{
		case (request[0] == "scope" || request[0] == "scope_rw") && len(request) == 2:
			scope := _ksOpenScope(request[1])
			scope.writable = request[0] == "scope_rw"
			scopes = append(scopes, scope)
			answer = []string{{"ok", strconv.Itoa(len(scopes) - 1)}}
		case (request[0] == "write" && len(request) == 4) || (request[0] == "delete" && len(request) == 3):
			index, convErr := strconv.Atoi(request[1])
			// A read-only token's scope can never be written through.
			if convErr != nil || index < 1 || index >= len(scopes) || !scopes[index].writable {{
				return
			}}
			if request[0] == "write" {{
				answer = _ksBrokerWrite(scopes[index], request[2], request[3])
			}} else {{
				answer = _ksBrokerDelete(scopes[index], request[2])
			}}
		case (request[0] == "read" || request[0] == "list") && len(request) == 3:
			index, convErr := strconv.Atoi(request[1])
			if convErr != nil || index < 1 || index >= len(scopes) {{
				return
			}}
			if request[0] == "read" {{
				answer = _ksBrokerRead(scopes[index], request[2])
			}} else {{
				answer = _ksBrokerList(scopes[index], request[2])
			}}
		case request[0] == "env" && len(request) == 2:
			answer = _ksBrokerEnv(request[1])
		default:
			served := false
			if _ksBrokerNet != nil {{
				answer, served = _ksBrokerNet(request)
			}}
			if !served && _ksBrokerServers != nil {{
				answer, served = _ksBrokerServers(request)
			}}
			if !served {{
				return
			}}
		}}
		if _ksWriteFrame(channel, answer) != nil {{
			return
		}}
	}}
}}

func _ksErrnoText(code syscall.Errno, path string) string {{
	if name, ok := _ksErrnoNames[code]; ok {{
		return name + ": " + path
	}}
	return "errno " + strconv.Itoa(int(code)) + ": " + path
}}

func _ksAsErrno(err error) syscall.Errno {{
	if code, ok := err.(syscall.Errno); ok {{
		return code
	}}
	return syscall.EIO
}}

// posixpath.normpath
func _ksNormpath(path string) string {{
	if path == "" {{
		return "."
	}}
	initial := 0
	if strings.HasPrefix(path, "/") {{
		initial = 1
		if strings.HasPrefix(path, "//") && !strings.HasPrefix(path, "///") {{
			initial = 2
		}}
	}}
	parts := []string{{}}
	for _, part := range strings.Split(path, "/") {{
		if part == "" || part == "." {{
			continue
		}}
		if part != ".." || (initial == 0 && len(parts) == 0) || (len(parts) > 0 && parts[len(parts)-1] == "..") {{
			parts = append(parts, part)
		}} else if len(parts) > 0 {{
			parts = parts[:len(parts)-1]
		}}
	}}
	out := strings.Repeat("/", initial) + strings.Join(parts, "/")
	if out == "" {{
		return "."
	}}
	return out
}}

func _ksGetwd() string {{
	buffer := make([]byte, 4096)
	n, _, errno := syscall.Syscall(syscall.SYS_GETCWD, uintptr(unsafe.Pointer(&buffer[0])), uintptr(len(buffer)), 0)
	if errno != 0 || n == 0 {{
		_ksAbort("KS5002", "native broker could not read the current directory")
	}}
	return string(buffer[:n-1])
}}

func _ksJoin(left string, right string) string {{
	if strings.HasPrefix(right, "/") {{
		return right
	}}
	if left == "" || strings.HasSuffix(left, "/") {{
		return left + right
	}}
	return left + "/" + right
}}

// posixpath.abspath
func _ksAbspath(path string) string {{
	if !strings.HasPrefix(path, "/") {{
		path = _ksJoin(_ksGetwd(), path)
	}}
	return _ksNormpath(path)
}}

// posixpath.split
func _ksSplit(path string) (string, string) {{
	index := strings.LastIndex(path, "/") + 1
	head, tail := path[:index], path[index:]
	if head != "" && strings.Trim(head, "/") != "" {{
		head = strings.TrimRight(head, "/")
	}}
	return head, tail
}}

// posixpath.realpath (strict=False), as in CPython 3.12.
func _ksRealpath(path string) string {{
	resolved, _ := _ksJoinRealpath("", path, map[string]*string{{}})
	return _ksAbspath(resolved)
}}

func _ksJoinRealpath(path string, rest string, seen map[string]*string) (string, bool) {{
	if strings.HasPrefix(rest, "/") {{
		rest = rest[1:]
		path = "/"
	}}
	for rest != "" {{
		name := rest
		if index := strings.Index(rest, "/"); index >= 0 {{
			name, rest = rest[:index], rest[index+1:]
		}} else {{
			rest = ""
		}}
		if name == "" || name == "." {{
			continue
		}}
		if name == ".." {{
			if path != "" {{
				var tail string
				path, tail = _ksSplit(path)
				if tail == ".." {{
					path = _ksJoin(_ksJoin(path, ".."), "..")
				}}
			}} else {{
				path = ".."
			}}
			continue
		}}
		next := _ksJoin(path, name)
		var info syscall.Stat_t
		if syscall.Lstat(next, &info) != nil || info.Mode&syscall.S_IFMT != syscall.S_IFLNK {{
			path = next
			continue
		}}
		if known, ok := seen[next]; ok {{
			if known != nil {{
				path = *known
				continue
			}}
			return _ksJoin(next, rest), false
		}}
		seen[next] = nil
		buffer := make([]byte, 4096)
		n, err := syscall.Readlink(next, buffer)
		if err != nil {{
			path = next
			continue
		}}
		var ok bool
		path, ok = _ksJoinRealpath(path, string(buffer[:n]), seen)
		if !ok {{
			return _ksJoin(path, rest), false
		}}
		value := path
		seen[next] = &value
	}}
	return path, true
}}

// posixpath.relpath split into components; nil when outside the scope.
func _ksRelativeParts(scope *_ksScope, path string) ([]string, bool) {{
	if strings.Contains(path, "\x00") {{
		return nil, false
	}}
	target := _ksAbspath(path)
	start := []string{{}}
	for _, part := range strings.Split(_ksAbspath(scope.prefix), "/") {{
		if part != "" {{
			start = append(start, part)
		}}
	}}
	parts := []string{{}}
	for _, part := range strings.Split(target, "/") {{
		if part != "" {{
			parts = append(parts, part)
		}}
	}}
	common := 0
	for common < len(start) && common < len(parts) && start[common] == parts[common] {{
		common++
	}}
	if common < len(start) {{
		return nil, false
	}}
	out := []string{{}}
	for _, part := range parts[common:] {{
		if part == ".." {{
			return nil, false
		}}
		if part != "" && part != "." {{
			out = append(out, part)
		}}
	}}
	return out, true
}}

func _ksOpenScope(prefix string) *_ksScope {{
	scope := &_ksScope{{prefix: _ksRealpath(prefix), root: -1}}
	fd, err := syscall.Open(scope.prefix, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {{
		scope.rootErr = _ksAsErrno(err)
	}} else {{
		scope.root = fd
	}}
	return scope
}}

// fstatat(dir, name, AT_SYMLINK_NOFOLLOW)
func _ksLstatAt(dir int, name string, info *syscall.Stat_t) syscall.Errno {{
	pointer, err := syscall.BytePtrFromString(name)
	if err != nil {{
		return syscall.EINVAL
	}}
	_, _, errno := syscall.Syscall6(syscall.SYS_NEWFSTATAT, uintptr(dir), uintptr(unsafe.Pointer(pointer)), uintptr(unsafe.Pointer(info)), 0x100, 0, 0)
	return errno
}}

// interpreter._replace_file_atomically: a fresh exclusive temp file beside the
// target, the target's mode, fsync, one rename, then the directory's fsync.
// Returns (symlink refused, errno).
func _ksReplaceAtomically(parent int, name string, text string) (bool, syscall.Errno) {{
	mode := uint32(0o600)
	var info syscall.Stat_t
	if code := _ksLstatAt(parent, name, &info); code == 0 {{
		switch info.Mode & syscall.S_IFMT {{
		case syscall.S_IFLNK:
			return true, 0
		case syscall.S_IFDIR:
			return false, syscall.EISDIR
		}}
		mode = info.Mode & 0o7777
	}} else if code != syscall.ENOENT {{
		return false, code
	}}
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {{
		return false, syscall.EIO
	}}
	temporary := ".ks-write-" + hex.EncodeToString(random) + ".tmp"
	fd, err := syscall.Openat(parent, temporary, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0o600)
	if err != nil {{
		return false, _ksAsErrno(err)
	}}
	fail := func(code syscall.Errno) (bool, syscall.Errno) {{
		syscall.Close(fd)
		syscall.Unlinkat(parent, temporary)
		return false, code
	}}
	data := []byte(text)
	for len(data) > 0 {{
		n, err := syscall.Write(fd, data)
		if err != nil {{
			if err == syscall.EINTR {{
				continue
			}}
			return fail(_ksAsErrno(err))
		}}
		if n == 0 {{
			return fail(syscall.EIO)
		}}
		data = data[n:]
	}}
	if mode != 0o600 {{
		if err := syscall.Fchmod(fd, mode); err != nil {{
			return fail(_ksAsErrno(err))
		}}
	}}
	if err := syscall.Fsync(fd); err != nil {{
		return fail(_ksAsErrno(err))
	}}
	syscall.Close(fd)
	if err := syscall.Renameat(parent, temporary, parent, name); err != nil {{
		syscall.Unlinkat(parent, temporary)
		return false, _ksAsErrno(err)
	}}
	if err := syscall.Fsync(parent); err != nil {{
		code := _ksAsErrno(err)
		if code != syscall.EINVAL && code != syscall.ENOTSUP && code != syscall.EOPNOTSUPP {{
			return false, code
		}}
	}}
	return false, 0
}}

func _ksBrokerWrite(scope *_ksScope, path string, text string) []string {{
	parts, inside := _ksRelativeParts(scope, path)
	if !inside {{
		return []string{{"error", {reject} + path}}
	}}
	if len(parts) == 0 {{
		return []string{{"error", {root_write} + path}}
	}}
	parent, symlink, code := _ksParent(scope, parts)
	if symlink != "" {{
		return []string{{"error", {symlink} + symlink}}
	}}
	if code != 0 {{
		return []string{{"error", {write_prefix} + _ksErrnoText(code, path)}}
	}}
	defer syscall.Close(parent)
	name := parts[len(parts)-1]
	refused, code := _ksReplaceAtomically(parent, name, text)
	if refused || code == syscall.ELOOP || code == syscall.EMLINK {{
		return []string{{"error", {symlink} + name}}
	}}
	if code != 0 {{
		return []string{{"error", {write_prefix} + _ksErrnoText(code, path)}}
	}}
	return []string{{"ok"}}
}}

func _ksBrokerDelete(scope *_ksScope, path string) []string {{
	parts, inside := _ksRelativeParts(scope, path)
	if !inside {{
		return []string{{"error", {reject} + path}}
	}}
	if len(parts) == 0 {{
		return []string{{"error", {root_delete} + path}}
	}}
	parent, symlink, code := _ksParent(scope, parts)
	if symlink != "" {{
		return []string{{"error", {symlink} + symlink}}
	}}
	if code != 0 {{
		return []string{{"error", {delete_prefix} + _ksErrnoText(code, path)}}
	}}
	defer syscall.Close(parent)
	name := parts[len(parts)-1]
	var info syscall.Stat_t
	if code := _ksLstatAt(parent, name, &info); code != 0 {{
		if code == syscall.ELOOP || code == syscall.EMLINK {{
			return []string{{"error", {symlink} + name}}
		}}
		return []string{{"error", {delete_prefix} + _ksErrnoText(code, path)}}
	}}
	var err error
	switch info.Mode & syscall.S_IFMT {{
	case syscall.S_IFLNK:
		return []string{{"error", {symlink} + name}}
	case syscall.S_IFDIR:
		err = _ksUnlinkat(parent, name, 0x200) // AT_REMOVEDIR
	default:
		err = _ksUnlinkat(parent, name, 0)
	}}
	if err != nil {{
		code := _ksAsErrno(err)
		if code == syscall.ELOOP || code == syscall.EMLINK {{
			return []string{{"error", {symlink} + name}}
		}}
		return []string{{"error", {delete_prefix} + _ksErrnoText(code, path)}}
	}}
	return []string{{"ok"}}
}}

func _ksUnlinkat(dir int, name string, flags int) error {{
	pointer, err := syscall.BytePtrFromString(name)
	if err != nil {{
		return err
	}}
	_, _, errno := syscall.Syscall(syscall.SYS_UNLINKAT, uintptr(dir), uintptr(unsafe.Pointer(pointer)), uintptr(flags))
	if errno != 0 {{
		return errno
	}}
	return nil
}}

func _ksIsSymlinkAt(dir int, name string) bool {{
	var info syscall.Stat_t
	pointer, err := syscall.BytePtrFromString(name)
	if err != nil {{
		return false
	}}
	// newfstatat(dir, name, &info, AT_SYMLINK_NOFOLLOW)
	_, _, errno := syscall.Syscall6(syscall.SYS_NEWFSTATAT, uintptr(dir), uintptr(unsafe.Pointer(pointer)), uintptr(unsafe.Pointer(&info)), 0x100, 0, 0)
	if errno != 0 {{
		return false
	}}
	return info.Mode&syscall.S_IFMT == syscall.S_IFLNK
}}

// The parent directory of parts[len-1]: (fd, symlink name, errno).
func _ksParent(scope *_ksScope, parts []string) (int, string, syscall.Errno) {{
	if scope.root < 0 {{
		return -1, "", scope.rootErr
	}}
	current, err := syscall.Dup(scope.root)
	if err != nil {{
		return -1, "", _ksAsErrno(err)
	}}
	for _, component := range parts[:len(parts)-1] {{
		next, err := syscall.Openat(current, component, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		if err != nil {{
			code := _ksAsErrno(err)
			if (code == syscall.ELOOP || code == syscall.ENOTDIR) && _ksIsSymlinkAt(current, component) {{
				syscall.Close(current)
				return -1, component, 0
			}}
			syscall.Close(current)
			return -1, "", code
		}}
		syscall.Close(current)
		current = next
	}}
	return current, "", 0
}}

func _ksBrokerRead(scope *_ksScope, path string) []string {{
	parts, inside := _ksRelativeParts(scope, path)
	if !inside {{
		return []string{{"error", {reject} + path}}
	}}
	if len(parts) == 0 {{
		return []string{{"error", {root_read} + path}}
	}}
	parent, symlink, code := _ksParent(scope, parts)
	if symlink != "" {{
		return []string{{"error", {symlink} + symlink}}
	}}
	if code != 0 {{
		return []string{{"error", {read_prefix} + _ksErrnoText(code, path)}}
	}}
	defer syscall.Close(parent)
	name := parts[len(parts)-1]
	fd, err := syscall.Openat(parent, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {{
		code := _ksAsErrno(err)
		if code == syscall.ELOOP || code == syscall.EMLINK {{
			return []string{{"error", {symlink} + name}}
		}}
		return []string{{"error", {read_prefix} + _ksErrnoText(code, path)}}
	}}
	defer syscall.Close(fd)
	data := make([]byte, 0, 65536)
	chunk := make([]byte, 65536)
	for len(data) <= {max_bytes} {{
		n, err := syscall.Read(fd, chunk)
		if err != nil {{
			if err == syscall.EINTR {{
				continue
			}}
			return []string{{"error", {read_prefix} + _ksErrnoText(_ksAsErrno(err), path)}}
		}}
		if n == 0 {{
			break
		}}
		data = append(data, chunk[:n]...)
	}}
	if len(data) > {max_bytes} {{
		return []string{{"error", {bytes_message}}}
	}}
	return []string{{"ok", string(data)}}
}}

func _ksListNames(fd int) ([]string, syscall.Errno) {{
	if _, err := syscall.Seek(fd, 0, 0); err != nil {{
		return nil, _ksAsErrno(err)
	}}
	names := []string{{}}
	buffer := make([]byte, 65536)
	for {{
		n, err := syscall.ReadDirent(fd, buffer)
		if err != nil {{
			return nil, _ksAsErrno(err)
		}}
		if n <= 0 {{
			break
		}}
		_, _, names = syscall.ParseDirent(buffer[:n], -1, names)
		if len(names) > {max_items} {{
			break
		}}
	}}
	return names, 0
}}

func _ksBrokerList(scope *_ksScope, path string) []string {{
	parts, inside := _ksRelativeParts(scope, path)
	if !inside {{
		return []string{{"error", {reject} + path}}
	}}
	var fd int
	if len(parts) == 0 {{
		if scope.root < 0 {{
			return []string{{"error", {list_prefix} + _ksErrnoText(scope.rootErr, path)}}
		}}
		duplicate, err := syscall.Dup(scope.root)
		if err != nil {{
			return []string{{"error", {list_prefix} + _ksErrnoText(_ksAsErrno(err), path)}}
		}}
		fd = duplicate
	}} else {{
		parent, symlink, code := _ksParent(scope, parts)
		if symlink != "" {{
			return []string{{"error", {symlink} + symlink}}
		}}
		if code != 0 {{
			return []string{{"error", {list_prefix} + _ksErrnoText(code, path)}}
		}}
		name := parts[len(parts)-1]
		opened, err := syscall.Openat(parent, name, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		syscall.Close(parent)
		if err != nil {{
			code := _ksAsErrno(err)
			if code == syscall.ELOOP || code == syscall.EMLINK {{
				return []string{{"error", {symlink} + name}}
			}}
			return []string{{"error", {list_prefix} + _ksErrnoText(code, path)}}
		}}
		fd = opened
	}}
	defer syscall.Close(fd)
	names, code := _ksListNames(fd)
	if code != 0 {{
		return []string{{"error", {list_prefix} + _ksErrnoText(code, path)}}
	}}
	if len(names) > {max_items} {{
		return []string{{"error", {list_message}}}
	}}
	for _, name := range names {{
		if !utf8.ValidString(name) {{
			return []string{{"error", {list_name} + path}}
		}}
	}}
	// Python sorts by code point; for UTF-8 that is byte order.
	sort.Strings(names)
	return append([]string{{"ok"}}, names...)
}}

func _ksBrokerEnv(name string) []string {{
	value, found := syscall.Getenv(name)
	if !found {{
		return []string{{"error", {env_missing} + name}}
	}}
	if !utf8.ValidString(value) {{
		return []string{{"error", {env_not_text} + name}}
	}}
	return []string{{"ok", value}}
}}
'''

__all__ = [
    "BROKER_IMPORTS",
    "ALLOWED_SYSCALLS_AMD64",
    "WORKER_ENV",
    "broker_runtime",
]

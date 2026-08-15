"""Linux native-Go parity for the bounded one-shot Serve exchange.

The high-level Go listener API does not expose an exact backlog argument. Because
Serve Authority v1 treats connection count as a security budget, this adapter uses
a Linux socket/listen boundary with the policy's max_connections as the backlog,
then converts the descriptor to a TCPListener. Non-Linux native Serve generation
remains fail-closed.
"""

from __future__ import annotations

import sys

from . import codegen_go as _codegen
from . import serve_authority_v1 as _serve_authority
from .ast_nodes import MemberExpression
from .diagnostics import SourceLocation

_INSTALLED = False
_ORIGINAL_GENERATE = None
_ORIGINAL_VALIDATE = None


_GO_SERVE_HELPERS = r'''
const ksServeMaxConnections int64 = 4096
const ksServeMaxBytes int64 = 16 * 1024 * 1024
const ksServeMaxDeadlineMs int64 = 120000
const ksServeHardHeaderBytes int64 = 64 * 1024

type ksServeRoot struct{}

type ksServePolicy struct {
	bind             string
	host             string
	port             int
	maxConnections   int64
	maxRequestBytes  int64
	maxResponseBytes int64
	deadlineMs       int64
}

type ksServeCaps struct{ policy ksServePolicy }

func ksServeProtocol(message string) *KsError {
	return &KsError{Message: "KS3410: " + message}
}

func ksServeIO(message string) *KsError {
	return &KsError{Message: "KS3411: " + message}
}

func ksServeIntArgument(method string, arguments []any, index int) (int64, *KsError) {
	if index >= len(arguments) {
		return 0, &KsError{Message: "KS4003: Eksik Int metot argümanı: " + method}
	}
	value, ok := arguments[index].(int64)
	if !ok {
		return 0, &KsError{Message: "KS1301: '" + method + "' Int argüman bekler."}
	}
	return value, nil
}

func ksServeCanonicalBind(raw string) (string, int, string, bool) {
	text := strings.TrimSpace(raw)
	if text == "" {
		return "", 0, "", false
	}
	lower := strings.ToLower(text)
	if strings.HasPrefix(lower, "localhost:") {
		portText := text[len("localhost:"):]
		port, err := strconv.Atoi(portText)
		if err != nil || port < 1 || port > 65535 {
			return "", 0, "", false
		}
		return "127.0.0.1", port, net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), true
	}
	if !strings.HasPrefix(text, "[") && strings.Count(text, ":") > 1 {
		return "", 0, "", false
	}
	host, portText, err := net.SplitHostPort(text)
	if err != nil || host == "" || portText == "" {
		return "", 0, "", false
	}
	port, err := strconv.Atoi(portText)
	if err != nil || port < 1 || port > 65535 {
		return "", 0, "", false
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return "", 0, "", false
	}
	if ipv4 := ip.To4(); ipv4 != nil {
		host = ipv4.String()
	} else {
		host = ip.String()
	}
	return host, port, net.JoinHostPort(host, strconv.Itoa(port)), true
}

func ksServeAllow(arguments []any) any {
	if failure := ksMethodArity("allow", arguments, 5); failure != nil {
		return failure
	}
	bind, failure := ksStringArgument("allow", arguments, 0)
	if failure != nil {
		return failure
	}
	host, port, canonical, ok := ksServeCanonicalBind(bind)
	if !ok {
		return ksErrorf("KS2411: Serve v1 yalnızca canonical loopback host:port kabul eder")
	}
	connections, failure := ksServeIntArgument("allow", arguments, 1)
	if failure != nil { return failure }
	requestBytes, failure := ksServeIntArgument("allow", arguments, 2)
	if failure != nil { return failure }
	responseBytes, failure := ksServeIntArgument("allow", arguments, 3)
	if failure != nil { return failure }
	deadlineMs, failure := ksServeIntArgument("allow", arguments, 4)
	if failure != nil { return failure }

	if connections < 1 || connections > ksServeMaxConnections {
		return ksErrorf("KS2411: Serve max_connections 1..4096 aralığında olmalıdır")
	}
	if requestBytes < 1 || requestBytes > ksServeMaxBytes {
		return ksErrorf("KS2411: Serve max_request_bytes güvenlik sınırı dışında")
	}
	if responseBytes < 1 || responseBytes > ksServeMaxBytes {
		return ksErrorf("KS2411: Serve max_response_bytes güvenlik sınırı dışında")
	}
	if deadlineMs < 1 || deadlineMs > ksServeMaxDeadlineMs {
		return ksErrorf("KS2411: Serve I/O deadline 1..120000 ms aralığında olmalıdır")
	}
	return &ksServeCaps{policy: ksServePolicy{
		bind: canonical,
		host: host,
		port: port,
		maxConnections: connections,
		maxRequestBytes: requestBytes,
		maxResponseBytes: responseBytes,
		deadlineMs: deadlineMs,
	}}
}

func ksServeListen(policy ksServePolicy, deadline time.Time) (*net.TCPListener, *KsError) {
	if runtime.GOOS != "linux" {
		return nil, ksServeIO("native Serve v1 yalnızca Linux backlog-bound socket hedefinde desteklenir")
	}
	ip := net.ParseIP(policy.host)
	if ip == nil || !ip.IsLoopback() {
		return nil, ksServeProtocol("sealed Serve bind artık loopback değil")
	}

	family := syscall.AF_INET
	var address syscall.Sockaddr
	if ipv4 := ip.To4(); ipv4 != nil {
		var raw [4]byte
		copy(raw[:], ipv4)
		address = &syscall.SockaddrInet4{Port: policy.port, Addr: raw}
	} else {
		ipv6 := ip.To16()
		if ipv6 == nil {
			return nil, ksServeProtocol("sealed IPv6 Serve bind geçersiz")
		}
		var raw [16]byte
		copy(raw[:], ipv6)
		family = syscall.AF_INET6
		address = &syscall.SockaddrInet6{Port: policy.port, Addr: raw}
	}

	fd, err := syscall.Socket(family, syscall.SOCK_STREAM|syscall.SOCK_CLOEXEC, 0)
	if err != nil {
		return nil, ksServeIO("listener socket açılamadı: " + err.Error())
	}
	open := true
	defer func() {
		if open { _ = syscall.Close(fd) }
	}()
	if err := syscall.Bind(fd, address); err != nil {
		return nil, ksServeIO("listener bind başarısız: " + err.Error())
	}
	if err := syscall.Listen(fd, int(policy.maxConnections)); err != nil {
		return nil, ksServeIO("listener backlog kurulamadı: " + err.Error())
	}

	file := os.NewFile(uintptr(fd), "koschei-serve-listener")
	if file == nil {
		return nil, ksServeIO("listener descriptor geçersiz")
	}
	listener, err := net.FileListener(file)
	_ = file.Close()
	open = false
	if err != nil {
		return nil, ksServeIO("listener descriptor bağlanamadı: " + err.Error())
	}
	tcp, ok := listener.(*net.TCPListener)
	if !ok {
		_ = listener.Close()
		return nil, ksServeIO("listener TCP biçiminde değil")
	}
	if err := tcp.SetDeadline(deadline); err != nil {
		_ = tcp.Close()
		return nil, ksServeIO("listener deadline kurulamadı: " + err.Error())
	}
	return tcp, nil
}

func ksServeHeaderEnd(value []byte) int {
	for index := 0; index+3 < len(value); index++ {
		if value[index] == '\r' && value[index+1] == '\n' &&
			value[index+2] == '\r' && value[index+3] == '\n' {
			return index
		}
	}
	return -1
}

func ksServeTokenByte(value byte) bool {
	if value >= '0' && value <= '9' { return true }
	if value >= 'A' && value <= 'Z' { return true }
	if value >= 'a' && value <= 'z' { return true }
	switch value {
	case '!', '#', '$', '%', '&', '\'', '*', '+', '-', '.', '^', '_', '`', '|', '~':
		return true
	}
	return false
}

func ksServeMethodValid(value string) bool {
	if value == "" { return false }
	for index := 0; index < len(value); index++ {
		byteValue := value[index]
		if byteValue < 'A' || byteValue > 'Z' { return false }
	}
	return true
}

func ksServeTargetValid(value string) bool {
	if value == "" || value[0] != '/' || strings.Contains(value, "#") {
		return false
	}
	for index := 0; index < len(value); index++ {
		if value[index] < 0x21 || value[index] > 0x7e { return false }
	}
	return true
}

func ksServeHeaderValueValid(value string) bool {
	for index := 0; index < len(value); index++ {
		byteValue := value[index]
		if byteValue == '\t' { continue }
		if byteValue < 0x20 || byteValue == 0x7f { return false }
	}
	return true
}

func ksServeParseHead(raw []byte) (int, int64, *KsError) {
	marker := ksServeHeaderEnd(raw)
	if marker < 0 {
		return 0, 0, ksServeProtocol("HTTP header terminator bulunamadı")
	}
	headerEnd := marker + 4
	if int64(headerEnd) > ksServeHardHeaderBytes {
		return 0, 0, ksServeProtocol("HTTP headers hard limit'i aştı")
	}

	lines := strings.Split(string(raw[:marker]), "\r\n")
	if len(lines) == 0 || lines[0] == "" {
		return 0, 0, ksServeProtocol("HTTP request line eksik")
	}
	parts := strings.Split(lines[0], " ")
	if len(parts) != 3 || !ksServeMethodValid(parts[0]) || !ksServeTargetValid(parts[1]) {
		return 0, 0, ksServeProtocol("HTTP request line reduced grammar'ı ihlal etti")
	}
	version := parts[2]
	if version != "HTTP/1.0" && version != "HTTP/1.1" {
		return 0, 0, ksServeProtocol("yalnız HTTP/1.0 ve HTTP/1.1 kabul edilir")
	}

	hosts := 0
	lengths := 0
	var contentLength int64
	for _, line := range lines[1:] {
		separator := strings.IndexByte(line, ':')
		if separator <= 0 {
			return 0, 0, ksServeProtocol("malformed HTTP header line")
		}
		rawName := line[:separator]
		if rawName != strings.TrimSpace(rawName) {
			return 0, 0, ksServeProtocol("malformed HTTP header name")
		}
		for index := 0; index < len(rawName); index++ {
			if !ksServeTokenByte(rawName[index]) {
				return 0, 0, ksServeProtocol("malformed HTTP header name")
			}
		}
		value := strings.Trim(line[separator+1:], " \t")
		if !ksServeHeaderValueValid(value) {
			return 0, 0, ksServeProtocol("HTTP header value control byte içeriyor")
		}
		name := strings.ToLower(rawName)
		switch name {
		case "host":
			hosts++
			if strings.TrimSpace(value) == "" {
				return 0, 0, ksServeProtocol("Host header boş olamaz")
			}
		case "transfer-encoding":
			return 0, 0, ksServeProtocol("Transfer-Encoding exchange v1'de desteklenmez")
		case "content-length":
			lengths++
			if lengths > 1 {
				return 0, 0, ksServeProtocol("duplicate Content-Length reddedildi")
			}
			if value == "" {
				return 0, 0, ksServeProtocol("Content-Length boş olamaz")
			}
			for index := 0; index < len(value); index++ {
				if value[index] < '0' || value[index] > '9' {
					return 0, 0, ksServeProtocol("Content-Length decimal olmalıdır")
				}
			}
			parsed, err := strconv.ParseInt(value, 10, 64)
			if err != nil || parsed < 0 {
				return 0, 0, ksServeProtocol("Content-Length geçersiz")
			}
			contentLength = parsed
		}
	}
	if version == "HTTP/1.1" && hosts != 1 {
		return 0, 0, ksServeProtocol("HTTP/1.1 exactly one Host gerektirir")
	}
	if hosts > 1 {
		return 0, 0, ksServeProtocol("duplicate Host reddedildi")
	}
	return headerEnd, contentLength, nil
}

func ksServeReadRequest(connection net.Conn, policy ksServePolicy) any {
	headerLimit := policy.maxRequestBytes
	if headerLimit > ksServeHardHeaderBytes { headerLimit = ksServeHardHeaderBytes }
	buffer := make([]byte, 0, min(int(policy.maxRequestBytes), 4096))
	var headerEnd int
	var contentLength int64

	for headerEnd == 0 {
		if int64(len(buffer)) >= headerLimit {
			return ksServeProtocol("HTTP headers configured request budget'ını aştı")
		}
		chunkSize := int64(4096)
		remaining := headerLimit - int64(len(buffer)) + 1
		if chunkSize > remaining { chunkSize = remaining }
		chunk := make([]byte, int(chunkSize))
		n, err := connection.Read(chunk)
		if n > 0 {
			buffer = append(buffer, chunk[:n]...)
			if int64(len(buffer)) > policy.maxRequestBytes {
				return ksServeProtocol("request max_request_bytes sınırını aştı")
			}
			marker := ksServeHeaderEnd(buffer)
			if marker >= 0 {
				var failure *KsError
				headerEnd, contentLength, failure = ksServeParseHead(buffer)
				if failure != nil { return failure }
				if int64(headerEnd) > headerLimit {
					return ksServeProtocol("HTTP headers configured header budget'ını aştı")
				}
			}
		}
		if headerEnd != 0 { break }
		if err != nil {
			if err == io.EOF { return ksServeProtocol("connection headers tamamlanmadan kapandı") }
			if networkError, ok := err.(net.Error); ok && networkError.Timeout() {
				return ksServeIO("request header read I/O deadline'ı aştı")
			}
			return ksServeIO("request header read başarısız: " + err.Error())
		}
		if n == 0 {
			return ksServeIO("request header read sıfır byte ilerleme yaptı")
		}
	}

	expected := int64(headerEnd) + contentLength
	if expected > policy.maxRequestBytes {
		return ksServeProtocol("request body max_request_bytes sınırını aştı")
	}
	if int64(len(buffer)) > expected {
		return ksServeProtocol("Content-Length ötesinde gözlenen byte reddedildi")
	}
	for int64(len(buffer)) < expected {
		remaining := expected - int64(len(buffer))
		chunkSize := int64(4096)
		if chunkSize > remaining+1 { chunkSize = remaining + 1 }
		chunk := make([]byte, int(chunkSize))
		n, err := connection.Read(chunk)
		if n > 0 {
			buffer = append(buffer, chunk[:n]...)
			if int64(len(buffer)) > expected {
				return ksServeProtocol("declared Content-Length ötesinde byte reddedildi")
			}
		}
		if int64(len(buffer)) >= expected { break }
		if err != nil {
			if err == io.EOF { return ksServeProtocol("request body tamamlanmadan connection kapandı") }
			if networkError, ok := err.(net.Error); ok && networkError.Timeout() {
				return ksServeIO("request body read I/O deadline'ı aştı")
			}
			return ksServeIO("request body read başarısız: " + err.Error())
		}
		if n == 0 { return ksServeIO("request body read sıfır byte ilerleme yaptı") }
	}

	body := buffer[headerEnd:int(expected)]
	if !utf8.Valid(body) {
		return ksServeProtocol("exchange v1 request body UTF-8 olmalıdır")
	}
	return string(body)
}

func ksServeResponseWire(response string, policy ksServePolicy) any {
	payload := []byte(response)
	head := []byte(fmt.Sprintf(
		"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
		len(payload),
	))
	wire := append(head, payload...)
	if int64(len(wire)) > policy.maxResponseBytes {
		return ksServeProtocol("response max_response_bytes sınırını aştı")
	}
	return wire
}

func ksServeWriteAll(connection net.Conn, wire []byte) *KsError {
	for written := 0; written < len(wire); {
		n, err := connection.Write(wire[written:])
		if n > 0 { written += n }
		if written >= len(wire) { return nil }
		if err != nil {
			if networkError, ok := err.(net.Error); ok && networkError.Timeout() {
				return ksServeIO("response write I/O deadline'ı aştı")
			}
			return ksServeIO("response write başarısız: " + err.Error())
		}
		if n == 0 { return ksServeIO("response write sıfır byte ilerleme yaptı") }
	}
	return nil
}

func ksServeExchange(capability *ksServeCaps, responseValue any) any {
	response, ok := responseValue.(string)
	if !ok {
		return ksServeProtocol("ServeCaps.exchange() response String olmalıdır")
	}
	wireValue := ksServeResponseWire(response, capability.policy)
	if failure, ok := wireValue.(*KsError); ok { return failure }
	wire := wireValue.([]byte)

	deadline := time.Now().Add(time.Duration(capability.policy.deadlineMs) * time.Millisecond)
	listener, failure := ksServeListen(capability.policy, deadline)
	if failure != nil { return failure }
	defer listener.Close()

	connection, err := listener.Accept()
	if err != nil {
		if networkError, ok := err.(net.Error); ok && networkError.Timeout() {
			return ksServeIO("accept I/O deadline'ı aştı")
		}
		return ksServeIO("accept başarısız: " + err.Error())
	}
	defer connection.Close()
	if err := connection.SetDeadline(deadline); err != nil {
		return ksServeIO("connection deadline kurulamadı: " + err.Error())
	}

	body := ksServeReadRequest(connection, capability.policy)
	if failure, ok := body.(*KsError); ok { return failure }
	if failure := ksServeWriteAll(connection, wire); failure != nil { return failure }
	return body
}

'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        if new in source:
            return source
        raise RuntimeError(f"Serve Go runtime layout changed at {label}; patch failed closed.")
    return source.replace(old, new, 1)


def _patch_capability_runtime() -> None:
    runtime_source = _codegen.CAPABILITY_RUNTIME

    runtime_source = _replace_once(
        runtime_source,
        '''type ksSystemCaps struct {
\tnet     *ksNetRoot
\tdisk    *ksDiskRoot
\tenv     *ksEnvRoot
\tprocess *ksProcessRoot
}''',
        '''type ksSystemCaps struct {
\tnet     *ksNetRoot
\tdisk    *ksDiskRoot
\tenv     *ksEnvRoot
\tprocess *ksProcessRoot
\tserve   *ksServeRoot
}''',
        "SystemCaps field",
    )

    runtime_source = _replace_once(
        runtime_source,
        '''\tcase *ksSystemCaps, *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps, *ksProcessCaps:''',
        '''\tcase *ksSystemCaps, *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps, *ksProcessCaps, *ksServeCaps:''',
        "capability containment",
    )

    runtime_source = _replace_once(
        runtime_source,
        '''\t\tprocess: &ksProcessRoot{},
\t}''',
        '''\t\tprocess: &ksProcessRoot{},
\t\tserve:   &ksServeRoot{},
\t}''',
        "SystemCaps constructor",
    )

    runtime_source = _replace_once(
        runtime_source,
        '''\t\tcase "process":
\t\t\treturn item.process
\t\t}''',
        '''\t\tcase "process":
\t\t\treturn item.process
\t\tcase "serve":
\t\t\treturn item.serve
\t\t}''',
        "SystemCaps member",
    )

    call_anchor = "func ksCallMethod(receiver any, method string, arguments ...any) any {"
    if "func ksServeExchange(" not in runtime_source:
        runtime_source = _replace_once(
            runtime_source,
            call_anchor,
            _GO_SERVE_HELPERS.replace("\\t", "\t") + call_anchor,
            "Serve helper insertion",
        )

    runtime_source = _replace_once(
        runtime_source,
        '''\tswitch item := receiver.(type) {
\tcase *ksNetRoot:''',
        '''\tswitch item := receiver.(type) {
\tcase *ksServeRoot:
\t\tif method != "allow" {
\t\t\treturn ksErrorf("KS2402: ServeRoot önce allow ile daraltılmalıdır.")
\t\t}
\t\treturn ksServeAllow(arguments)
\tcase *ksServeCaps:
\t\tif method != "exchange" {
\t\t\treturn ksErrorf("KS2404: ServeCaps yetkisi '" + method + "' işlemine izin vermez.")
\t\t}
\t\tif failure := ksMethodArity(method, arguments, 1); failure != nil {
\t\t\treturn failure
\t\t}
\t\treturn ksServeExchange(item, arguments[0])
\tcase *ksNetRoot:''',
        "method dispatch",
    )

    runtime_source = _replace_once(
        runtime_source,
        '''\tcase *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps,
\t\t*ksProcessCaps, *ksResponse:''',
        '''\tcase *ksNetRoot, *ksDiskRoot, *ksEnvRoot, *ksProcessRoot, *ksServeRoot,
\t\t*ksNetCaps, *ksDiskCaps, *ksDiskReadCaps, *ksEnvCaps,
\t\t*ksProcessCaps, *ksServeCaps, *ksResponse:''',
        "dynamic method dispatch",
    )

    _codegen.CAPABILITY_RUNTIME = runtime_source


def _uses_serve(program) -> bool:
    for declaration in program.declarations:
        for parameter in declaration.parameters:
            if any(name in {"ServeRoot", "ServeCaps"} for name in parameter.type_ref.names):
                return True
        for statement in declaration.body.statements:
            for expression in _codegen._walk_statement(statement):
                if isinstance(expression, MemberExpression) and expression.member in {"serve", "exchange"}:
                    return True
    return False


def _validate_capability_backend(self) -> None:
    if not _uses_serve(self.program):
        return _ORIGINAL_VALIDATE(self)
    if not sys.platform.startswith("linux"):
        raise _codegen.CodegenError(
            "KS4001",
            "Native Serve v1 backlog-bound socket ABI şu anda yalnızca Linux hedefinde desteklenir.",
            SourceLocation(1, 1),
        )
    # Bypass Serve Authority v1's intentional pre-listener rejection, but retain
    # every capability/backend validation layer that existed before it.
    return _serve_authority._ORIGINAL_CODEGEN_VALIDATE(self)


def _generate_with_serve_imports(self) -> str:
    source = _ORIGINAL_GENERATE(self)
    if '\t"net"\n' not in source:
        marker = '\t"net/http"\n'
        if marker not in source:
            raise RuntimeError("Go net/http import missing; Serve import patch failed closed.")
        source = source.replace(marker, '\t"net"\n' + marker, 1)
    if '\t"unicode/utf8"\n' not in source:
        marker = '\t"time"\n'
        if marker not in source:
            raise RuntimeError("Go time import missing; Serve import patch failed closed.")
        source = source.replace(marker, marker + '\t"unicode/utf8"\n', 1)
    return source


def install_serve_loopback_exchange_go_v1() -> None:
    global _INSTALLED, _ORIGINAL_GENERATE, _ORIGINAL_VALIDATE
    if _INSTALLED:
        return

    _codegen.NATIVE_CAPABILITY_METHODS.add("exchange")
    _patch_capability_runtime()

    _ORIGINAL_VALIDATE = _codegen.GoCodegen._validate_capability_backend
    _codegen.GoCodegen._validate_capability_backend = _validate_capability_backend

    _ORIGINAL_GENERATE = _codegen.GoCodegen.generate
    _codegen.GoCodegen.generate = _generate_with_serve_imports

    _INSTALLED = True

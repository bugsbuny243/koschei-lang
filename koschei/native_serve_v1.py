"""The multi-request loopback server in native binaries (gates G4 and G2).

The worker cannot create sockets, so the broker owns the listener and the one
pending connection. ``accept()`` and ``reply()`` are requests on the broker
channel; the broker ports ``serve_knowhere_v1`` exactly: the loopback bind
rule, the strict HTTP/1.x request grammar of ``serve_loopback_exchange_v1``,
the request, response, connection and deadline budgets, the Knowhere rule
(one request per connection, answered once) and every Error text.
"""

from __future__ import annotations

from . import serve_knowhere_v1 as _serve

SERVE_IMPORTS = ("errors", "io", "net", "time")


def _go(value: str) -> str:
    from .mir_go_native import _go_string

    return _go_string(value)


def serve_runtime() -> str:
    from . import serve_authority_v1 as _authority

    reasons = "\n".join(f"\t{code}: {_go(text)}," for code, text in sorted(_serve.REASONS.items()))
    budget_prefix, budget_suffix = _serve.BUDGET_MESSAGE.split("{count}")
    status_prefix, status_suffix = _serve.STATUS_MESSAGE.split("{status}")
    return _SERVE_RUNTIME.format(
        reasons=reasons,
        pending=_go(_serve.PENDING_MESSAGE),
        no_pending=_go(_serve.NO_PENDING_MESSAGE),
        budget_prefix=_go(budget_prefix),
        budget_suffix=_go(budget_suffix),
        status_prefix=_go(status_prefix),
        status_suffix=_go(status_suffix),
        empty_body=_go(_serve.EMPTY_BODY_MESSAGE),
        max_header=_serve._exchange._MAX_HEADER_BYTES,
        min_connections=_authority._MIN_CONNECTIONS,
        max_connections=_authority._MAX_CONNECTIONS,
        min_bytes=_authority._MIN_BYTES,
        max_bytes=_authority._MAX_BYTES,
        min_deadline=_authority._MIN_DEADLINE_MS,
        max_deadline=_authority._MAX_DEADLINE_MS,
    )


def request_runtime() -> str:
    """HttpRequest members; part of the base runtime (no imports)."""

    header_prefix, header_suffix = _serve.HEADER_MESSAGE.split("{name}")
    return _REQUEST_RUNTIME.format(
        header_prefix=_go(header_prefix),
        header_suffix=_go(header_suffix),
        body_text=_go(_serve.BODY_TEXT_MESSAGE),
    )


_REQUEST_RUNTIME = r'''
func _ksRequestMember(request _ksHttpRequest, name string, arguments []any) any {{
	switch name {{
	case "method":
		_ksArity("method", arguments, 0)
		return request.method
	case "path":
		_ksArity("path", arguments, 0)
		return request.path
	case "body":
		_ksArity("body", arguments, 0)
		if !utf8.ValidString(request.body) {{
			return _ksError{{message: {body_text}}}
		}}
		return request.body
	case "body_bytes":
		_ksArity("body_bytes", arguments, 0)
		return _ksBytes{{data: request.body}}
	case "header":
		_ksArity("header", arguments, 1)
		wanted, ok := arguments[0].(string)
		if !ok {{
			_ksAbort("KS5002", "HttpRequest.header name drifted")
		}}
		// Names are ASCII tokens; only ASCII letters fold.
		folded := []byte(wanted)
		for index, character := range folded {{
			if character >= 'A' && character <= 'Z' {{
				folded[index] = character + 32
			}}
		}}
		for _, header := range request.headers {{
			if header[0] == string(folded) {{
				return header[1]
			}}
		}}
		return _ksError{{message: {header_prefix} + wanted + {header_suffix}}}
	}}
	_ksAbort("KS3101", "undefined member '"+name+"'")
	return nil
}}
'''

_SERVE_RUNTIME = r'''
// ---- loopback server through the broker (native_serve_v1) ----------------

func _ksCapsServe(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.serve receiver drifted")
	}}
	return _ksServeRoot{{}}
}}

func _ksServeInt(value any) string {{
	number, ok := value.(int64)
	if !ok {{
		_ksAbort("KS5002", "ServeRoot.allow budget drifted")
	}}
	return strconv.FormatInt(number, 10)
}}

func _ksServeAllow(receiver any, bind any, connections any, requestBytes any, responseBytes any, deadline any) any {{
	if _, ok := receiver.(_ksServeRoot); !ok {{
		_ksAbort("KS5002", "ServeRoot receiver drifted")
	}}
	text, ok := bind.(string)
	if !ok {{
		_ksAbort("KS5002", "ServeRoot.allow bind drifted")
	}}
	done, answer := _ksAsk("serve_scope", text, _ksServeInt(connections), _ksServeInt(requestBytes), _ksServeInt(responseBytes), _ksServeInt(deadline))
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	// Like Python dropping a server, a collected token closes its listener
	// and pending connection in the broker.
	token := &_ksServeCaps{{scope: answer[0]}}
	runtime.SetFinalizer(token, func(token *_ksServeCaps) {{ _ksQueueRelease("serve_release", token.scope) }})
	return token
}}

// Callers keep the token alive (runtime.KeepAlive) until the broker has
// answered, so its finalizer cannot release the server mid-request.
func _ksServeScopeOf(receiver any) string {{
	caps, ok := receiver.(*_ksServeCaps)
	if !ok {{
		_ksAbort("KS5002", "ServeCaps receiver drifted")
	}}
	return caps.scope
}}

func _ksServeAccept(receiver any) any {{
	scope := _ksServeScopeOf(receiver)
	done, answer := _ksAsk("serve_accept", scope, "retry")
	if !done && len(answer) == 0 {{
		// The bind is held by a dropped server of this program: collect it
		// and ask once more.
		_ksCollectReleases("serve_release")
		done, answer = _ksAsk("serve_accept", scope, "final")
	}}
	runtime.KeepAlive(receiver)
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	if len(answer) < 3 || (len(answer)-3)%2 != 0 {{
		_ksAbort("KS5002", "native broker answer drifted")
	}}
	request := _ksHttpRequest{{method: answer[0], path: answer[1], body: answer[2]}}
	for index := 3; index < len(answer); index += 2 {{
		request.headers = append(request.headers, [2]string{{answer[index], answer[index+1]}})
	}}
	return request
}}

func _ksServeReply(receiver any, status any, body any) any {{
	code, ok := status.(int64)
	if !ok {{
		_ksAbort("KS5002", "ServeCaps.reply status drifted")
	}}
	var kind, payload string
	switch value := body.(type) {{
	case string:
		kind, payload = "s", value
	case _ksBytes:
		kind, payload = "b", value.data
	default:
		_ksAbort("KS5002", "ServeCaps.reply body drifted")
	}}
	done, answer := _ksAsk("serve_reply", _ksServeScopeOf(receiver), strconv.FormatInt(code, 10), kind, payload)
	runtime.KeepAlive(receiver)
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	return _ksUnit{{}}
}}

// ---- broker side ----------------------------------------------------------

var _ksReasons = map[int64]string{{
{reasons}
}}

type _ksServeScope struct {{
	host          string
	port          int
	connections   int
	requestBytes  int
	responseBytes int
	deadline      time.Duration
	listener      net.Listener
	pending       net.Conn
	accepted      int
}}

var _ksServeScopes = []*_ksServeScope{{nil}}

// serve_authority_v1._parse_loopback_bind
func _ksParseLoopbackBind(raw string) (string, int, bool) {{
	text := strings.TrimFunc(raw, _ksIsSpace)
	if text == "" {{
		return "", 0, false
	}}
	var host, portText string
	if strings.HasPrefix(text, "[") {{
		closing := strings.Index(text, "]")
		if closing <= 1 || closing+1 >= len(text) || text[closing+1] != ':' {{
			return "", 0, false
		}}
		host, portText = text[1:closing], text[closing+2:]
	}} else {{
		separator := strings.LastIndex(text, ":")
		if separator <= 0 {{
			return "", 0, false
		}}
		host, portText = text[:separator], text[separator+1:]
	}}
	if portText == "" || len(portText) > 5 || strings.Trim(portText, "0123456789") != "" {{
		return "", 0, false
	}}
	port, _ := strconv.Atoi(portText)
	if port < 1 || port > 65535 {{
		return "", 0, false
	}}
	if strings.ToLower(host) == "localhost" {{
		return "localhost", port, true
	}}
	if strings.Contains(host, "%") {{
		return "", 0, false
	}}
	ip := net.ParseIP(host)
	if ip == nil {{
		return "", 0, false
	}}
	if strings.Contains(host, ":") {{
		if ip.To4() != nil || !ip.Equal(net.IPv6loopback) {{
			return "", 0, false
		}}
		return "::1", port, true
	}}
	if ip.To4() == nil || ip.To4()[0] != 127 {{
		return "", 0, false
	}}
	return ip.String(), port, true
}}

func _ksServeOpenScope(request []string) []string {{
	host, port, ok := _ksParseLoopbackBind(request[1])
	if !ok {{
		return []string{{"err", "KS2411: Serve v1 yalnızca açık loopback host:port kabul eder"}}
	}}
	values := make([]int, 4)
	for index := range values {{
		number, err := strconv.Atoi(request[index+2])
		if err != nil {{
			return nil
		}}
		values[index] = number
	}}
	limits := [][3]int{{{{{min_connections}, {max_connections}}}, {{{min_bytes}, {max_bytes}}}, {{{min_bytes}, {max_bytes}}}, {{{min_deadline}, {max_deadline}}}}}
	names := []string{{"max_connections", "max_request_bytes", "max_response_bytes", "deadline_ms"}}
	for index, value := range values {{
		if value < limits[index][0] || value > limits[index][1] {{
			return []string{{"err", "KS2411: Serve " + names[index] + " " + strconv.Itoa(limits[index][0]) + ".." + strconv.Itoa(limits[index][1]) + " aralığında olmalıdır"}}
		}}
	}}
	_ksServeScopes = append(_ksServeScopes, &_ksServeScope{{
		host: host, port: port, connections: values[0], requestBytes: values[1],
		responseBytes: values[2], deadline: time.Duration(values[3]) * time.Millisecond,
	}})
	return []string{{"ok", strconv.Itoa(len(_ksServeScopes) - 1)}}
}}

var _ksSocketCodes = map[syscall.Errno]string{{
	syscall.EADDRINUSE:    "EADDRINUSE",
	syscall.EADDRNOTAVAIL: "EADDRNOTAVAIL",
	syscall.EACCES:        "EACCES",
	syscall.ECONNRESET:    "ECONNRESET",
	syscall.EPIPE:         "EPIPE",
	syscall.ECONNABORTED:  "ECONNABORTED",
}}

// serve_loopback_exchange_v1.socket_code
func _ksSocketCode(err error) string {{
	var code syscall.Errno
	if errors.As(err, &code) {{
		if name, ok := _ksSocketCodes[code]; ok {{
			return name
		}}
	}}
	return "EIO"
}}

func _ksServeListen(scope *_ksServeScope) error {{
	family := syscall.AF_INET
	if strings.Contains(scope.host, ":") {{
		family = syscall.AF_INET6
	}}
	fd, err := syscall.Socket(family, syscall.SOCK_STREAM|syscall.SOCK_CLOEXEC, 0)
	if err != nil {{
		return err
	}}
	fail := func(err error) error {{
		syscall.Close(fd)
		return err
	}}
	if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_REUSEADDR, 1); err != nil {{
		return fail(err)
	}}
	if family == syscall.AF_INET6 {{
		address := &syscall.SockaddrInet6{{Port: scope.port}}
		copy(address.Addr[:], net.IPv6loopback)
		err = syscall.Bind(fd, address)
	}} else {{
		address := &syscall.SockaddrInet4{{Port: scope.port}}
		host := scope.host
		if host == "localhost" {{
			host = "127.0.0.1"
		}}
		copy(address.Addr[:], net.ParseIP(host).To4())
		err = syscall.Bind(fd, address)
	}}
	if err != nil {{
		return fail(err)
	}}
	backlog := scope.connections
	if backlog > 128 {{
		backlog = 128
	}}
	if err := syscall.Listen(fd, backlog); err != nil {{
		return fail(err)
	}}
	file := os.NewFile(uintptr(fd), "koschei-serve")
	listener, err := net.FileListener(file)
	file.Close()
	if err != nil {{
		return err
	}}
	scope.listener = listener
	return nil
}}

func _ksServeWire(status int64, body string) string {{
	return "HTTP/1.1 " + strconv.FormatInt(status, 10) + " " + _ksReasons[status] + "\r\n" +
		"Content-Type: text/plain; charset=utf-8\r\n" +
		"Content-Length: " + strconv.Itoa(len(body)) + "\r\n" +
		"Connection: close\r\n\r\n" + body
}}

// serve_knowhere_v1._close
func _ksServeClose(conn net.Conn, status int64, deadline time.Time) {{
	if status != 0 {{
		remaining := time.Second
		if !deadline.IsZero() {{
			remaining = time.Until(deadline)
			if remaining < 10*time.Millisecond {{
				remaining = 10 * time.Millisecond
			}}
		}}
		conn.SetWriteDeadline(time.Now().Add(remaining))
		io.WriteString(conn, _ksServeWire(status, _ksReasons[status]))
	}}
	conn.Close()
}}

// Python's str.isspace on Latin-1 text.
func _ksLatinSpace(character byte) bool {{
	switch {{
	case character >= 0x09 && character <= 0x0d, character >= 0x1c && character <= 0x20:
		return true
	case character == 0x85, character == 0xa0:
		return true
	}}
	return false
}}

func _ksLatinStrip(text string) string {{
	start, end := 0, len(text)
	for start < end && _ksLatinSpace(text[start]) {{
		start++
	}}
	for end > start && _ksLatinSpace(text[end-1]) {{
		end--
	}}
	return text[start:end]
}}

func _ksLatinText(raw string) string {{
	runes := make([]rune, len(raw))
	for index := 0; index < len(raw); index++ {{
		runes[index] = rune(raw[index])
	}}
	return string(runes)
}}

// Lowercases ASCII letters only; other bytes (Latin-1 text) stay as they are.
func _ksASCIILower(text string) string {{
	out := []byte(text)
	for index, character := range out {{
		if character >= 'A' && character <= 'Z' {{
			out[index] = character + 32
		}}
	}}
	return string(out)
}}

const _ksTokenChars = "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

func _ksProtocolError(message string) string {{
	return "KS3410: " + message
}}

func _ksIOError(message string) string {{
	return "KS3411: " + message
}}

// The effective request-head rule: serve_loopback_exchange_parity_v1 over
// serve_loopback_http_strict_v1 over serve_loopback_exchange_v1, in that
// order of checks.
func _ksParseRequestHead(raw string) (int, int, string) {{
	marker := strings.Index(raw, "\r\n\r\n")
	if marker < 0 {{
		return 0, 0, _ksProtocolError("HTTP header terminator was not found")
	}}
	if marker+4 > {max_header} {{
		return 0, 0, _ksProtocolError("HTTP headers exceed the hard header limit")
	}}
	lines := strings.Split(raw[:marker], "\r\n")
	if lines[0] == "" {{
		return 0, 0, _ksProtocolError("HTTP request line is missing")
	}}
	parts := strings.Split(lines[0], " ")
	if len(parts) != 3 {{
		return 0, 0, _ksProtocolError("HTTP request line must contain method, target and version")
	}}
	method, target, version := parts[0], parts[1], parts[2]
	if method == "" || strings.Trim(method, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") != "" {{
		return 0, 0, _ksProtocolError("exchange v1 accepts uppercase alphabetic HTTP methods only")
	}}
	printable := target != "" && strings.HasPrefix(target, "/") && !strings.Contains(target, "#")
	for index := 0; printable && index < len(target); index++ {{
		printable = target[index] >= 0x21 && target[index] <= 0x7e
	}}
	if !printable {{
		return 0, 0, _ksProtocolError("exchange v1 requires a printable ASCII origin-form request target")
	}}
	if version != "HTTP/1.0" && version != "HTTP/1.1" {{
		return 0, 0, _ksProtocolError("only HTTP/1.0 and HTTP/1.1 are accepted")
	}}
	hosts, lengths := 0, 0
	length := ""
	emptyHost := false
	for _, line := range lines[1:] {{
		name, rawValue, found := strings.Cut(line, ":")
		if line == "" || !found {{
			return 0, 0, _ksProtocolError("malformed HTTP header line")
		}}
		if name == "" || strings.Trim(name, _ksTokenChars) != "" {{
			return 0, 0, _ksProtocolError("malformed HTTP header name")
		}}
		value := strings.Trim(rawValue, " \t")
		for index := 0; index < len(value); index++ {{
			character := value[index]
			if character != '\t' && (character < 0x20 || character == 0x7f) {{
				return 0, 0, _ksProtocolError("HTTP header value contains a control byte")
			}}
		}}
		switch _ksASCIILower(name) {{
		case "host":
			hosts++
			emptyHost = emptyHost || value == ""
		case "content-length":
			lengths++
			length = _ksLatinStrip(rawValue)
		case "transfer-encoding":
			return 0, 0, _ksProtocolError("Transfer-Encoding is not supported by exchange v1")
		}}
	}}
	if version == "HTTP/1.1" && hosts != 1 {{
		return 0, 0, _ksProtocolError("HTTP/1.1 exchange v1 requires exactly one Host header")
	}}
	if hosts > 1 {{
		return 0, 0, _ksProtocolError("duplicate Host headers are rejected")
	}}
	if lengths > 1 {{
		return 0, 0, _ksProtocolError("duplicate Content-Length headers are rejected")
	}}
	size := 0
	if lengths == 1 {{
		if length == "" || strings.Trim(length, "0123456789") != "" {{
			return 0, 0, _ksProtocolError("Content-Length must be a non-negative decimal integer")
		}}
		parsed, err := strconv.ParseInt(length, 10, 64)
		if err != nil || parsed > 1<<40 {{
			// Python's int has no bound; any such length is over every budget.
			parsed = 1 << 40
		}}
		size = int(parsed)
	}}
	if emptyHost {{
		return 0, 0, _ksProtocolError("Host header may not be empty")
	}}
	return marker + 4, size, ""
}}

// serve_knowhere_v1._read_request: (request fields, status, error)
func _ksServeRead(conn net.Conn, scope *_ksServeScope, deadline time.Time) ([]string, int64, string) {{
	buffer := make([]byte, 0, 4096)
	headerLimit := scope.requestBytes
	if headerLimit > {max_header} {{
		headerLimit = {max_header}
	}}
	chunk := make([]byte, 4096)
	receive := func(limit int) (int, int64, string) {{
		if !time.Now().Before(deadline) {{
			return 0, 400, _ksIOError("request read exceeded the I/O deadline")
		}}
		conn.SetReadDeadline(deadline)
		if limit > 4096 {{
			limit = 4096
		}}
		count, err := conn.Read(chunk[:limit])
		if count > 0 {{
			buffer = append(buffer, chunk[:count]...)
			return count, 0, ""
		}}
		if err == nil || errors.Is(err, io.EOF) {{
			return 0, 0, ""
		}}
		if errors.Is(err, os.ErrDeadlineExceeded) {{
			return 0, 400, _ksIOError("request read exceeded the I/O deadline")
		}}
		return 0, 400, _ksIOError("request read failed: " + _ksSocketCode(err))
	}}
	for strings.Index(string(buffer), "\r\n\r\n") < 0 {{
		if len(buffer) >= headerLimit {{
			return nil, 413, _ksProtocolError("HTTP headers exceed the configured request budget")
		}}
		count, status, message := receive(headerLimit - len(buffer) + 1)
		if status != 0 {{
			return nil, status, message
		}}
		if count == 0 {{
			return nil, 400, _ksProtocolError("connection closed before HTTP headers completed")
		}}
	}}
	bodyStart, length, failure := _ksParseRequestHead(string(buffer))
	if failure != "" {{
		return nil, 400, failure
	}}
	expected := bodyStart + length
	if expected > scope.requestBytes {{
		return nil, 413, _ksProtocolError("request body exceeds max_request_bytes")
	}}
	if len(buffer) > expected {{
		return nil, 400, _ksProtocolError("HTTP pipelining or bytes beyond Content-Length are rejected")
	}}
	for len(buffer) < expected {{
		count, status, message := receive(expected - len(buffer) + 1)
		if status != 0 {{
			return nil, status, message
		}}
		if count == 0 {{
			return nil, 400, _ksProtocolError("connection closed before request body completed")
		}}
		if len(buffer) > expected {{
			return nil, 400, _ksProtocolError("bytes beyond declared Content-Length are rejected")
		}}
	}}
	// serve_knowhere_v1._parse_headers
	lines := strings.Split(string(buffer[:bodyStart-4]), "\r\n")
	parts := strings.Split(lines[0], " ")
	fields := []string{{_ksLatinText(parts[0]), _ksLatinText(parts[1]), string(buffer[bodyStart:expected])}}
	for _, line := range lines[1:] {{
		name, value, _ := strings.Cut(line, ":")
		fields = append(fields, _ksLatinText(_ksASCIILower(name)), _ksLatinText(strings.Trim(value, " \t")))
	}}
	return fields, 0, ""
}}

// The address a scope's listener binds.
func _ksServeAddress(scope *_ksServeScope) string {{
	if scope.host == "localhost" {{
		return "127.0.0.1:" + strconv.Itoa(scope.port)
	}}
	return scope.host + ":" + strconv.Itoa(scope.port)
}}

// Another live server of this program listens on the scope's address.
func _ksServeAddressHeld(scope *_ksServeScope) bool {{
	for _, other := range _ksServeScopes {{
		if other != nil && other != scope && other.listener != nil && _ksServeAddress(other) == _ksServeAddress(scope) {{
			return true
		}}
	}}
	return false
}}

func _ksServeAcceptBroker(scope *_ksServeScope, retry bool) []string {{
	if scope.listener == nil {{
		if err := _ksServeListen(scope); err != nil {{
			if retry && errors.Is(err, syscall.EADDRINUSE) && _ksServeAddressHeld(scope) {{
				// Perhaps by a server whose token was dropped but not yet
				// collected: the worker collects and asks again once.
				return []string{{"busy"}}
			}}
			return []string{{"err", _ksIOError("listener failed: " + _ksSocketCode(err))}}
		}}
	}}
	if scope.pending != nil {{
		_ksServeClose(scope.pending, 500, time.Time{{}})
		scope.pending = nil
		return []string{{"err", {pending}}}
	}}
	if scope.accepted >= scope.connections {{
		return []string{{"err", {budget_prefix} + strconv.Itoa(scope.connections) + {budget_suffix}}}
	}}
	deadline := time.Now().Add(scope.deadline)
	scope.listener.(*net.TCPListener).SetDeadline(deadline)
	conn, err := scope.listener.Accept()
	if err != nil {{
		if errors.Is(err, os.ErrDeadlineExceeded) {{
			return []string{{"err", _ksIOError("accept exceeded the I/O deadline")}}
		}}
		return []string{{"err", _ksIOError("accept failed: " + _ksSocketCode(err))}}
	}}
	scope.accepted++
	fields, status, message := _ksServeRead(conn, scope, deadline)
	if status != 0 {{
		_ksServeClose(conn, status, deadline)
		return []string{{"err", message}}
	}}
	scope.pending = conn
	return append([]string{{"ok"}}, fields...)
}}

func _ksServeReplyBroker(scope *_ksServeScope, statusText string, kind string, body string) []string {{
	if scope.pending == nil {{
		return []string{{"err", {no_pending}}}
	}}
	conn := scope.pending
	scope.pending = nil
	status, err := strconv.ParseInt(statusText, 10, 64)
	if _, known := _ksReasons[status]; err != nil || !known {{
		_ksServeClose(conn, 500, time.Time{{}})
		return []string{{"err", {status_prefix} + statusText + {status_suffix}}}
	}}
	if kind != "s" && kind != "b" {{
		return nil
	}}
	if status == 204 && body != "" {{
		_ksServeClose(conn, 500, time.Time{{}})
		return []string{{"err", {empty_body}}}
	}}
	wire := _ksServeWire(status, body)
	if len(wire) > scope.responseBytes {{
		_ksServeClose(conn, 500, time.Time{{}})
		return []string{{"err", _ksProtocolError("response exceeds max_response_bytes")}}
	}}
	defer conn.Close()
	conn.SetWriteDeadline(time.Now().Add(scope.deadline))
	if _, err := io.WriteString(conn, wire); err != nil {{
		if errors.Is(err, os.ErrDeadlineExceeded) {{
			return []string{{"err", _ksIOError("response write exceeded the I/O deadline")}}
		}}
		return []string{{"err", _ksIOError("response write failed: " + _ksSocketCode(err))}}
	}}
	return []string{{"ok"}}
}}

func _ksBrokerServeServe(request []string) ([]string, bool) {{
	switch {{
	case request[0] == "serve_scope" && len(request) == 6:
		answer := _ksServeOpenScope(request)
		return answer, answer != nil
	case (request[0] == "serve_accept" && len(request) == 3 && (request[2] == "retry" || request[2] == "final")) ||
		(request[0] == "serve_reply" && len(request) == 5) || (request[0] == "serve_release" && len(request) == 2):
		index, err := strconv.Atoi(request[1])
		// A released server is never addressed again.
		if err != nil || index < 1 || index >= len(_ksServeScopes) || _ksServeScopes[index] == nil {{
			return nil, false
		}}
		scope := _ksServeScopes[index]
		var answer []string
		switch request[0] {{
		case "serve_accept":
			answer = _ksServeAcceptBroker(scope, request[2] == "retry")
		case "serve_reply":
			answer = _ksServeReplyBroker(scope, request[2], request[3], request[4])
		default:
			// serve_knowhere_v1: a dropped server's sockets close, the
			// listener first (_Server's slot order); an unanswered client
			// sees its connection close.
			if scope.listener != nil {{
				scope.listener.Close()
			}}
			if scope.pending != nil {{
				scope.pending.Close()
			}}
			_ksServeScopes[index] = nil
			answer = []string{{"ok"}}
		}}
		return answer, answer != nil
	}}
	return nil, false
}}

func init() {{
	_ksBrokerServers = _ksBrokerServeServe
}}
'''

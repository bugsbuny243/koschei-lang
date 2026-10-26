"""Native ``NetCaps.get`` through the capability broker (readiness gate G2).

The worker cannot open sockets (``native_broker_v1``), so a request is a
message to the broker, which applies ``net_v1``'s rules: the same URL
grammar, origin check, headers, redirect loop, status handling, body budget,
UTF-8 rule, proxy choice and failure codes as ``ks run``. Only programs that
use the network carry this fragment and ``net/http``.
"""

from __future__ import annotations

from . import net_v1
from .http_response_budget_v1 import (
    HTTP_CONTENT_ENCODING_ERROR_V1,
    HTTP_RESPONSE_BUDGET_ERROR_V1,
    HTTP_RESPONSE_MAX_BYTES_V1,
)

NET_IMPORTS = ("context", "crypto/tls", "crypto/x509", "errors", "io", "net", "net/http", "net/url", "time")


def _go(value: str) -> str:
    from .mir_go_native import _go_string

    return _go_string(value)


def net_runtime() -> str:
    statuses = ", ".join(str(code) for code in sorted(net_v1.REDIRECT_STATUSES))
    return _NET_RUNTIME.format(
        user_agent=_go(net_v1.USER_AGENT),
        timeout=net_v1.TIMEOUT_SECONDS,
        max_redirects=net_v1.MAX_REDIRECTS,
        statuses=statuses,
        outside=_go(net_v1.OUTSIDE_PREFIX),
        redirect=_go(net_v1.REDIRECT_PREFIX),
        failed=_go(net_v1.FAILED_PREFIX),
        too_many=_go(net_v1.TOO_MANY_REDIRECTS),
        not_text=_go(net_v1.NOT_TEXT_PREFIX),
        invalid_target=_go(net_v1.INVALID_TARGET),
        max_body=HTTP_RESPONSE_MAX_BYTES_V1,
        budget=_go(f"{HTTP_RESPONSE_BUDGET_ERROR_V1}: HTTP response body exceeds {HTTP_RESPONSE_MAX_BYTES_V1} byte budget"),
        encoding=_go(f"{HTTP_CONTENT_ENCODING_ERROR_V1}: unsupported HTTP content encoding: "),
    )


_NET_RUNTIME = r'''
// ---- network through the broker (native_net_v1, rules of net_v1) ---------

func _ksCapsNet(receiver any) any {{
	if _, ok := receiver.(_ksSystemCaps); !ok {{
		_ksAbort("KS5002", "SystemCaps.net receiver drifted")
	}}
	return _ksNetRoot{{}}
}}

func _ksNetAllow(receiver any, origin any) any {{
	if _, ok := receiver.(_ksNetRoot); !ok {{
		_ksAbort("KS5002", "NetRoot receiver drifted")
	}}
	text, ok := origin.(string)
	if !ok {{
		_ksAbort("KS5002", "NetRoot.allow origin drifted")
	}}
	_, answer := _ksAsk("net_scope", text)
	return _ksNetCaps{{scope: answer[0]}}
}}

func _ksNetGet(receiver any, address any) any {{
	caps, ok := receiver.(_ksNetCaps)
	if !ok {{
		_ksAbort("KS5002", "NetCaps receiver drifted")
	}}
	text, ok := address.(string)
	if !ok {{
		_ksAbort("KS5002", "NetCaps.get url drifted")
	}}
	done, answer := _ksAsk("net_get", caps.scope, text)
	if !done {{
		return _ksError{{message: answer[0]}}
	}}
	if len(answer) != 2 {{
		_ksAbort("KS5002", "native broker answer drifted")
	}}
	status, err := strconv.ParseInt(answer[0], 10, 64)
	if err != nil {{
		_ksAbort("KS5002", "native broker answer drifted")
	}}
	return _ksResponse{{status: status, body: answer[1]}}
}}

// ---- broker side ----------------------------------------------------------

type _ksURL struct {{
	scheme string
	host   string
	port   int
	target string
}}

func (u _ksURL) origin() string {{
	return u.scheme + " " + u.host + " " + strconv.Itoa(u.port)
}}

func (u _ksURL) authority() string {{
	host := u.host
	if strings.Contains(host, ":") {{
		host = "[" + host + "]"
	}}
	if (u.scheme == "https" && u.port == 443) || (u.scheme == "http" && u.port == 80) {{
		return host
	}}
	return host + ":" + strconv.Itoa(u.port)
}}

func (u _ksURL) text() string {{
	return u.scheme + "://" + u.authority() + u.target
}}

func _ksPrintable(text string) bool {{
	for index := 0; index < len(text); index++ {{
		if text[index] < 0x21 || text[index] > 0x7e {{
			return false
		}}
	}}
	return true
}}

func _ksAllIn(text string, allowed string) bool {{
	for index := 0; index < len(text); index++ {{
		if strings.IndexByte(allowed, text[index]) < 0 {{
			return false
		}}
	}}
	return true
}}

const _ksTargetChars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~:/?[]@!$&'()*+,;=%"
const _ksHexChars = "0123456789abcdefABCDEF"

func _ksValidTarget(target string) bool {{
	if !_ksAllIn(target, _ksTargetChars) {{
		return false
	}}
	for index := 0; index < len(target); index++ {{
		if target[index] == '%' {{
			if index+2 >= len(target) || strings.IndexByte(_ksHexChars, target[index+1]) < 0 || strings.IndexByte(_ksHexChars, target[index+2]) < 0 {{
				return false
			}}
			index += 2
		}}
	}}
	return true
}}

// net_v1.parse_url
func _ksParseURL(raw string) (_ksURL, bool) {{
	if !_ksPrintable(raw) {{
		return _ksURL{{}}, false
	}}
	separator := strings.Index(raw, "://")
	if separator <= 0 {{
		return _ksURL{{}}, false
	}}
	scheme := strings.ToLower(raw[:separator])
	first := scheme[0]
	if first < 'a' || first > 'z' || !_ksAllIn(scheme, "abcdefghijklmnopqrstuvwxyz0123456789+.-") {{
		return _ksURL{{}}, false
	}}
	if scheme != "http" && scheme != "https" {{
		return _ksURL{{}}, false
	}}
	rest := raw[separator+3:]
	end := len(rest)
	if found := strings.IndexAny(rest, "/?#"); found != -1 {{
		end = found
	}}
	authority, remainder := rest[:end], rest[end:]
	if authority == "" || strings.Contains(authority, "@") {{
		return _ksURL{{}}, false
	}}
	var host, portText string
	hasPort := false
	if strings.HasPrefix(authority, "[") {{
		close := strings.Index(authority, "]")
		if close == -1 {{
			return _ksURL{{}}, false
		}}
		host = strings.ToLower(authority[1:close])
		after := authority[close+1:]
		if host == "" || !_ksAllIn(host, "0123456789abcdef:.") {{
			return _ksURL{{}}, false
		}}
		if after != "" {{
			if !strings.HasPrefix(after, ":") {{
				return _ksURL{{}}, false
			}}
			portText, hasPort = after[1:], true
		}}
	}} else {{
		name, port, colon := strings.Cut(authority, ":")
		host = strings.ToLower(name)
		if host == "" || !_ksAllIn(host, "abcdefghijklmnopqrstuvwxyz0123456789.-_") {{
			return _ksURL{{}}, false
		}}
		portText, hasPort = port, colon
	}}
	port := 80
	if scheme == "https" {{
		port = 443
	}}
	if hasPort {{
		if portText == "" || len(portText) > 5 || !_ksAllIn(portText, "0123456789") {{
			return _ksURL{{}}, false
		}}
		port, _ = strconv.Atoi(portText)
		if port < 1 || port > 65535 {{
			return _ksURL{{}}, false
		}}
	}}
	target, _, _ := strings.Cut(remainder, "#")
	if !strings.HasPrefix(target, "/") {{
		target = "/" + target
	}}
	if !_ksValidTarget(target) {{
		return _ksURL{{}}, false
	}}
	return _ksURL{{scheme: scheme, host: host, port: port, target: target}}, true
}}

// net_v1.resolve_location
func _ksResolveLocation(base _ksURL, location string) (_ksURL, bool) {{
	if !_ksPrintable(location) {{
		return _ksURL{{}}, false
	}}
	head, _, _ := strings.Cut(location, "?")
	head, _, _ = strings.Cut(head, "#")
	if strings.Contains(head, "://") {{
		return _ksParseURL(location)
	}}
	if strings.HasPrefix(location, "//") {{
		return _ksParseURL(base.scheme + ":" + location)
	}}
	location, _, _ = strings.Cut(location, "#")
	path, _, _ := strings.Cut(base.target, "?")
	var target string
	switch {{
	case strings.HasPrefix(location, "/"):
		target = location
	case location == "" || strings.HasPrefix(location, "?"):
		target = path + location
	default:
		target = path[:strings.LastIndex(path, "/")+1] + location
	}}
	return _ksParseURL(base.scheme + "://" + base.authority() + target)
}}

// The address family is decided by the text, as ipaddress.ip_address does.
func _ksIPOf(text string) (net.IP, bool, bool) {{
	ip := net.ParseIP(text)
	if ip == nil {{
		return nil, false, false
	}}
	return ip, strings.Contains(text, ":"), true
}}

func _ksIsLoopback(host string) bool {{
	if host == "localhost" || strings.HasSuffix(host, ".localhost") {{
		return true
	}}
	ip, six, ok := _ksIPOf(host)
	if !ok {{
		return false
	}}
	if six {{
		return ip.Equal(net.IPv6loopback) && ip.To4() == nil
	}}
	return ip.To4()[0] == 127
}}

func _ksEnvironment(name string) string {{
	value, found := os.LookupEnv(strings.ToLower(name))
	if !found {{
		value = os.Getenv(strings.ToUpper(name))
	}}
	return strings.TrimSpace(value)
}}

// net_v1._bypassed
func _ksBypassed(host string, port int, noProxy string) bool {{
	if noProxy == "*" {{
		return true
	}}
	address, addressSix, isIP := _ksIPOf(host)
	for _, raw := range strings.Split(noProxy, ",") {{
		entry := strings.ToLower(strings.TrimSpace(raw))
		if entry == "" {{
			continue
		}}
		entryPort, hasPort := "", false
		if strings.HasPrefix(entry, "[") {{
			close := strings.Index(entry, "]")
			if close == -1 {{
				continue
			}}
			if strings.HasPrefix(entry[close+1:], ":") {{
				entryPort, hasPort = entry[close+2:], true
			}}
			entry = entry[1:close]
		}} else if strings.Count(entry, ":") == 1 {{
			entry, entryPort, _ = strings.Cut(entry, ":")
			hasPort = true
		}}
		if hasPort && entryPort != strconv.Itoa(port) {{
			continue
		}}
		if strings.Contains(entry, "/") {{
			_, network, err := net.ParseCIDR(entry)
			if err != nil {{
				continue
			}}
			if isIP && addressSix == strings.Contains(entry, ":") && network.Contains(address) {{
				return true
			}}
			continue
		}}
		if entryAddress, entrySix, ok := _ksIPOf(entry); ok {{
			if isIP && addressSix == entrySix && address.Equal(entryAddress) {{
				return true
			}}
			continue
		}}
		entry = strings.TrimPrefix(entry, "*")
		if strings.HasPrefix(entry, ".") {{
			if strings.HasSuffix(host, entry) || host == entry[1:] {{
				return true
			}}
		}} else if host == entry || strings.HasSuffix(host, "."+entry) {{
			return true
		}}
	}}
	return false
}}

// net_v1.proxy_for
func _ksProxyFor(target _ksURL) string {{
	if _ksIsLoopback(target.host) || _ksBypassed(target.host, target.port, _ksEnvironment("no_proxy")) {{
		return ""
	}}
	proxy := _ksEnvironment(target.scheme + "_proxy")
	if proxy == "" {{
		return ""
	}}
	if !strings.Contains(proxy, "://") {{
		proxy = "http://" + proxy
	}}
	return proxy
}}

type _ksNetScope struct {{
	origin   _ksURL
	valid    bool
	broken   bool
	proxied  bool
	client   *http.Client
}}

// Every read and write on a connection must make progress within the
// timeout, like a Python socket timeout.
type _ksIdleConn struct {{
	net.Conn
}}

func (c _ksIdleConn) Read(buffer []byte) (int, error) {{
	c.Conn.SetReadDeadline(time.Now().Add({timeout} * time.Second))
	return c.Conn.Read(buffer)
}}

func (c _ksIdleConn) Write(buffer []byte) (int, error) {{
	c.Conn.SetWriteDeadline(time.Now().Add({timeout} * time.Second))
	return c.Conn.Write(buffer)
}}

func _ksNetOpenScope(origin string) *_ksNetScope {{
	parsed, ok := _ksParseURL(origin)
	scope := &_ksNetScope{{origin: parsed, valid: ok}}
	if !ok {{
		return scope
	}}
	var proxyURL *url.URL
	if proxy := _ksProxyFor(parsed); proxy != "" {{
		if !strings.HasPrefix(strings.ToLower(proxy), "http://") {{
			scope.broken = true
			return scope
		}}
		parsedProxy, err := url.Parse(proxy)
		if err != nil {{
			scope.broken = true
			return scope
		}}
		if parsedProxy.User != nil {{
			password, set := parsedProxy.User.Password()
			if parsedProxy.User.Username() == "" || !set || password == "" {{
				parsedProxy.User = nil
			}}
		}}
		proxyURL = parsedProxy
		scope.proxied = true
	}}
	dialer := &net.Dialer{{Timeout: {timeout} * time.Second}}
	transport := &http.Transport{{
		Proxy: func(*http.Request) (*url.URL, error) {{ return proxyURL, nil }},
		DialContext: func(ctx context.Context, network string, address string) (net.Conn, error) {{
			conn, err := dialer.DialContext(ctx, network, address)
			if err != nil {{
				return nil, err
			}}
			return _ksIdleConn{{conn}}, nil
		}},
		TLSHandshakeTimeout: {timeout} * time.Second,
		DisableCompression:  true,
		DisableKeepAlives:   true,
		TLSNextProto:        map[string]func(string, *tls.Conn) http.RoundTripper{{}},
	}}
	scope.client = &http.Client{{
		Transport: transport,
		CheckRedirect: func(*http.Request, []*http.Request) error {{
			return http.ErrUseLastResponse
		}},
	}}
	return scope
}}

// net_v1.failure_code
func _ksNetFailure(err error) string {{
	var dns *net.DNSError
	var unknown x509.UnknownAuthorityError
	var hostname x509.HostnameError
	var invalid x509.CertificateInvalidError
	var verification *tls.CertificateVerificationError
	var record tls.RecordHeaderError
	var alert tls.AlertError
	var timeout interface{{ Timeout() bool }}
	switch {{
	case errors.Is(err, syscall.ECONNREFUSED):
		return "ECONNREFUSED"
	case errors.Is(err, syscall.ECONNRESET), errors.Is(err, syscall.EPIPE), errors.Is(err, syscall.ECONNABORTED),
		errors.Is(err, io.EOF), errors.Is(err, io.ErrUnexpectedEOF):
		return "ECONNRESET"
	case errors.Is(err, syscall.ETIMEDOUT), errors.Is(err, os.ErrDeadlineExceeded), errors.Is(err, context.DeadlineExceeded):
		return "ETIMEDOUT"
	case errors.As(err, &timeout) && timeout.Timeout():
		return "ETIMEDOUT"
	case errors.Is(err, syscall.EHOSTUNREACH):
		return "EHOSTUNREACH"
	case errors.Is(err, syscall.ENETUNREACH):
		return "ENETUNREACH"
	case errors.As(err, &dns):
		return "EDNS"
	case errors.As(err, &unknown), errors.As(err, &hostname), errors.As(err, &invalid),
		errors.As(err, &verification), errors.As(err, &record), errors.As(err, &alert):
		return "ETLS"
	case strings.Contains(err.Error(), "malformed HTTP"):
		return "EPROTO"
	}}
	return "EIO"
}}

func _ksIsRedirect(status int) bool {{
	switch status {{
	case {statuses}:
		return true
	}}
	return false
}}

func _ksBrokerNetGet(scope *_ksNetScope, raw string) []string {{
	current, ok := _ksParseURL(raw)
	if !scope.valid || !ok || current.origin() != scope.origin.origin() {{
		return []string{{"err", {outside} + raw}}
	}}
	if scope.broken {{
		return []string{{"err", {failed} + "EIO: " + raw}}
	}}
	redirects := 0
	for {{
		path, query, hasQuery := strings.Cut(current.target, "?")
		requestURL := &url.URL{{Scheme: current.scheme, Host: current.authority(), Opaque: path, RawQuery: query, ForceQuery: hasQuery && query == ""}}
		if scope.proxied && current.scheme == "http" {{
			// A forwarding proxy is sent the absolute URL, as Python does.
			requestURL.Opaque = "//" + current.authority() + path
		}}
		request := &http.Request{{
			Method:     http.MethodGet,
			URL:        requestURL,
			Host:       current.authority(),
			Header:     http.Header{{"User-Agent": {{{user_agent}}}, "Accept-Encoding": {{"identity"}}}},
			Close:      true,
			Proto:      "HTTP/1.1",
			ProtoMajor: 1,
			ProtoMinor: 1,
		}}
		response, err := scope.client.Do(request)
		if err != nil {{
			return []string{{"err", {failed} + _ksNetFailure(err) + ": " + raw}}
		}}
		location := ""
		if _ksIsRedirect(response.StatusCode) {{
			location = response.Header.Get("Location")
		}}
		if location == "" {{
			encoding := strings.TrimSpace(response.Header.Get("Content-Encoding"))
			if lowered := strings.ToLower(encoding); lowered != "" && lowered != "identity" {{
				response.Body.Close()
				return []string{{"err", {encoding} + encoding}}
			}}
			body, err := io.ReadAll(io.LimitReader(response.Body, {max_body}+1))
			response.Body.Close()
			if err != nil {{
				return []string{{"err", {failed} + _ksNetFailure(err) + ": " + raw}}
			}}
			if len(body) > {max_body} {{
				return []string{{"err", {budget}}}
			}}
			if !utf8.Valid(body) {{
				return []string{{"err", {not_text} + raw}}
			}}
			return []string{{"ok", strconv.Itoa(response.StatusCode), string(body)}}
		}}
		response.Body.Close()
		target, ok := _ksResolveLocation(current, location)
		if !ok || target.origin() != scope.origin.origin() {{
			shown := location
			if ok {{
				shown = target.text()
			}} else if !_ksPrintable(location) {{
				shown = {invalid_target}
			}}
			return []string{{"err", {redirect} + shown}}
		}}
		redirects++
		if redirects > {max_redirects} {{
			return []string{{"err", {failed} + {too_many} + ": " + raw}}
		}}
		current = target
	}}
}}

var _ksNetScopes = []*_ksNetScope{{nil}}

func _ksBrokerNetServe(request []string) ([]string, bool) {{
	switch {{
	case request[0] == "net_scope" && len(request) == 2:
		_ksNetScopes = append(_ksNetScopes, _ksNetOpenScope(request[1]))
		return []string{{"ok", strconv.Itoa(len(_ksNetScopes) - 1)}}, true
	case request[0] == "net_get" && len(request) == 3:
		index, err := strconv.Atoi(request[1])
		if err != nil || index < 1 || index >= len(_ksNetScopes) {{
			return nil, false
		}}
		return _ksBrokerNetGet(_ksNetScopes[index], request[2]), true
	}}
	return nil, false
}}

func init() {{
	_ksBrokerNet = _ksBrokerNetServe
}}
'''

# kcage: Koschei's capability manifest for any program

Status: **prototype**. Requirements: linux/amd64, Linux 6.7+ (Landlock ABI 4) and
unprivileged user namespaces.

A Koschei program declares everything it can reach up front, and the compiler
and the native broker enforce that list. `kcage` brings the same idea to
programs that are not written in Koschei: a Python script, a Node tool, an AI
agent's generated code, any binary.

```json
{
  "read":  ["agent.py", "data"],
  "write": ["out"],
  "env":   ["OPENAI_API_KEY"],
  "net":   ["api.openai.com:443"]
}
```

```sh
kcage caps manifest.json                   # print what the program may reach
kcage run  manifest.json -- python3 agent.py
```

The kernel refuses anything outside the manifest. The program does not have to
cooperate:

| Authority | How it is enforced |
|---|---|
| Files | Landlock grants read-only and read-write paths. Everything else fails with `EACCES`, including the program's own source if it is not listed. Interpreter directories (`/usr`, `/lib`, TLS roots) stay readable unless `"system": false` |
| Environment | The program starts with an empty environment plus the listed variables |
| Network | The program gets its own network namespace with only loopback. Landlock lets it connect to one local port: a proxy that `kcage` runs outside the namespace. The proxy forwards only to the listed `host:port` pairs and logs every refusal. A program that ignores the proxy has no route out, including UDP and DNS |
| Other processes | Landlock scoping blocks signals to processes outside the sandbox and their abstract unix sockets |
| Gaps Landlock leaves | seccomp refuses `socket(AF_UNIX)`, so `docker.sock` and other host sockets are unreachable. It also refuses `chmod`, `chown`, xattrs and `io_uring` |

## Demo

`demo/agent.py` first does its job: it reads `data/`, writes `out/` and calls
`pypi.org`. Then it tries what a hijacked agent would. Under
`demo/manifest.json` the output is:

```
kcage: allowed pypi.org:443
kcage: DENIED evil.example.com:443 (not in manifest)
[OK]      read data/input.txt
[OK]      write out/result.txt
[OK]      call pypi.org: 200
[BLOCKED] read ~/.ssh/id_rsa: PermissionError
[BLOCKED] read /etc/hostname: PermissionError
[BLOCKED] overwrite agent.py itself: PermissionError
[BLOCKED] delete data/input.txt: PermissionError
[BLOCKED] read secret env AWS_SECRET_ACCESS_KEY: KeyError
[BLOCKED] send data to evil.example.com: 403 Forbidden
[BLOCKED] raw TCP to 1.1.1.1:443, bypassing the proxy: PermissionError
```

## Tests

`go test ./...` builds `kcage` and runs probe scripts inside it. Each listed
authority must work. Each of the following must be refused:

- reads outside the manifest
- writes, deletes, renames and `chmod` on read-only files
- unlisted environment variables
- other processes' `/proc` entries
- unix sockets
- direct TCP and UDP
- unlisted hosts

With the seccomp filter removed, the test fails on `chmod` and on the unix
socket. The tests skip where the kernel lacks Landlock ABI 4 or user
namespaces.

## Limits (prototype)

- linux/amd64 only. The manifest format is JSON.
- Network rules match host names through an HTTP(S) proxy. A program that does
  not honour `HTTPS_PROXY` gets no network at all.
- `utimes` (changing timestamps) on read-only files is not refused.
- No one outside the project has reviewed it yet.

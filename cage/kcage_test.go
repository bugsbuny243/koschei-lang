package main

import (
	"bytes"
	"encoding/json"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// buildKcage builds the binary once per test run.
func buildKcage(t *testing.T) string {
	t.Helper()
	binary := filepath.Join(t.TempDir(), "kcage")
	build := exec.Command("go", "build", "-o", binary, ".")
	build.Env = append(os.Environ(), "CGO_ENABLED=0")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build: %v\n%s", err, out)
	}
	return binary
}

func requireSandbox(t *testing.T, binary string) {
	t.Helper()
	if abi := landlockABI(); abi < 4 {
		t.Skipf("Landlock ABI %d < 4", abi)
	}
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not installed")
	}
	probe := exec.Command("unshare", "-rn", "true")
	if err := probe.Run(); err != nil {
		t.Skipf("unprivileged user namespaces unavailable: %v", err)
	}
}

type sandbox struct {
	dir      string
	manifest string
}

func newSandbox(t *testing.T, script string, net []string) sandbox {
	t.Helper()
	dir := t.TempDir()
	for _, sub := range []string{"data", "out"} {
		if err := os.Mkdir(filepath.Join(dir, sub), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	os.WriteFile(filepath.Join(dir, "data", "input.txt"), []byte("hello"), 0o644)
	os.WriteFile(filepath.Join(dir, "secret.txt"), []byte("TOP-SECRET"), 0o644)
	os.WriteFile(filepath.Join(dir, "script.py"), []byte(script), 0o644)
	manifest := map[string]any{
		"read":  []string{"script.py", "data"},
		"write": []string{"out"},
		"env":   []string{"KCAGE_ALLOWED"},
		"net":   net,
	}
	data, _ := json.Marshal(manifest)
	path := filepath.Join(dir, "manifest.json")
	os.WriteFile(path, data, 0o644)
	return sandbox{dir: dir, manifest: path}
}

func (s sandbox) run(t *testing.T, binary string) (string, string) {
	t.Helper()
	cmd := exec.Command(binary, "run", s.manifest, "--", "python3", "script.py")
	cmd.Dir = s.dir
	cmd.Env = append(os.Environ(), "KCAGE_ALLOWED=yes", "KCAGE_SECRET=leaked")
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		t.Fatalf("kcage run: %v\nstdout:\n%s\nstderr:\n%s", err, stdout.String(), stderr.String())
	}
	return stdout.String(), stderr.String()
}

const probes = `
import os, socket
def t(label, f):
    try:
        f(); print("ALLOWED", label)
    except Exception as e:
        print("DENIED", label, type(e).__name__)
t("read-data", lambda: open("data/input.txt").read())
t("write-out", lambda: open("out/result.txt", "w").write("x"))
t("env-allowed", lambda: os.environ["KCAGE_ALLOWED"])
t("read-secret", lambda: open("secret.txt").read())
t("write-data", lambda: open("data/input.txt", "a").write("x"))
t("delete-data", lambda: os.remove("data/input.txt"))
t("rename-out-of-data", lambda: os.rename("data/input.txt", "out/moved.txt"))
t("chmod-data", lambda: os.chmod("data/input.txt", 0o777))
t("env-secret", lambda: os.environ["KCAGE_SECRET"])
t("read-etc-hostname", lambda: open("/etc/hostname").read())
t("read-proc-1", lambda: open("/proc/1/environ", "rb").read())
t("unix-socket", lambda: socket.socket(socket.AF_UNIX))
t("tcp-direct", lambda: socket.create_connection(("127.0.0.1", 22), timeout=2))
t("udp-out", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("8.8.8.8", 53)))
`

func verdicts(out string) map[string]string {
	result := map[string]string{}
	for _, line := range strings.Split(out, "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 {
			result[fields[1]] = fields[0]
		}
	}
	return result
}

func TestManifestIsTheWholeAuthority(t *testing.T) {
	binary := buildKcage(t)
	requireSandbox(t, binary)
	box := newSandbox(t, probes, nil)
	out, _ := box.run(t, binary)
	got := verdicts(out)
	want := map[string]string{
		"read-data": "ALLOWED", "write-out": "ALLOWED", "env-allowed": "ALLOWED",
		"read-secret": "DENIED", "write-data": "DENIED", "delete-data": "DENIED",
		"rename-out-of-data": "DENIED", "chmod-data": "DENIED", "env-secret": "DENIED",
		"read-etc-hostname": "DENIED", "read-proc-1": "DENIED", "unix-socket": "DENIED",
		"tcp-direct": "DENIED", "udp-out": "DENIED",
	}
	for probe, verdict := range want {
		if got[probe] != verdict {
			t.Errorf("%s: got %q, want %q\n%s", probe, got[probe], verdict, out)
		}
	}
	if data, _ := os.ReadFile(filepath.Join(box.dir, "data", "input.txt")); string(data) != "hello" {
		t.Errorf("data/input.txt changed: %q", data)
	}
}

func TestNetworkGoesOnlyToListedHosts(t *testing.T) {
	binary := buildKcage(t)
	requireSandbox(t, binary)
	// A local upstream stands in for the internet; it must not need the host's proxy.
	t.Setenv("HTTPS_PROXY", "")
	t.Setenv("https_proxy", "")
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			conn.Write([]byte("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"))
			conn.Close()
		}
	}()
	allowed := listener.Addr().String()
	script := `
import urllib.request
def t(label, url):
    try:
        print("ALLOWED", label, urllib.request.urlopen(url, timeout=10).read().decode())
    except Exception as e:
        print("DENIED", label, type(e).__name__)
t("listed", "http://` + allowed + `/")
t("unlisted", "http://127.0.0.1:1/")
`
	box := newSandbox(t, script, []string{allowed})
	out, stderr := box.run(t, binary)
	got := verdicts(out)
	if got["listed"] != "ALLOWED" || got["unlisted"] != "DENIED" {
		t.Fatalf("network verdicts %v\nstdout:\n%s\nstderr:\n%s", got, out, stderr)
	}
	if !strings.Contains(stderr, "DENIED 127.0.0.1:1") {
		t.Errorf("proxy did not log the refusal:\n%s", stderr)
	}
}

func TestManifestRejectsBadNetEntries(t *testing.T) {
	path := filepath.Join(t.TempDir(), "m.json")
	os.WriteFile(path, []byte(`{"net": ["no-port"]}`), 0o644)
	if _, err := loadManifest(path); err == nil {
		t.Fatal("accepted a net entry without a port")
	}
	os.WriteFile(path, []byte(`{"nett": []}`), 0o644)
	if _, err := loadManifest(path); err == nil {
		t.Fatal("accepted an unknown field")
	}
}

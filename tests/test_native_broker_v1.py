"""Native capability broker (G2, first step): read-only disk and environment.

The binary must give the same answers as `ks run`, the worker must run
confined with an empty environment, and the confinement must actually stop
file, socket and exec system calls.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from koschei.cli_entry import main as cli_main
from koschei.mir_go_native import generate_go_mir_native, inspect_mir_go_support
from koschei.modules import check_graph, load_graph

ROOT = Path(__file__).resolve().parent.parent
GO = shutil.which("go")
SUPPORTED = GO is not None and sys.platform == "linux" and platform.machine() in {"x86_64", "AMD64"}

PROGRAM = """
fn main(caps: SystemCaps) {
    let disk = caps.disk.allow_read_only("root")
    println(disk.read("root/a.txt"))
    println(disk.read_bytes("root/bin.dat"))
    println(disk.read("root/bin.dat"))
    println(disk.read("root/link"))
    println(disk.read("root/sublink/inner.txt"))
    println(disk.read("root/sub/../a.txt"))
    println(disk.read("./root/sub/inner.txt"))
    println(disk.read("root/missing"))
    println(disk.read("root/sub"))
    println(disk.read("root"))
    println(disk.read("/etc/passwd"))
    println(disk.read("root/../../x"))
    println(disk.read("rootless/a.txt"))
    println(disk.list("root"))
    println(disk.list("root/sub"))
    println(disk.list("root/a.txt"))
    println(disk.list("root/sublink"))
    let other = caps.disk.allow_read_only("missing-scope")
    println(other.read("missing-scope/x"))
    let linked = caps.disk.allow_read_only("rootlink")
    println(linked.read("rootlink/a.txt"))
    println(linked.read("root/a.txt"))
    println(caps.env.allow("KS_TEST_VALUE").get())
    println(caps.env.allow("KS_TEST_MISSING").get())
    println(caps.env.allow("KS_TEST_BINARY").get())
}
"""


def _refused_after_confinement(trace: str) -> list[str]:
    """Calls the worker (and its threads) saw refused after seccomp."""

    first, worker, pending, refused, confined = None, set(), {}, [], False
    for line in trace.splitlines():
        match = re.match(r"(\d+)\s+(.*)", line)
        if not match:
            continue
        pid, rest = int(match.group(1)), match.group(2)
        first = pid if first is None else first
        resumed = re.match(r"<\.\.\. (\w+) resumed>(.*)", rest)
        if resumed:
            name, full = resumed.group(1), pending.pop(pid, "") + resumed.group(2)
        else:
            call = re.match(r"(\w+)\((.*)", rest)
            if not call:
                continue
            name, full = call.group(1), rest
            if "<unfinished" in rest:
                pending[pid] = rest
                continue
        if name == "execve" and pid != first and full.rstrip().endswith("= 0"):
            worker.add(pid)
        if pid not in worker:
            continue
        if name in ("clone", "clone3"):
            child = re.search(r"= (\d+)", full)
            if child:
                worker.add(int(child.group(1)))
        if name == "seccomp":
            confined = True
        elif confined and re.search(r"= -1 (EPERM|ENOSYS)", full):
            refused.append(full)
    return refused


WRITES = """
fn main(caps: SystemCaps) {
    let disk = caps.disk.allow("root")
    println(disk.write("root/new.txt", "yeni\\r\\nsatır"))
    println(disk.read("root/new.txt"))
    println(disk.write("root/keep.txt", "replaced"))
    println(disk.write("root/link", "x"))
    println(disk.write("root/sublink/x.txt", "x"))
    println(disk.write("root/dir", "x"))
    println(disk.write("root/missing/x.txt", "x"))
    println(disk.write("root", "x"))
    println(disk.write("/tmp/outside.txt", "x"))
    println(disk.write_file("root/sub/inner.txt", "iç"))
    println(disk.read_bytes("root/sub/inner.txt"))
    println(disk.delete("root/sub/inner.txt"))
    println(disk.delete("root/sub/inner.txt"))
    println(disk.delete("root/link"))
    println(disk.delete("root/dir"))
    println(disk.delete("root"))
    println(disk.list("root"))
}
"""


def workspace() -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory(prefix="koschei-broker-")
    base = Path(directory.name)
    (base / "root" / "sub").mkdir(parents=True)
    (base / "root" / "a.txt").write_bytes("merhaba\r\ndünya".encode())
    (base / "root" / "bin.dat").write_bytes(b"\xff")
    (base / "root" / "sub" / "inner.txt").write_text("içerik", encoding="utf-8")
    (base / "root" / "link").symlink_to("a.txt")
    (base / "root" / "sublink").symlink_to("sub")
    (base / "rootlink").symlink_to("root")
    (base / "rootless").mkdir()
    (base / "rootless" / "a.txt").write_text("outside", encoding="utf-8")
    (base / "main.ks").write_text(PROGRAM, encoding="utf-8")
    return directory


def environment() -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("KS_TEST")}
    env["KS_TEST_VALUE"] = "değer"
    env_bytes = {os.fsencode(key): os.fsencode(value) for key, value in env.items()}
    env_bytes[b"KS_TEST_BINARY"] = b"\xff"
    env_bytes[b"PYTHONPATH"] = os.fsencode(str(ROOT))
    return env_bytes


class NativeBrokerTests(unittest.TestCase):
    def build(self, path: Path) -> Path:
        binary = path.parent / "app"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli_main(["build", str(path), "-o", str(binary)]), 0, errors.getvalue())
        return binary

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_the_binary_answers_like_ks_run(self) -> None:
        with workspace() as directory:
            base = Path(directory)
            env = environment()
            run = subprocess.run(
                [sys.executable, "-m", "koschei", "run", "main.ks"],
                cwd=base, env=env, capture_output=True, timeout=120, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            expected = run.stdout.decode("utf-8")
            lines = expected.split("\n")
            self.assertEqual(lines[0], "merhaba\r")
            self.assertIn("KS3405", expected)
            self.assertIn("Dosya okunamadı: ENOENT: root/missing", expected)
            self.assertIn("Ortam değişkeni geçerli UTF-8 metin değil: KS_TEST_BINARY", expected)
            binary = self.build(base / "main.ks")
            native = subprocess.run([str(binary)], cwd=base, env=env, capture_output=True, timeout=60, check=False)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(native.stdout.decode("utf-8"), expected)

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_the_worker_is_confined_and_starts_without_an_environment(self) -> None:
        source = (
            "fn main(caps: SystemCaps) {\n    let input = caps.input.allow(16)\n"
            '    let home = caps.env.allow("HOME")\n'
            '    let text = input.read_text() or ""\n    println("{text} {home.get() or "?"}")\n}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            binary = self.build(path)
            broker = subprocess.Popen(
                [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={"HOME": "/home/koschei", "SECRET_TOKEN": "do-not-leak"},
            )
            try:
                worker = None
                deadline = time.monotonic() + 20
                while worker is None and time.monotonic() < deadline:
                    children = Path(f"/proc/{broker.pid}/task/{broker.pid}/children")
                    pids = children.read_text().split() if children.exists() else []
                    worker = int(pids[0]) if pids else None
                    time.sleep(0.05)
                self.assertIsNotNone(worker, "worker process did not start")
                status = ""
                while time.monotonic() < deadline and "Seccomp:\t2" not in status:
                    status = Path(f"/proc/{worker}/status").read_text()
                    time.sleep(0.05)
                self.assertIn("Seccomp:\t2", status)
                self.assertIn("NoNewPrivs:\t1", status)
                self.assertEqual(Path(f"/proc/{worker}/environ").read_bytes(), b"KOSCHEI_NATIVE_WORKER=v1\x00")
                out, err = broker.communicate(b"hi", timeout=20)
            finally:
                if broker.poll() is None:
                    broker.kill()
            self.assertEqual(broker.returncode, 0, err)
            self.assertEqual(out.decode(), "hi /home/koschei\n")

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_the_filter_stops_file_socket_and_exec_calls(self) -> None:
        source = 'fn main(caps: SystemCaps) {\n    println(caps.env.allow("X").get() or "")\n}\n'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(source, encoding="utf-8")
            graph = load_graph(base / "main.ks")
            check_graph(graph)
            go_source = generate_go_mir_native(graph.mir)
            go_source = go_source.replace("func main() {", "func koscheiMain() {", 1)
            go_source += '''
func main() {
	_ksConfine()
	_, openErr := os.Open("/etc/hostname")
	_, socketErr := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	execErr := syscall.Exec("/bin/true", []string{"true"}, nil)
	_, forkErr := syscall.ForkExec("/bin/true", []string{"true"}, nil)
	fmt.Println(openErr != nil, socketErr == syscall.EPERM, execErr == syscall.EPERM, forkErr != nil)
	fmt.Println(syscall.Mkdir("/tmp/koschei-confined", 0o700) == syscall.EPERM)
	// An allow list: calls nobody listed are refused too, and the listed
	// ones with argument checks only reach this process.
	path := []byte("/etc/passwd\\x00")
	var info [256]byte
	_, _, statErr := syscall.RawSyscall6(262, ^uintptr(99), uintptr(unsafe.Pointer(&path[0])), uintptr(unsafe.Pointer(&info[0])), 0, 0, 0)
	_, _, ioctlErr := syscall.RawSyscall(syscall.SYS_IOCTL, 0, syscall.TIOCSTI, uintptr(unsafe.Pointer(&path[0])))
	_, _, forkRaw := syscall.RawSyscall(syscall.SYS_CLONE, uintptr(syscall.SIGCHLD), 0, 0)
	_, _, killOther := syscall.RawSyscall(syscall.SYS_KILL, uintptr(os.Getppid()), 0, 0)
	_, _, tgkillOther := syscall.RawSyscall(syscall.SYS_TGKILL, uintptr(os.Getppid()), uintptr(os.Getppid()), 0)
	_, _, prlimitOther := syscall.RawSyscall6(syscall.SYS_PRLIMIT64, uintptr(os.Getppid()), 7, 0, uintptr(unsafe.Pointer(&info[0])), 0, 0)
	_, _, ptraceErr := syscall.RawSyscall(syscall.SYS_PTRACE, 16, uintptr(os.Getppid()), 0)
	_, _, clone3Err := syscall.RawSyscall(435, 0, 0, 0)
	_, _, killSelf := syscall.RawSyscall(syscall.SYS_KILL, uintptr(os.Getpid()), 0, 0)
	_, _, prlimitSelf := syscall.RawSyscall6(syscall.SYS_PRLIMIT64, 0, 7, 0, uintptr(unsafe.Pointer(&info[0])), 0, 0)
	refused := []syscall.Errno{statErr, ioctlErr, forkRaw, killOther, tgkillOther, prlimitOther, ptraceErr}
	all := true
	for _, errno := range refused {
		all = all && errno == syscall.EPERM
	}
	fmt.Println(all, clone3Err == syscall.ENOSYS, killSelf == 0, prlimitSelf == 0)
	_ = koscheiMain
}
'''
            (base / "probe.go").write_text(go_source, encoding="utf-8")
            (base / "go.mod").write_text("module probe\n\ngo 1.21\n", encoding="utf-8")
            built = subprocess.run([GO, "build", "-o", "probe", "."], cwd=base, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            probe = subprocess.run([str(base / "probe")], capture_output=True, text=True, timeout=30)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout, "true true true true\ntrue\ntrue true true true\n")

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_writes_and_deletes_match_ks_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "main.ks").write_text(WRITES, encoding="utf-8")
            def fresh() -> None:
                shutil.rmtree(base / "root", ignore_errors=True)
                (base / "root" / "sub").mkdir(parents=True)
                (base / "root" / "dir").mkdir()
                (base / "root" / "keep.txt").write_text("old", encoding="utf-8")
                os.chmod(base / "root" / "keep.txt", 0o640)
                (base / "root" / "link").symlink_to("keep.txt")
                (base / "root" / "sublink").symlink_to("sub")
            def state() -> list:
                return sorted(
                    (str(path.relative_to(base)), path.is_symlink() or path.read_bytes() if path.is_file() else None,
                     oct(os.lstat(path).st_mode & 0o777))
                    for path in (base / "root").rglob("*")
                )
            fresh()
            run = subprocess.run(
                [sys.executable, "-m", "koschei", "run", "main.ks"], cwd=base,
                env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, timeout=120, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            expected, expected_state = run.stdout, state()
            self.assertIn(b"Dosya yaz\xc4\xb1lamad\xc4\xb1: EISDIR: root/dir", expected)
            binary = self.build(base / "main.ks")
            fresh()
            native = subprocess.run([str(binary)], cwd=base, capture_output=True, timeout=60, check=False)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(native.stdout, expected)
            self.assertEqual(state(), expected_state)
            self.assertFalse(any(".ks-write-" in name for name in os.listdir(base / "root")))

    @unittest.skipUnless(SUPPORTED and shutil.which("strace"), "needs strace on linux/amd64")
    def test_a_confined_worker_needs_no_refused_call(self) -> None:
        # The allow list must cover what the Go runtime does under load: a
        # traced worker that allocates, collects garbage, starts threads and
        # uses every brokered domain gets no EPERM or ENOSYS.
        source = """
fn churn(n: Int) -> Int {
    let mut items = [0]
    let mut i = 0
    while i < n {
        items = items.push(i)
        i = i + 1
    }
    let mut text = ""
    for item in items {
        text = "{text}{item}"
    }
    return text.length()
}

fn main(caps: SystemCaps) {
    let input = caps.input.allow(64)
    println(input.read_text())
    let disk = caps.disk.allow("root")
    println(disk.write("root/b.txt", "x"))
    println(disk.read("root/b.txt"))
    println(disk.list("root"))
    println(disk.delete("root/b.txt"))
    println(caps.env.allow("HOME").get())
    let random = caps.random.allow(8)
    let roll = random.below(6) or -1
    println(roll >= 0)
    println(churn(20000))
}
"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "root").mkdir()
            (base / "main.ks").write_text(source, encoding="utf-8")
            binary = self.build(base / "main.ks")
            trace = base / "trace.txt"
            run = subprocess.run(
                ["strace", "-f", "-qq", "-o", str(trace), str(binary)], cwd=base,
                input=b"in", capture_output=True, timeout=120, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            refused = _refused_after_confinement(trace.read_text())
            self.assertEqual(refused, [])

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_narrowing_in_a_loop_reuses_the_broker_scope(self) -> None:
        source = (
            "fn main(caps: SystemCaps) {\n    let mut i = 0\n    let mut ok = 0\n    while i < 150 {\n"
            '        let disk = caps.disk.allow_read_only("root")\n'
            '        let text = disk.read("root/a.txt") or ""\n'
            '        if text == "hi" {\n            ok = ok + 1\n        }\n        i = i + 1\n    }\n    println(ok)\n}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "root").mkdir()
            (base / "root" / "a.txt").write_text("hi", encoding="utf-8")
            (base / "main.ks").write_text(source, encoding="utf-8")
            binary = self.build(base / "main.ks")

            def few_descriptors() -> None:
                resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

            native = subprocess.run(
                [str(binary)], cwd=base, capture_output=True, timeout=60, check=False,
                preexec_fn=few_descriptors,
            )
            self.assertEqual((native.returncode, native.stdout), (0, b"150\n"), native.stderr)

    @unittest.skipUnless(SUPPORTED, "broker confinement is linux/amd64")
    def test_the_worker_dies_with_its_broker(self) -> None:
        source = (
            'fn main(caps: SystemCaps) {\n    println(caps.env.allow("HOME").get() or "?")\n'
            "    let mut i = 0\n    while i >= 0 {\n        i = (i + 1) % 1000\n    }\n}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.ks"
            path.write_text(source, encoding="utf-8")
            binary = self.build(path)
            broker = subprocess.Popen([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                broker.stdout.readline()
                worker = int(Path(f"/proc/{broker.pid}/task/{broker.pid}/children").read_text().split()[0])
                broker.kill()
                broker.wait(timeout=20)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and Path(f"/proc/{worker}").exists():
                    status = Path(f"/proc/{worker}/status").read_text() if Path(f"/proc/{worker}/status").exists() else ""
                    if "State:\tZ" in status:
                        break
                    time.sleep(0.05)
                status = Path(f"/proc/{worker}/status").read_text() if Path(f"/proc/{worker}").exists() else ""
                self.assertTrue(status == "" or "State:\tZ" in status, status[:200])
            finally:
                if broker.poll() is None:
                    broker.kill()

    def test_processes_stay_closed(self) -> None:
        cases = {
            "process": 'fn main(caps: SystemCaps) {\n    let p = caps.process.allow("echo")\n    println(p.run("hello") or "")\n}\n',
        }
        for name, source in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "main.ks"
                path.write_text(source, encoding="utf-8")
                graph = load_graph(path)
                check_graph(graph)
                support = inspect_mir_go_support(graph.mir)
                self.assertFalse(support.supported)
                self.assertTrue(any("(G2)" in reason for reason in support.reasons), support.reasons)


if __name__ == "__main__":
    unittest.main()

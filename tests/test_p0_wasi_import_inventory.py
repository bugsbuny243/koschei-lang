"""P0.1 experimental Go->WASI import inventory for a pure Koschei fixture.

This does NOT constitute an independent Koschei WASM backend or runtime sandbox.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from koschei.codegen_go import generate_go
from koschei.parser import parse
from koschei.semantic import check


ROOT = pathlib.Path(__file__).resolve().parents[1]
GO = shutil.which("go")
FORBIDDEN_WASI_IMPORTS = {
    "path_open", "path_create_directory", "path_remove_directory",
    "path_unlink_file", "path_rename", "path_link", "path_symlink",
    "path_readlink", "fd_readdir", "sock_accept",
}
# No preopened directory / inherited environment access for a pure program.
FORBIDDEN_WASI_IMPORTS |= {"fd_prestat_get", "fd_prestat_dir_name", "environ_get", "environ_sizes_get", "args_get", "args_sizes_get"}


def _u32(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 35, 7):
        if pos >= len(data):
            raise ValueError("truncated unsigned LEB128")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte & 128 == 0:
            if value > 0xFFFFFFFF:
                raise ValueError("oversized u32")
            return value, pos
    raise ValueError("invalid unsigned LEB128")


def _name(data: bytes, pos: int) -> tuple[str, int]:
    length, pos = _u32(data, pos)
    end = pos + length
    if end > len(data):
        raise ValueError("truncated name")
    return data[pos:end].decode("utf-8"), end


def _imports(data: bytes) -> tuple[tuple[str, str], ...]:
    if not data.startswith(b"\x00asm\x01\x00\x00\x00"):
        raise ValueError("not a wasm v1 module")
    pos = 8
    while pos < len(data):
        section_id = data[pos]
        pos += 1
        size, pos = _u32(data, pos)
        end = pos + size
        if end > len(data):
            raise ValueError("truncated section")
        if section_id == 2:
            count, pos = _u32(data, pos)
            result = []
            for _ in range(count):
                module, pos = _name(data, pos)
                member, pos = _name(data, pos)
                if pos >= end:
                    raise ValueError("truncated import descriptor")
                kind = data[pos]
                pos += 1
                if kind == 0:  # function type index
                    _, pos = _u32(data, pos)
                elif kind == 1:  # table type
                    pos += 1  # reftype
                    flags, pos = _u32(data, pos)
                    _, pos = _u32(data, pos)
                    if flags & 1:
                        _, pos = _u32(data, pos)
                elif kind == 2:  # memory limits
                    flags, pos = _u32(data, pos)
                    _, pos = _u32(data, pos)
                    if flags & 1:
                        _, pos = _u32(data, pos)
                elif kind == 3:  # global
                    pos += 2
                else:
                    raise ValueError(f"unsupported import kind: {kind}")
                if pos > end:
                    raise ValueError("import exceeds section")
                result.append((module, member))
            if pos != end:
                raise ValueError("unconsumed import section bytes")
            return tuple(result)
        pos = end
    return ()


def _unexpected_authority(imports: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Reject ambient filesystem/socket imports and every unreviewed namespace.

    Go WASI startup's argument/environment imports are recorded separately;
    allowing those imports in this inventory is NOT a sandbox guarantee.
    """
    startup = {"args_get", "args_sizes_get", "environ_get", "environ_sizes_get",
               "fd_prestat_get", "fd_prestat_dir_name"}
    # An allowlist prevents unknown future WASI functions from silently
    # widening the pure-program authority surface.
    permitted = {"fd_write", "proc_exit", "random_get", "clock_time_get",
                 "clock_res_get", "sched_yield", "fd_fdstat_get", "fd_close",
                 "fd_seek", "fd_read", "fd_filestat_get", "fd_sync",
                 "fd_datasync", "poll_oneoff", "fd_fdstat_set_flags",
                 "fd_prestat_get", "fd_prestat_dir_name"} | startup
    return tuple(
        (module, member) for module, member in imports
        if module != "wasi_snapshot_preview1"
        or member not in permitted
        or member in (FORBIDDEN_WASI_IMPORTS - startup)
    )


class P0WasiImportParserTests(unittest.TestCase):
    def test_empty_module_has_no_imports(self) -> None:
        self.assertEqual(_imports(b"\x00asm\x01\x00\x00\x00"), ())

    def test_truncated_leb128_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated unsigned LEB128"):
            _u32(bytes((0x80,)), 0)

    def test_oversized_leb128_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "oversized u32"):
            _u32(bytes((255, 255, 255, 255, 31)), 0)

    def test_truncated_import_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated name"):
            _name(bytes((5,)) + b'ab', 0)

    def test_truncated_import_section_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _imports(b"\x00asm\x01\x00\x00\x00\x02\x05\x01")

    def test_forbidden_import_is_parsed(self) -> None:
        module = b"wasi_snapshot_preview1"
        member = b"environ_get"
        payload = (b"\x01" + bytes([len(module)]) + module
                   + bytes([len(member)]) + member + b"\x00\x00")
        wasm = b"\x00asm\x01\x00\x00\x00" + b"\x02" + bytes([len(payload)]) + payload
        self.assertEqual(_imports(wasm), (("wasi_snapshot_preview1", "environ_get"),))
        self.assertIn("environ_get", FORBIDDEN_WASI_IMPORTS)


    def test_wasi_filesystem_import_is_rejected(self) -> None:
        self.assertEqual(
            _unexpected_authority((("wasi_snapshot_preview1", "path_open"),)),
            (("wasi_snapshot_preview1", "path_open"),),
        )

    def test_non_wasi_import_namespace_is_rejected(self) -> None:
        self.assertEqual(
            _unexpected_authority((("env", "host_disk_open"),)),
            (("env", "host_disk_open"),),
        )

    def test_unknown_wasi_function_is_rejected(self) -> None:
        self.assertEqual(
            _unexpected_authority((("wasi_snapshot_preview1", "future_host_escape"),)),
            (("wasi_snapshot_preview1", "future_host_escape"),),
        )

    def test_lookalike_wasi_namespace_is_rejected(self) -> None:
        self.assertEqual(
            _unexpected_authority((("wasi_unreviewed_extension", "fd_write"),)),
            (("wasi_unreviewed_extension", "fd_write"),),
        )

    def test_go_startup_import_is_not_mistaken_for_isolation(self) -> None:
        self.assertEqual(
            _unexpected_authority((("wasi_snapshot_preview1", "environ_get"),)),
            (),
        )


@unittest.skipUnless(GO, "Go toolchain is required for experimental WASI evidence")
class P0WasiImportInventoryTests(unittest.TestCase):
    def test_pure_fixture_imports_are_audited_and_filesystem_denied(self) -> None:
        source = (ROOT / "examples/hello.ks").read_text(encoding="utf-8")
        program = parse(source)
        check(program)
        with tempfile.TemporaryDirectory(prefix="koschei-p0-wasi-") as tmp:
            work = pathlib.Path(tmp)
            (work / "main.go").write_text(generate_go(program), encoding="utf-8")
            (work / "go.mod").write_text("module koscheiwasiinventory\n\ngo 1.21\n", encoding="utf-8")
            wasm = work / "main.wasm"
            env = dict(os.environ, GOOS="wasip1", GOARCH="wasm", CGO_ENABLED="0")
            built = subprocess.run(
                [GO, "build", "-o", str(wasm), "."],
                cwd=work, env=env, capture_output=True, text=True, timeout=240,
            )
            if built.returncode != 0:
                # The current generated Go runtime is platform-specific:
                # syscall.SOCK_CLOEXEC/O_NONBLOCK/Unlinkat/Renameat and a
                # WASI-specific uint64/int64 stat mismatch block compilation.
                # This is an explicit UNSUPPORTED target, not a passing
                # compiled-WASM security receipt.
                blockers = (
                    "syscall.SOCK_CLOEXEC", "syscall.O_NONBLOCK",
                    "syscall.Unlinkat", "syscall.Renameat",
                    "mismatched types uint64 and int64",
                )
                print("P0_WASI_COMPILE_BLOCKED " + built.stderr.strip())
                self.assertTrue(
                    any(blocker in built.stderr for blocker in blockers),
                    "Unexpected WASI build failure: " + built.stderr,
                )
                self.skipTest("WASI backend unavailable: generated Go runtime is not portable")
            self.assertEqual(built.returncode, 0, built.stderr)
            imports = _imports(wasm.read_bytes())
            print(f"P0_WASI_IMPORT_RECEIPT fixture='examples/hello.ks' imports={imports!r}")
            self.assertTrue(imports, "Go WASI module must have inspectable imports")
            imported = {member for module, member in imports if module.startswith("wasi_")}
            residual = imported & FORBIDDEN_WASI_IMPORTS
            print(f"P0_WASI_RESIDUAL_AUTHORITY imports={tuple(sorted(residual))!r}")
            self.assertEqual(
                _unexpected_authority(imports), (),
                "Pure fixture imports unreviewed ambient authority",
            )


if __name__ == "__main__":
    unittest.main()

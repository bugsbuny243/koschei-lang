"""Experimental host-measured WASI execution, not a production sandbox.

No directory preopens, no guest environment variables, no network configuration.
Fuel is a deterministic instruction budget, NOT a wall-clock deadline.
"""
from dataclasses import dataclass
from pathlib import Path
from time import monotonic_ns

from koschei.runner_billing import RunUsage


@dataclass(frozen=True)
class ExecutionReceipt:
    usage: RunUsage
    stdout: str
    stderr: str


def execute_pure_wasi(
    wasm_path: str, tenant_id: str, run_id: str, *,
    max_duration_ms: int, fuel: int = 50_000_000,
    memory_bytes: int = 64 * 1024 * 1024,
    stdout_path: str, stderr_path: str,
) -> ExecutionReceipt:
    """Execute trusted pure-WASI artifact with host-side elapsed measurement.

    Caller owns output paths; a production runner must isolate output files and
    enforce a hard wall-clock timeout externally before enabling billing.
    """
    if not tenant_id or not run_id or type(max_duration_ms) is not int or max_duration_ms <= 0:
        raise ValueError("invalid run identity or maximum duration")
    if type(fuel) is not int or fuel <= 0 or type(memory_bytes) is not int or memory_bytes <= 0:
        raise ValueError("invalid resource limits")
    if Path(stdout_path).resolve() == Path(stderr_path).resolve():
        raise ValueError("output paths must differ")

    import wasmtime

    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    module = wasmtime.Module.from_file(engine, wasm_path)
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    store = wasmtime.Store(engine)
    store.set_fuel(fuel)
    store.set_limits(memory_size=memory_bytes)
    wasi = wasmtime.WasiConfig()
    wasi.argv = ["guest.wasm"]
    wasi.stdout_file = stdout_path
    wasi.stderr_file = stderr_path
    store.set_wasi(wasi)

    # No preopened directories, guest env or socket configuration.
    started_ns = monotonic_ns()
    outcome = "succeeded"
    try:
        instance = linker.instantiate(store, module)
        instance.exports(store)["_start"](store)
    except wasmtime.ExitTrap as exc:
        if exc.code != 0:
            outcome = "guest_failed"
    except wasmtime.Trap:
        outcome = "guest_failed"
    except Exception:
        outcome = "host_failed"
        raise
    finally:
        elapsed_ms = (monotonic_ns() - started_ns + 999_999) // 1_000_000
    if elapsed_ms > max_duration_ms:
        outcome = "guest_timeout"
    usage = RunUsage(run_id, tenant_id, elapsed_ms, outcome)
    return ExecutionReceipt(
        usage,
        Path(stdout_path).read_text(encoding="utf-8") if Path(stdout_path).exists() else "",
        Path(stderr_path).read_text(encoding="utf-8") if Path(stderr_path).exists() else "",
    )

"""Route executable/compiler commands through one trusted Object Space session.

Object Space has no semantic entry filename and accepts no raw crypto/temporal
secrets on the CLI. A trusted embedding installs one scoped opener through
``object_space_session``; run, mir, caps, emit-go and build then consume exactly
the authenticated graph returned by that opener.

Legacy file projects keep their existing command paths. A directory that looks
like Object Space never silently falls back to the legacy resolver.

Object Space native build has an additional confidentiality rule: generated Go
source may not be staged in a normal disk-backed temporary directory. The current
Linux implementation requires an admitted tmpfs scratch root (``/dev/shm``) and
fails closed if it cannot prove that property.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from . import cli as _cli
from . import object_space_check_v1 as _check
from .capabilities import analyze_graph, render as render_manifest
from .capabilities import to_dict as manifest_to_dict
from .codegen_go import generate_go_mir
from .interpreter import run_mir as interpret_mir
from .mir import require_mir, to_dict as mir_to_dict
from .object_space_check_v1 import (
    _open_scoped_project,
    object_space_check_session,
)
from .object_space_graph_v1 import check_object_space_graph
from .object_space_v1 import ObjectSpaceProject


class ObjectSpaceCommandError(ValueError):
    pass


# The old public name remains valid for compatibility, but the same scoped broker
# now authorizes all compiler commands in this slice.
object_space_session = object_space_check_session

_INSTALLED = False
_ORIGINAL_COMMAND_RUN = None
_ORIGINAL_COMMAND_MIR = None
_ORIGINAL_COMMAND_CAPS = None
_ORIGINAL_COMMAND_EMIT_GO = None
_ORIGINAL_COMMAND_BUILD = None


def _looks_like_object_space(path: str | Path) -> bool:
    # Resolve the routing guard dynamically. The adversarial guard intentionally
    # replaces this predicate during package installation; caching an older
    # function object would make installer order part of the security boundary.
    return _check._looks_like_object_space(path)


def _checked(path: str) -> tuple[ObjectSpaceProject, object]:
    project = _open_scoped_project(path)
    graph, _ = check_object_space_graph(project)
    return project, graph


def _stable_identity_needles(project: ObjectSpaceProject) -> tuple[str, ...]:
    values = [project.project_id.hex()]
    values.extend(record.object_id.hex() for record in project.records)
    values.extend(record.locator_text for record in project.records)
    return tuple(values)


def _reject_identity_leak(text: str, project: ObjectSpaceProject, *, surface: str) -> None:
    for value in _stable_identity_needles(project):
        if value and value in text:
            raise ObjectSpaceCommandError(
                f"Object Space {surface} would expose stable storage/object identity; "
                "the command failed closed"
            )


def _public_mir_payload(graph: object, project: ObjectSpaceProject) -> dict:
    payload = mir_to_dict(require_mir(graph))
    modules = payload.get("modules", [])
    alias_by_name: dict[str, str] = {}
    for index, module in enumerate(modules, start=1):
        name = module.get("name")
        if isinstance(name, str):
            alias = f"<object-{index}>"
            alias_by_name[name] = alias
            module["name"] = alias
    root = payload.get("root")
    if isinstance(root, str) and root in alias_by_name:
        payload["root"] = alias_by_name[root]
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    _reject_identity_leak(encoded, project, surface="MIR view")
    return payload


def _sanitize_manifest_holder_names(manifest: object, graph: object) -> None:
    holders = getattr(manifest, "holder_functions", None)
    if not isinstance(holders, dict) or not holders:
        return
    aliases = {
        module.name: f"<object-{index}>"
        for index, module in enumerate(graph.in_dependency_order(), start=1)
    }
    sanitized: dict[str, list[str]] = {}
    for label, parameters in holders.items():
        replacement = label
        for name, alias in aliases.items():
            prefix = name + "."
            if label.startswith(prefix):
                replacement = alias + label[len(name):]
                break
        sanitized[replacement] = parameters
    manifest.holder_functions = sanitized


def _object_space_command_run(path: str) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_RUN is not None
        return _ORIGINAL_COMMAND_RUN(path)
    _, graph = _checked(path)
    return interpret_mir(require_mir(graph), [])


def _object_space_command_mir(path: str) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_MIR is not None
        return _ORIGINAL_COMMAND_MIR(path)
    project, graph = _checked(path)
    print(json.dumps(_public_mir_payload(graph, project), ensure_ascii=False, indent=2))
    return 0


def _object_space_command_caps(
    path: str,
    as_json: bool,
    denied: list[str] | None,
) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_CAPS is not None
        return _ORIGINAL_COMMAND_CAPS(path, as_json, denied)

    project, graph = _checked(path)
    manifest = analyze_graph(graph)
    _sanitize_manifest_holder_names(manifest, graph)
    source_name = "<object-space>"
    if as_json:
        text = json.dumps(
            manifest_to_dict(manifest, source_name),
            ensure_ascii=False,
            indent=2,
        )
        _reject_identity_leak(text, project, surface="capability manifest")
        print(text)
    else:
        text = render_manifest(manifest, source_name)
        _reject_identity_leak(text, project, surface="capability manifest")
        print(text, end="")

    if not denied:
        return 0
    violations = sorted(set(manifest.domains()) & set(denied))
    if violations:
        print(
            "KOSCHEI POLICY: denied capability domain requested: "
            + ", ".join(violations),
            file=sys.stderr,
        )
        return 2
    return 0


def _object_space_go_source(path: str) -> tuple[ObjectSpaceProject, str]:
    project, graph = _checked(path)
    source = generate_go_mir(require_mir(graph))
    _reject_identity_leak(source, project, surface="native backend source")
    return project, source


def _object_space_command_emit_go(path: str) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_EMIT_GO is not None
        return _ORIGINAL_COMMAND_EMIT_GO(path)
    _, source = _object_space_go_source(path)
    print(source, end="")
    return 0


def _relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _target_inside_project(target: Path, project: ObjectSpaceProject) -> bool:
    # Check both lexical and symlink-resolved location. A path such as
    # <project>/artifact -> /outside must still be rejected: merely opening a
    # semantic output name inside k0/k1 reality violates the canonical surface
    # even if the symlink ultimately points elsewhere.
    lexical_root = Path(os.path.abspath(os.fspath(project.root)))
    lexical_target = Path(os.path.abspath(os.fspath(target)))
    if _relative_to(lexical_target, lexical_root):
        return True

    resolved_root = project.root.resolve()
    resolved_target = target.resolve()
    return _relative_to(resolved_target, resolved_root)


def _unescape_mount_field(value: str) -> str:
    # Linux mountinfo escapes space/tab/newline/backslash as octal sequences.
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _memory_backed_workspace_root() -> Path | None:
    """Return a proven tmpfs scratch root or None.

    v1 deliberately recognizes only Linux /dev/shm mounted as tmpfs. This is a
    narrow proof surface, not a heuristic such as trusting TMPDIR.
    """

    candidate = Path("/dev/shm")
    try:
        info = candidate.lstat()
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return None

    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if separator < 6 or separator + 1 >= len(fields):
            continue
        mount_point = _unescape_mount_field(fields[4])
        fs_type = fields[separator + 1]
        if mount_point == "/dev/shm" and fs_type == "tmpfs":
            return candidate
    return None


def _object_space_command_build(path: str, output: str | None, locale: str) -> int:
    if not _looks_like_object_space(path):
        assert _ORIGINAL_COMMAND_BUILD is not None
        return _ORIGINAL_COMMAND_BUILD(path, output, locale)

    project, go_source = _object_space_go_source(path)
    if not output:
        raise ObjectSpaceCommandError(
            "Object Space build requires an explicit -o/--output because the "
            "project has no semantic entry filename from which to derive a binary name"
        )

    requested_target = Path(output)
    if _target_inside_project(requested_target, project):
        raise ObjectSpaceCommandError(
            "Object Space build output cannot be written inside the canonical k0/k1 project root"
        )
    target = requested_target.resolve()

    go_binary = shutil.which("go")
    if go_binary is None:
        message = (
            "KOSCHEI ERROR: 'go' was not found. Install Go for native builds "
            "or use 'ks run'."
            if locale == "en"
            else "KOSCHEI ERROR: 'go' bulunamadı. Native derleme için Go kurun "
            "veya 'ks run' kullanın."
        )
        print(message, file=sys.stderr)
        return 1

    scratch_root = _memory_backed_workspace_root()
    if scratch_root is None:
        raise ObjectSpaceCommandError(
            "Object Space native build requires a proven memory-backed tmpfs scratch "
            "workspace; generated backend source will not be written to disk-backed temp storage"
        )

    with tempfile.TemporaryDirectory(
        prefix="koschei-native-",
        dir=scratch_root,
    ) as workspace:
        directory = Path(workspace)
        os.chmod(directory, 0o700)
        source_file = directory / "main.go"
        module_file = directory / "go.mod"
        source_file.write_text(go_source, encoding="utf-8")
        module_file.write_text(
            "module koscheiprogram\n\ngo 1.21\n",
            encoding="utf-8",
        )
        os.chmod(source_file, 0o600)
        os.chmod(module_file, 0o600)
        completed = subprocess.run(
            [go_binary, "build", "-o", str(target), "."],
            cwd=directory,
            capture_output=True,
            text=True,
        )

    if completed.returncode != 0:
        message = (
            "KOSCHEI ERROR: Go compilation failed. This is a compiler bug; "
            "report it with the Object Space compiler diagnostics.\n"
            if locale == "en"
            else "KOSCHEI ERROR: Go derlemesi başarısız oldu. Bu bir derleyici "
            "hatasıdır; Object Space derleyici tanılarıyla birlikte bildirin.\n"
        )
        print(message + completed.stderr.strip(), file=sys.stderr)
        return 1

    print(f"KOSCHEI BUILD: {target}")
    return 0


def install_object_space_commands_v1() -> None:
    global _INSTALLED
    global _ORIGINAL_COMMAND_RUN, _ORIGINAL_COMMAND_MIR, _ORIGINAL_COMMAND_CAPS
    global _ORIGINAL_COMMAND_EMIT_GO, _ORIGINAL_COMMAND_BUILD
    if _INSTALLED:
        return
    _ORIGINAL_COMMAND_RUN = _cli.command_run
    _ORIGINAL_COMMAND_MIR = _cli.command_mir
    _ORIGINAL_COMMAND_CAPS = _cli.command_caps
    _ORIGINAL_COMMAND_EMIT_GO = _cli.command_emit_go
    _ORIGINAL_COMMAND_BUILD = _cli.command_build
    _cli.command_run = _object_space_command_run
    _cli.command_mir = _object_space_command_mir
    _cli.command_caps = _object_space_command_caps
    _cli.command_emit_go = _object_space_command_emit_go
    _cli.command_build = _object_space_command_build
    _INSTALLED = True

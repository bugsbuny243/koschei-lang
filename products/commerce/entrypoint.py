"""Prepare an attached /data volume, then permanently drop root privileges.

Railway binds volumes at runtime with root ownership, overwriting the
Dockerfile's /data directory ownership. Only this one-time mount preparation
needs root. The HTTP server and the Koschei subprocess run as 'commerce'.
Fail closed unless /data is a real mounted filesystem.
"""
from __future__ import annotations

import os
import pwd
import stat
import sys
from pathlib import Path

DATA = Path("/data")
EXPECTED_DB_FILES = ("commerce.db", "commerce.db-wal", "commerce.db-shm")


def is_volume_mount() -> bool:
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split(" ")
            if len(fields) >= 6 and fields[4] == str(DATA):
                return True
    except OSError:
        return False
    return False


def prepare_volume() -> None:
    if not DATA.is_dir() or DATA.is_symlink() or not is_volume_mount():
        raise RuntimeError("Commerce requires a real persistent volume mounted at /data")

    account = pwd.getpwnam("commerce")
    uid, gid = account.pw_uid, account.pw_gid

    os.chown(DATA, uid, gid)
    for name in EXPECTED_DB_FILES:
        path = DATA / name
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("Unexpected non-regular SQLite file in mounted volume")
        os.chown(path, uid, gid, follow_symlinks=False)
    # The service itself never runs with the privileges used for mount setup.
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    if os.geteuid() != uid or os.getegid() != gid:
        raise RuntimeError("Failed to drop commerce service privileges")


def main() -> None:
    prepare_volume()
    os.execv(sys.executable, [sys.executable, "/opt/commerce/server.py"])


if __name__ == "__main__":
    main()

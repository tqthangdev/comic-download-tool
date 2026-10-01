"""
updater/update.py

The standalone updater. It waits for the running app to exit, backs the
installation up, swaps in the prepared version, verifies it, launches it again
and cleans up — restoring the previous installation if anything goes wrong.

The app starts it as a separate process:

    <app> --update --source <dir> --target <dir> --pid <pid> --version <version>

This module only uses the standard library on purpose: it must not import code
from the installation it is about to replace (the new version may have a
different layout), and it must not hold open files inside it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

WAIT_TIMEOUT_SECONDS = 120
POLL_SECONDS = 0.5
STAGING_SUFFIX = ".update-staging-"
BACKUP_SUFFIX = ".backup-"
ENTRY_POINTS = ("ComicDownloadTool.exe", "ComicDownloadTool", "run.py")
VERSION_FILE = "version.json"

_log_file = None


def log(message: str) -> None:
    """Append to the updater log next to the installation (never inside it)."""
    global _log_file
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        if _log_file is None:
            return
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Process helpers
# --------------------------------------------------------------------------- #

def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes

        STILL_ACTIVE = 259
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_for_exit(pid: int, timeout: float = WAIT_TIMEOUT_SECONDS) -> bool:
    """Block until the old app is gone (True) or the timeout runs out (False)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            return True
        time.sleep(POLL_SECONDS)
    return False


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #

def _move(src: Path, dst: Path) -> None:
    """Move a folder, falling back to a copy when it crosses filesystems."""
    try:
        os.replace(src, dst)
    except OSError:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)


def has_entry_point(root: Path) -> bool:
    """True when `root` holds something launchable.

    Must be a file: release zips carry a top-level folder named after the
    executable, which is not an install by itself.
    """
    return any((root / name).is_file() for name in ENTRY_POINTS)


def _package_version(root: Path) -> str:
    import json

    try:
        data = json.loads((root / VERSION_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return ""
    return str(data.get("version") or "").strip().lstrip("vV")


def looks_installed(root: Path, version: str) -> bool:
    """True when `root` is a runnable install of `version`."""
    if not root.is_dir() or not has_entry_point(root):
        return False
    want = (version or "").strip().lstrip("vV")
    if not want:
        return True
    return _package_version(root) == want


def launch(target: Path) -> bool:
    """Start the freshly installed app."""
    kwargs = {"cwd": str(target)}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    for name in ("ComicDownloadTool.exe", "ComicDownloadTool"):
        exe = target / name
        if exe.is_file():
            subprocess.Popen([str(exe)], **kwargs)
            return True

    entry = target / "run.py"
    if entry.is_file():
        subprocess.Popen([sys.executable, str(entry)], **kwargs)
        return True

    return False


# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #

def install(source: Path, target: Path, version: str) -> bool:
    """Replace `target` with `source`; restores the backup on any failure."""
    parent = target.parent
    staging = parent / f"{target.name}{STAGING_SUFFIX}{version}"
    backup = parent / f"{target.name}{BACKUP_SUFFIX}{version}"

    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)

    # The prepared package usually lives inside the installation being replaced,
    # so move it next to the target first — then the swap is a pair of renames.
    _move(source, staging)

    try:
        os.replace(target, backup)
    except OSError as e:
        log(f"cannot move the installation aside: {e}")
        shutil.rmtree(staging, ignore_errors=True)
        return False

    _move(staging, target)

    if not looks_installed(target, version):
        log("installed package does not look valid — rolling back")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(backup, target)
        launch(target)
        return False

    if not launch(target):
        log("could not launch the new version — rolling back")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(backup, target)
        launch(target)
        return False

    # Cleanup failures are not update failures (spec §15).
    shutil.rmtree(backup, ignore_errors=True)
    return True


def main(argv: Optional[list] = None) -> int:
    global _log_file

    parser = argparse.ArgumentParser(description="Comic Download Tool updater")
    parser.add_argument("--source", required=True, help="prepared app folder")
    parser.add_argument("--target", required=True, help="installation to replace")
    parser.add_argument("--pid", type=int, default=0, help="pid of the running app")
    parser.add_argument("--version", default="", help="version being installed")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    target = Path(args.target).resolve()
    _log_file = str(target.parent / f"{target.name}-update.log")

    log(f"updater started: source={source} target={target} pid={args.pid} version={args.version}")

    if not wait_for_exit(args.pid):
        log("the running app did not exit in time — aborting")
        return 1

    if not looks_installed(source, args.version):
        log("prepared package is not a valid install — aborting")
        return 1

    ok = install(source, target, args.version)
    log("update finished" if ok else "update failed (previous version restored)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

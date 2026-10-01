"""
core/updater/installer.py

Prepares an update — download, verify, extract, validate — and then hands the
actual replacement to the standalone updater process. The running app never
overwrites itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional

from core.logger import logger
from core.utils import BASE_DIR
from core.updater.checker import UpdateInfo
from core.updater.downloader import download_asset
from core.updater.verifier import validate_package, verify_download

# Staging area, inside the app folder as the spec describes. The updater moves
# it out of the way before replacing the app.
UPDATE_DIR_NAME = ".update"


class InstallError(Exception):
    """The update could not be prepared."""


def staging_dir(version: str) -> Path:
    return BASE_DIR / UPDATE_DIR_NAME / version.strip().lstrip("vV")


def _cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def prepare_update(
    info: UpdateInfo,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Download, verify, extract and validate the release package.

    Returns the folder holding the new application (the updater's --source).
    Any failure leaves the current installation untouched and removes the
    partial download.
    """
    asset = info.asset_for_platform()
    if asset is None:
        raise InstallError("no package for this platform")

    stage = staging_dir(info.latest)
    stage.mkdir(parents=True, exist_ok=True)

    zip_path = stage / asset.name
    download_asset(asset.url, zip_path, progress=progress)

    if not verify_download(zip_path, asset):
        _cleanup(stage)
        raise InstallError("checksum mismatch")

    extracted = stage / "extracted"
    _cleanup(extracted)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            broken = archive.testzip()
            if broken:
                raise InstallError(f"corrupt archive ({broken})")
            archive.extractall(extracted)
    except zipfile.BadZipFile as e:
        _cleanup(stage)
        raise InstallError("invalid zip archive") from e
    except InstallError:
        _cleanup(stage)
        raise
    except OSError as e:
        _cleanup(stage)
        raise InstallError(str(e)) from e

    app_root = validate_package(extracted, info.latest)
    if app_root is None:
        _cleanup(stage)
        raise InstallError("invalid update package")

    logger.info(f"[updater] staged {info.latest} at {app_root}")
    return app_root


def spawn_updater(source: Path, version: str) -> None:
    """Start the updater process that replaces this installation.

    The app exits right after this; the updater waits for that, so the swap
    never happens while the old build is still running.
    """
    launcher = [sys.executable]
    if not getattr(sys, "frozen", False):
        # Running from source: hand the entry script to the interpreter.
        launcher.append(str(Path(sys.argv[0]).resolve()))

    args = launcher + [
        "--update",
        "--source", str(source),
        "--target", str(BASE_DIR),
        "--pid", str(os.getpid()),
        "--version", version,
    ]

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(args, **kwargs)
    logger.info(f"[updater] started updater process for {version}")

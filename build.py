#!/usr/bin/env python3
"""Build a standalone ComicDownloadTool executable with PyInstaller.

Works on both Windows and Linux. Everything the build needs — the venv, the
dependencies declared in ``pyproject.toml``, Playwright Chromium, and
PyInstaller — is installed inside the project folder, so the script never
touches the system Python.

    python build.py                  # any interpreter; switches to .venv
    .venv/bin/python build.py        # build with the project venv
    python build.py --skip-browsers  # reuse the Chromium already downloaded
    python build.py --name MyApp     # custom executable name

The output is a onedir bundle in ``dist/<name>/`` — the executable plus
``_internal/`` (assets, version.json, Playwright driver and Chromium). That
whole folder is the distributable unit.

A ``run.spec`` is generated on the fly because the bundled Chromium lives in a
different cache per OS and Linux must not bundle the host's GUI libraries.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_NAME = "ComicDownloadTool"

# Linux: Qt/GTK/Wayland/X11 libraries must come from the target system. A copy
# built on another distribution fails at startup, so PyInstaller is told to skip
# them and the ones that slip into the bundle are deleted afterwards.
_SYSTEM_LIB_GLOBS = (
    "libxkbcommon.so.*",
    "libwayland-client.so.*",
    "libwayland-cursor.so.*",
    "libwayland-egl.so.*",
    "libX11.so.*",
    "libX11-xcb.so.*",
    "libxcb*.so.*",
)

# Passed to PyInstaller as `excludes` on Linux (module names, kept in step with
# the file globs above).
_SPEC_EXCLUDES = (
    "libxkbcommon",
    "libwayland-client",
    "libwayland-cursor",
    "libwayland-egl",
    "libX11",
    "libX11-xcb",
    "libxcb",
)

# Modules the app never uses, but that something in the dependency tree drags
# in. Excluding them stops their data files (Tcl/Tk, pikepdf's native libs)
# from being collected at all.
_DEAD_MODULE_EXCLUDES = (
    "tkinter",
    "_tkinter",
    "pikepdf",
)

# Leftovers deleted from _internal after the build, in case a module slipped
# past the excludes (globs, relative to _internal).
_TRIM_GLOBS = (
    "_tcl_data",
    "_tk_data",
    "libtcl*.so*",
    "libtk*.so*",
    "python3*/lib-dynload/_tkinter*",
    "pikepdf",
    "pikepdf.libs",
)

# Chromium ships a lot the scraper never needs: keep the English locales only
# and drop the Widevine DRM module.
_CHROMIUM_KEEP_LOCALES = ("en-US.pak", "en-GB.pak")

# The GUI stylesheets reference these indicator icons by absolute path, so they
# must be present inside the bundle or the checkboxes/radio buttons would
# silently render without their custom icons.
_INDICATOR_ASSETS = (
    "controls/checkbox-checked.svg",
    "controls/checkbox-unchecked.svg",
    "controls/radio-checked.svg",
    "controls/radio-unchecked.svg",
)

_SPEC_TEMPLATE = """\
from pathlib import Path
import playwright

block_cipher = None

BASE_DIR = Path(SPECPATH)

PLAYWRIGHT_DRIVER_PATH = (
    Path(playwright.__file__).parent / "driver"
)

datas = [
    (str(BASE_DIR / "assets"), "assets"),
    (str(BASE_DIR / "version.json"), "."),
    (str(PLAYWRIGHT_DRIVER_PATH), "playwright/driver"),
]

# Optional second engine: gallery-dl (GPL-2.0). Collected only when it is
# installed, so a native-only venv still builds. The app runs it out of process
# via `--gallery-dl-worker` (see run.py); its extractors are imported lazily, so
# they must be collected explicitly.
try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    GALLERYDL_HIDDEN = collect_submodules("gallery_dl")
    datas += collect_data_files("gallery_dl")
except Exception:
    GALLERYDL_HIDDEN = []

# ==========================================
# PLAYWRIGHT CHROMIUM
# ==========================================

browser_path = Path(@BROWSERS_PATH@)

for browser_dir in browser_path.glob("chromium-*"):
    if browser_dir.is_dir():
        datas.append(
            (
                str(browser_dir),
                "ms-playwright/" + browser_dir.name,
            )
        )

# ==========================================
# ANALYSIS
# ==========================================

a = Analysis(
    [str(BASE_DIR / "run.py")],

    pathex=[
        str(BASE_DIR),
    ],

    binaries=[],

    datas=datas,

    hiddenimports=[
        "playwright.async_api",
        "playwright.__main__",
        "qasync",
        "aiohttp",
        "bs4",
        "lxml",
    ] + GALLERYDL_HIDDEN,

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=@EXCLUDES@,

    win_no_prefer_redirects=False,
    win_private_assemblies=False,

    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,

    exclude_binaries=True,

    name=@NAME@,

    debug=False,
    bootloader_ignore_signals=False,

    strip=False,
    upx=True,

    console=False,

    icon=@ICON@,

    disable_windowed_traceback=False,
    argv_emulation=False,

    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,

    strip=False,
    upx=True,

    name=@NAME@,
)
"""


def venv_python() -> Path:
    """Path to the project venv's interpreter for the current OS."""
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def running_in_project_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except OSError:
        return False


def ensure_venv(no_venv: bool) -> None:
    """Create/enter the project venv, re-executing this script inside it.

    Keeps every dependency inside the project folder. When a venv cannot be
    created the build continues with the current interpreter.
    """
    if no_venv:
        return

    python = venv_python()

    if python.exists():
        if running_in_project_venv():
            return
        print(f"Switching to project virtualenv: {python}\n")
        raise SystemExit(_reexec(python))

    print("Creating virtual environment (.venv) ...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    except subprocess.CalledProcessError:
        print(
            "Could not create a virtual environment; continuing with the "
            "current interpreter.\n",
            file=sys.stderr,
        )
        return

    if python.exists():
        raise SystemExit(_reexec(python))


def _reexec(python: Path) -> int:
    return subprocess.call(
        [str(python), str(Path(__file__).resolve()), *sys.argv[1:]]
    )


def run(command: list[str]) -> int:
    print("Running:", " ".join(command))
    return subprocess.call(command, cwd=str(ROOT))


def install_dependencies() -> None:
    """Install runtime + build dependencies declared in pyproject.toml.

    `gallerydl` is included so the optional second engine is bundled. Remove it
    from this list to produce a native-only build (and drop the GPL-2.0 code).
    """
    print("\n=== Installing dependencies (pyproject.toml) ===")
    code = run([sys.executable, "-m", "pip", "install", "-e", ".[build,gallerydl]"])
    if code != 0:
        raise SystemExit("Dependency installation failed.")


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    print("\nPyInstaller not found — installing it ...")
    code = run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    if code != 0:
        raise SystemExit("Could not install PyInstaller.")


def patch_nodriver() -> None:
    """Fix nodriver's UTF-8 bug (its cdp modules ship latin-1 bytes).

    PyInstaller parses those modules during dependency analysis and raises
    "SyntaxError: Non-UTF-8 code starting with '\\xb1'". We cannot import
    nodriver to locate it (that import is the failure), so resolve the venv's
    site-packages via sysconfig. Safe to run repeatedly.
    """
    fix_script = ROOT / "tools" / "fix_nodriver.py"
    if not fix_script.exists():
        print(f"\nWarning: {fix_script} not found, skipping nodriver patch.")
        return

    import sysconfig

    nodriver_dir = Path(sysconfig.get_paths()["purelib"]) / "nodriver"
    print("\n=== Patching nodriver UTF-8 encoding ===")
    run([sys.executable, str(fix_script), str(nodriver_dir)])


def install_browsers() -> None:
    print("\n=== Installing Playwright Chromium ===")
    code = run([sys.executable, "-m", "playwright", "install", "chromium"])
    if code != 0:
        raise SystemExit("Playwright Chromium installation failed.")


def verify_project() -> None:
    print("\n=== Verify project ===")
    required = [ROOT / "run.py", ROOT / "version.json"]
    icon = ROOT / "assets" / "app" / ("icon.ico" if os.name == "nt" else "icon.png")
    required.append(icon)
    for path in required:
        if not path.exists():
            raise SystemExit(f"Missing required file: {path.relative_to(ROOT)}")


def clean() -> None:
    print("\n=== Cleaning previous build ===")
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    (ROOT / "run.spec").unlink(missing_ok=True)


def browser_cache_dir() -> Path:
    """Default Playwright browser cache for the current OS."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def write_spec(name: str) -> Path:
    print("\n=== Creating PyInstaller spec ===")
    icon = ROOT / "assets" / "app" / "icon.ico"
    spec = (
        _SPEC_TEMPLATE
        .replace("@BROWSERS_PATH@", repr(str(browser_cache_dir())))
        .replace("@NAME@", repr(name))
        .replace("@EXCLUDES@", repr(
            _DEAD_MODULE_EXCLUDES + (_SPEC_EXCLUDES if os.name != "nt" else ())
        ))
        .replace("@ICON@", repr(str(icon)) if os.name == "nt" and icon.exists() else "None")
    )
    spec_path = ROOT / "run.spec"
    spec_path.write_text(spec, encoding="utf-8")
    return spec_path


def run_pyinstaller() -> None:
    print("\n=== Building ONEDIR ===")
    code = run(
        [sys.executable, "-m", "PyInstaller", "run.spec", "--noconfirm", "--clean"]
    )
    if code != 0:
        raise SystemExit("PyInstaller build failed.")


def dist_dir(name: str) -> Path:
    return ROOT / "dist" / name


def remove_system_libs(name: str) -> list[str]:
    """Delete host GUI libraries that PyInstaller copied on Linux."""
    internal = dist_dir(name) / "_internal"
    if not internal.is_dir():
        return []

    removed = []
    for pattern in _SYSTEM_LIB_GLOBS:
        for library in sorted(internal.glob(pattern)):
            library.unlink(missing_ok=True)
            removed.append(library.name)
    return removed


def verify_build(name: str) -> None:
    print("\n=== Verify build ===")
    target = dist_dir(name)
    executable = target / (f"{name}.exe" if os.name == "nt" else name)
    if not executable.exists():
        raise SystemExit(f"Build failed: {executable.relative_to(ROOT)} was not created.")

    internal = target / "_internal"
    asset_dir = internal / "assets"
    for asset in _INDICATOR_ASSETS:
        if not (asset_dir / asset).exists():
            raise SystemExit(f"Missing bundled asset: assets/{asset}")
    print("OK: Indicator SVG assets bundled.")

    if os.name == "nt":
        return

    chromium = list(internal.glob("ms-playwright/chromium*/**/chrome"))
    if not chromium:
        raise SystemExit("Playwright Chromium was not bundled.")
    print(f"Chromium executable(s): {len(chromium)}")

    leftovers = [
        p.name for pattern in _SYSTEM_LIB_GLOBS for p in internal.glob(pattern)
    ]
    if leftovers:
        raise SystemExit(
            "System GUI libraries are still bundled: " + ", ".join(leftovers)
        )
    print("OK: No system GUI libraries bundled.")


def trim_bundle(name: str) -> int:
    """Delete files the app never uses, to shrink the bundle.

    Covers leftovers the excludes miss (Tcl/Tk data, pikepdf) and Chromium
    extras (every locale but English, the Widevine DRM module).
    """
    target = dist_dir(name)
    internal = target / "_internal"
    if not internal.is_dir():
        return 0

    before = dir_size(target)

    for pattern in _TRIM_GLOBS:
        for path in internal.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    for module in internal.glob("ms-playwright/chromium*/chrome-*"):
        if not module.is_dir():
            continue
        shutil.rmtree(module / "WidevineCdm", ignore_errors=True)
        locales = module / "locales"
        if locales.is_dir():
            for pak in locales.glob("*.pak"):
                if pak.name not in _CHROMIUM_KEEP_LOCALES:
                    pak.unlink(missing_ok=True)

    saved = before - dir_size(target)
    print(
        f"\n=== Trimming bundle ===\n"
        f"Removed {saved / (1024 * 1024):.1f} MB of unused files."
    )
    return saved


def cleanup_temp() -> None:
    print("\n=== Removing temporary files ===")
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    (ROOT / "run.spec").unlink(missing_ok=True)


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def build(name: str, skip_browsers: bool) -> int:
    install_dependencies()
    ensure_pyinstaller()
    patch_nodriver()
    if skip_browsers:
        print("\nSkipping Chromium download (--skip-browsers).")
    else:
        install_browsers()
    verify_project()
    clean()
    write_spec(name)
    run_pyinstaller()

    if os.name != "nt":
        for library in remove_system_libs(name):
            print(f"Removed bundled {library} (must come from the host)")

    trim_bundle(name)

    verify_build(name)
    cleanup_temp()

    print("\n==========================================")
    print(" Build successful")
    print("==========================================")
    print(f"Build size: {dir_size(dist_dir(name)) / (1024 * 1024):.2f} MB")
    print(f"\nOutput:\n{dist_dir(name)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a standalone ComicDownloadTool executable with PyInstaller."
    )
    parser.add_argument(
        "--name", default=DEFAULT_NAME, help="executable name"
    )
    parser.add_argument(
        "--skip-browsers",
        action="store_true",
        help="reuse the Playwright Chromium already downloaded",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="build with the current interpreter instead of the project venv",
    )
    args = parser.parse_args()

    ensure_venv(args.no_venv)
    try:
        return build(args.name, args.skip_browsers)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"\nBuild failed: {exc.code}", file=sys.stderr)
        return 1 if exc.code not in (0, None) else 0


if __name__ == "__main__":
    raise SystemExit(main())

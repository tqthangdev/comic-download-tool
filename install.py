#!/usr/bin/env python3
"""
Auto-installer for the Comic Download Tool.

Installs everything needed to run the app, all kept inside the code folder:
  1. Creates a virtual environment (.venv) — if the system lacks support
     (python3-venv / ensurepip) it falls back to installing packages into vendor/.
  2. Installs the dependencies listed in requirements.txt.
  3. Downloads Chromium for Playwright into ms-playwright/.

Usage:
  python install.py                # install everything
  python install.py --no-venv      # skip venv, install packages into vendor/
  python install.py --skip-browsers  # skip downloading Chromium (packages only)
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
VENV_DIR = ROOT / ".venv"
VENDOR_DIR = ROOT / "vendor"
BROWSERS_DIR = ROOT / "ms-playwright"


def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    subprocess.check_call(cmd, **kwargs)


def venv_python() -> Path:
    return (
        VENV_DIR / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else VENV_DIR / "bin" / "python"
    )


def main():
    print("=" * 60)
    print("  Comic Download Tool - Auto Installer")
    print("=" * 60)

    print(f"\nPython: {sys.version.split()[0]} ({sys.executable})")
    print(f"Hệ điều hành: {sys.platform}")

    if not REQUIREMENTS.exists():
        print(f"\nLỖI: không tìm thấy {REQUIREMENTS.name} trong thư mục project.")
        sys.exit(1)

    no_venv = "--no-venv" in sys.argv
    skip_browsers = "--skip-browsers" in sys.argv

    # ================= 1. VIRTUAL ENVIRONMENT =================
    venv_mode = None  # "venv" | "vendor"
    if no_venv:
        print("\n[1/3] Bỏ qua tạo venv (--no-venv), cài package vào thư mục vendor/.")
        venv_mode = "vendor"
    else:
        print("\n[1/3] Tạo virtual environment...")
        try:
            run([sys.executable, "-m", "venv", str(VENV_DIR)])
            vpy = venv_python()
            if not vpy.exists():
                raise FileNotFoundError(vpy)
            print(f"   Virtual environment đã sẵn sàng: {VENV_DIR}")
            venv_mode = "venv"
        except Exception as e:
            print(f"   Không tạo được venv: {e}")
            print("   -> Fallback: cài package vào thư mục vendor/ trong project.")
            venv_mode = "vendor"

    install_env = None
    py = sys.executable
    if venv_mode == "venv":
        py = venv_python()
    else:
        # Install packages directly into project/vendor, not touching system/user.
        VENDOR_DIR.mkdir(exist_ok=True)
        install_env = dict(os.environ)
        install_env["PYTHONPATH"] = str(VENDOR_DIR)

    # ================= 2. INSTALL DEPENDENCIES =================
    print("\n[2/3] Cài đặt dependencies...")
    install_args = [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if venv_mode == "vendor":
        install_args.append("--target")
        install_args.append(str(VENDOR_DIR))
    run(install_args, env=install_env)

    # ================= 3. PLAYWRIGHT BROWSERS =================
    if skip_browsers:
        print("\n[3/3] Bỏ qua tải Chromium (--skip-browsers).")
    else:
        print("\n[3/3] Tải Chromium cho Playwright (có thể mất vài phút)...")
        # Install Chromium into project/ms-playwright so the app always runs
        # from the code folder (portable), independent of the machine's cache.
        browser_env = dict(os.environ)
        browser_env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)
        run([str(py), "-m", "playwright", "install", "chromium"], env=browser_env)

    # ================= DONE =================
    print("\n" + "=" * 60)
    print("  Hoàn tất! Chạy app bằng lệnh:")
    if venv_mode == "venv":
        print(f"    {venv_python()} run.py")
    else:
        print(f"    PYTHONPATH={VENDOR_DIR} {py} run.py")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\nLỖI: lệnh thất bại (mã {e.returncode}): {e.cmd}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nĐã huỷ.")
        sys.exit(130)

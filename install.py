#!/usr/bin/env python3
"""
Auto-installer cho Comic Download Tool.

Cài mọi thứ cần thiết để chạy app:
  1. Tạo virtual environment (.venv) — nếu hệ thống không hỗ trợ (thiếu
     python3-venv / ensurepip) thì tự fallback cài vào user site-packages.
  2. Cài các dependencies trong requirements.txt.
  3. Tải Chromium cho Playwright (chạy `python run.py --install-browsers`
     cũng tương đương bước này).

Cách dùng:
  python install.py                # cài hết
  python install.py --no-venv      # không tạo venv, cài thẳng (user/system)
  python install.py --skip-browsers  # bỏ qua tải Chromium (nếu chỉ muốn cài package)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
VENV_DIR = ROOT / ".venv"


def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    subprocess.check_call(cmd, **kwargs)


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
    venv_python = None
    if no_venv:
        print("\n[1/3] Bỏ qua tạo venv (--no-venv), cài thẳng vào môi trường hiện tại.")
    else:
        print("\n[1/3] Tạo virtual environment...")
        try:
            run([sys.executable, "-m", "venv", str(VENV_DIR)])
            venv_python = (
                VENV_DIR / "Scripts" / "python.exe"
                if sys.platform == "win32"
                else VENV_DIR / "bin" / "python"
            )
            if not venv_python.exists():
                raise FileNotFoundError(venv_python)
            print(f"   Virtual environment đã sẵn sàng: {VENV_DIR}")
        except Exception as e:
            print(f"   Không tạo được venv: {e}")
            print("   -> Fallback: cài vào user site-packages (--user).")
            venv_python = None

    py = venv_python or sys.executable

    # ================= 2. INSTALL DEPENDENCIES =================
    print("\n[2/3] Cài đặt dependencies...")
    install_args = [str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    if venv_python is None:
        install_args.append("--user")
        if sys.platform != "win32":
            # PEP 668: nhiều distro Linux chặn pip cài vào hệ thống
            install_args.append("--break-system-packages")
    run(install_args)

    # ================= 3. PLAYWRIGHT BROWSERS =================
    if skip_browsers:
        print("\n[3/3] Bỏ qua tải Chromium (--skip-browsers).")
    else:
        print("\n[3/3] Tải Chromium cho Playwright (có thể mất vài phút)...")
        run([str(py), "-m", "playwright", "install", "chromium"])

    # ================= DONE =================
    print("\n" + "=" * 60)
    print("  Hoàn tất! Chạy app bằng lệnh:")
    if venv_python:
        print(f"    {venv_python} run.py")
    else:
        print(f"    {py} run.py")
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

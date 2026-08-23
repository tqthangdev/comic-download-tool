#!/usr/bin/env bash
#
# Click-to-run cho Linux/macOS:
#   - tự kiểm tra môi trường (.venv hoặc vendor/),
#   - nếu chưa cài thì chạy install.py,
#   - rồi khởi động run.py.
set -e
cd "$(dirname "$0")"

pick_python() {
    if [ -x ".venv/bin/python" ]; then
        PY=".venv/bin/python"
    elif [ -d "vendor" ]; then
        PY="python3"
        export PYTHONPATH="$PWD/vendor"
    else
        PY=""
    fi
}

pick_python

if [ -z "$PY" ]; then
    if [ ! -f "requirements.txt" ]; then
        echo "Khong tim thay requirements.txt trong thu muc project."
        echo "Hay chay: python3 install.py"
        exit 1
    fi
    echo "Chua cai dependencies. Dang cai đat (co the mat vai phut)..."
    python3 install.py
    pick_python
    if [ -z "$PY" ]; then
        echo "Cai dat that bai. Hay chay thu cong: python3 install.py"
        exit 1
    fi
fi

exec "$PY" run.py
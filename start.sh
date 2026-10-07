#!/usr/bin/env bash
#
# Click-to-run for Linux/macOS:
#   - detect the environment (.venv or vendor/),
#   - if nothing is installed, run ./setup.sh,
#   - then launch run.py.
set -e
cd "$(dirname "$0")"

pick_python() {
    if [ -x ".venv/bin/python" ]; then
        PY=".venv/bin/python"
        # Cannot import nodriver to locate it (that import is the failure), so
        # resolve the venv's site-packages via sysconfig instead.
        NODRIVER_DIR="$("$PY" -c "import sysconfig, os; print(os.path.join(sysconfig.get_paths()['purelib'], 'nodriver'))" 2>/dev/null || true)"
    elif [ -d "vendor" ]; then
        PY="python3"
        export PYTHONPATH="$PWD/vendor"
        NODRIVER_DIR="$PWD/vendor/nodriver"
    else
        PY=""
        NODRIVER_DIR=""
    fi
}

pick_python

if [ -z "$PY" ]; then
    if [ ! -f "pyproject.toml" ]; then
        echo "pyproject.toml not found in the project folder."
        echo "Please run: ./setup.sh"
        exit 1
    fi
    echo "Dependencies not installed. Installing (this may take a few minutes)..."
    ./setup.sh
    pick_python
    if [ -z "$PY" ]; then
        echo "Installation failed. Please run manually: ./setup.sh"
        exit 1
    fi
fi

# Patch the nodriver UTF-8 bug (safe to run repeatedly), matching start.bat.
if [ -n "$NODRIVER_DIR" ] && [ -f "$PWD/lib/fix_nodriver.py" ]; then
    "$PY" "$PWD/lib/fix_nodriver.py" "$NODRIVER_DIR" || true
fi

exec "$PY" run.py
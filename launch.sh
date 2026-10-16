#!/usr/bin/env bash
# launch.sh - Automated Cross-Platform Launcher for macOS and Linux
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ">>> AI Context Dumper Launcher"

# 1. Locate Supported Python Interpreter (>= 3.9)
PYTHON_BIN=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY_VER="$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
        MINOR="$(echo "$PY_VER" | cut -d. -f2)"
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON_BIN="$(command -v "$cand")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[!] Error: Python >= 3.9 is required, but was not found." >&2
    echo "    Please install Python 3.9+ via your system package manager or pyenv." >&2
    exit 1
fi

# 2. Setup or Re-use Isolated Virtual Environment
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Creating virtual environment in .venv..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# 3. Reconcile Dependencies
echo "Verifying and updating dependencies..."
"$VENV_PYTHON" -m pip install --quiet --upgrade pip
"$VENV_PYTHON" -m pip install --quiet -r requirements.txt

# 4. Launch Application
echo "Starting AI Context Dumper..."
exec "$VENV_PYTHON" dump.py "$@"
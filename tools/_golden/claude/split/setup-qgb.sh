#!/usr/bin/env bash
# GENERATED FILE - DO NOT EDIT.
# This is a generated artifact. Edit skills/source/body.md instead.
# converter_version: 0.1.0
# build_input_digest: a9597890ff883282
set -euo pipefail

# setup-qgb.sh -- qgb installer (venv-default).
#
# Trust boundary note: the default install path below runs
# 'pip install git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v0.1.2', which is clone-equivalent
# trust (arbitrary code from the repo at that tag runs during
# 'pip install').  --require-hashes is not available for VCS
# installs (NF-011); this script does not attempt to simulate it.
# Use --from-path for an offline / local-clone install instead.
#
# This file may not have the executable bit set after extracting
# from a zip archive; invoke it explicitly: bash setup-qgb.sh

FROM_PATH=""
while [ $# -gt 0 ]; do
    case "$1" in
        --from-path)
            FROM_PATH="$2"
            shift 2
            ;;
        --from-path=*)
            FROM_PATH="${1#--from-path=}"
            shift
            ;;
        *)
            echo "[setup-qgb] ERROR: unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

echo "[setup-qgb] Step 1: locating Python..."
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[setup-qgb] ERROR: no working Python 3 interpreter found (tried 'python3' and 'python')." >&2
    echo "[setup-qgb] Install Python 3 and re-run this script." >&2
    exit 1
fi
echo "[setup-qgb] Using interpreter: $PYTHON_CMD"

echo "[setup-qgb] Step 2: checking .venv..."
if [ -d ".venv" ]; then
    echo "[setup-qgb] .venv already exists -- leaving it untouched."
else
    echo "[setup-qgb] Creating .venv..."
    "$PYTHON_CMD" -m venv .venv
fi
VENV_PYTHON=".venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "[setup-qgb] ERROR: expected venv interpreter not found: $VENV_PYTHON" >&2
    exit 1
fi

if [ -n "$FROM_PATH" ]; then
    echo "[setup-qgb] Step 3: installing qgb from local path (editable): $FROM_PATH"
    "$VENV_PYTHON" -m pip install -e "$FROM_PATH"
else
    echo "[setup-qgb] Step 3: installing qgb from git+https://github.com/Yumeno/Quality-gate-builder.git (tag skill-v0.1.2)..."
    "$VENV_PYTHON" -m pip install "git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v0.1.2"
fi

echo "[setup-qgb] Step 4: verifying installation..."
if ! "$VENV_PYTHON" -m qgb --version; then
    echo "[setup-qgb] ERROR: '$VENV_PYTHON -m qgb --version' failed." >&2
    echo "[setup-qgb] qgb was not installed correctly. See the error above." >&2
    exit 1
fi

echo ""
echo "[setup-qgb] qgb installed successfully into .venv."
echo "[setup-qgb] To activate this venv in your shell:"
echo "[setup-qgb]     source .venv/bin/activate"
echo "[setup-qgb] Agent sessions do NOT auto-activate a venv: invoke qgb explicitly instead:"
echo "[setup-qgb]     .venv/bin/python -m qgb <command>"


#!/bin/sh
set -e

if [ ! -f "pyproject.toml" ]; then
    exit 0
fi

if ! grep -q 'name = "unityflow"' pyproject.toml 2>/dev/null; then
    exit 0
fi

echo "[unityflow-dev] Installing development dependencies..."
pip install --quiet --upgrade "black~=26.1.0" "ruff~=0.14.0" "pytest~=9.0.0"
echo "[unityflow-dev] Development tools ready (black, ruff, pytest)"

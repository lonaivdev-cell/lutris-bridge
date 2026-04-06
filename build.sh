#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== lutris-bridge build ==="

# Create/use a venv so we don't pollute the system
if [ ! -d ".venv-build" ]; then
    echo "Creating build virtualenv..."
    python3 -m venv .venv-build
fi

source .venv-build/bin/activate

echo "Installing project and build dependencies..."
pip install --quiet .
pip install --quiet pyinstaller

echo "Running PyInstaller..."
pyinstaller --clean --noconfirm lutris-bridge.spec

echo ""
echo "Build complete: dist/lutris-bridge"
echo "Size: $(du -h dist/lutris-bridge | cut -f1)"

# Quick smoke test
echo ""
echo "Smoke test:"
dist/lutris-bridge --version

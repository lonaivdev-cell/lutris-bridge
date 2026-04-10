#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARCH="${ARCH:-x86_64}"
APPDIR="lutris-bridge.AppDir"
APPIMAGETOOL="appimagetool-${ARCH}.AppImage"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/${APPIMAGETOOL}"

echo "=== lutris-bridge AppImage build ==="

# --- 1. Build GUI binary with PyInstaller -----------------------------------

if [ ! -d ".venv-build" ]; then
    echo "Creating build virtualenv..."
    python3 -m venv .venv-build
fi

source .venv-build/bin/activate

echo "Installing project and build dependencies..."
pip install --quiet .
pip install --quiet pyinstaller

echo "Building GUI binary with PyInstaller..."
pyinstaller --clean --noconfirm lutris-bridge-gui.spec

echo "GUI binary: dist/lutris-bridge-gui ($(du -h dist/lutris-bridge-gui | cut -f1))"

# --- 2. Assemble AppDir -----------------------------------------------------

echo "Assembling AppDir..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

cp dist/lutris-bridge-gui "$APPDIR/usr/bin/"
cp packaging/lutris-bridge.desktop "$APPDIR/"
cp packaging/lutris-bridge.svg "$APPDIR/"
ln -sf usr/bin/lutris-bridge-gui "$APPDIR/AppRun"

# --- 3. Download appimagetool if needed -------------------------------------

if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "$APPIMAGETOOL_URL" -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# --- 4. Build AppImage -------------------------------------------------------

echo "Building AppImage..."

# In Docker / CI environments FUSE is unavailable, so extract and run directly.
if [ "${APPIMAGE_EXTRACT_AND_RUN:-0}" = "1" ]; then
    if [ ! -d "squashfs-root" ]; then
        ./"$APPIMAGETOOL" --appimage-extract >/dev/null 2>&1
    fi
    ARCH="$ARCH" ./squashfs-root/AppRun "$APPDIR" "dist/lutris-bridge-${ARCH}.AppImage"
else
    ARCH="$ARCH" ./"$APPIMAGETOOL" "$APPDIR" "dist/lutris-bridge-${ARCH}.AppImage"
fi

chmod +x "dist/lutris-bridge-${ARCH}.AppImage"

echo ""
echo "=== Build complete ==="
echo "AppImage: dist/lutris-bridge-${ARCH}.AppImage ($(du -h "dist/lutris-bridge-${ARCH}.AppImage" | cut -f1))"

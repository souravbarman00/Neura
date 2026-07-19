#!/usr/bin/env bash
# Build "Neura.app" — a native-window macOS app (WKWebView via pywebview, NO browser)
# that boots the local services and shows the UI — then package it into "Neura.dmg".
#
# Like alive's build_mac_app.sh, this is a LAUNCHER bundle: it runs the project in
# place using this repo's .venv + built frontend/dist. It works on a Mac where the
# project is set up (the .app hardcodes this repo path). For a fully self-contained
# installer for arbitrary Macs, the .venv + dist would need to be bundled (multi-GB)
# and the app notarized — see the notes at the end.
#
# Run:  (cd frontend && npm run build) && bash scripts/build_mac_app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Neura"
BUILD_DIR="$ROOT/dist-app"
APP="$BUILD_DIR/$APP_NAME.app"
DMG="$ROOT/$APP_NAME.dmg"

echo "▸ Building $APP  (ROOT=$ROOT)"

# ---- Preconditions ----
[ -x "$ROOT/.venv/bin/python" ] || { echo "✗ .venv missing — set up the project venv first"; exit 1; }
"$ROOT/.venv/bin/python" -c "import webview" 2>/dev/null \
  || { echo "✗ pywebview not in .venv — run: uv pip install --python .venv/bin/python pywebview"; exit 1; }
[ -f "$ROOT/desktop.py" ] || { echo "✗ desktop.py missing"; exit 1; }
[ -f "$ROOT/frontend/dist/index.html" ] || { echo "✗ frontend not built — run: (cd frontend && npm run build)"; exit 1; }

rm -rf "$BUILD_DIR"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# ---- Info.plist (real window app: dock icon, high-DPI) ----
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.neura.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>neura</string>
  <key>CFBundleIconFile</key><string>neura</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# ---- Launcher executable: run the pywebview desktop app (native window, no browser) ----
cat > "$APP/Contents/MacOS/neura" <<LAUNCHER
#!/bin/bash
ROOT="$ROOT"
cd "\$ROOT" || exit 1
LOGDIR="\$HOME/Library/Logs/Neura"; mkdir -p "\$LOGDIR"
echo "=== Neura start \$(date) ===" >> "\$LOGDIR/neura.log"
exec "\$ROOT/.venv/bin/python" "\$ROOT/desktop.py" >> "\$LOGDIR/neura.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/neura"

# ---- Icon (best-effort; app works without it) ----
SRC_PNG=""
for c in "$ROOT/frontend/public/icon.png" "$ROOT/frontend/public/logo.png" "$ROOT/frontend/dist/favicon.png"; do
  [ -f "$c" ] && { SRC_PNG="$c"; break; }
done
if [ -n "$SRC_PNG" ] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  TMP="$(mktemp -d)/neura.iconset"; mkdir -p "$TMP"
  for s in 16 32 64 128 256 512; do
    sips -z $s $s "$SRC_PNG" --out "$TMP/icon_${s}x${s}.png" >/dev/null 2>&1 || true
    d=$((s*2)); sips -z $d $d "$SRC_PNG" --out "$TMP/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
  done
  iconutil -c icns "$TMP" -o "$APP/Contents/Resources/neura.icns" 2>/dev/null || echo "  (icon skipped)"
else
  echo "  (no source icon found — skipping)"
fi

# ---- Ad-hoc sign so it launches on Apple Silicon ----
codesign --force --deep -s - "$APP" 2>/dev/null && echo "  ✓ ad-hoc signed" || echo "  (codesign skipped)"

# ---- Package into a .dmg with an /Applications drop target ----
STAGE="$(mktemp -d)/${APP_NAME}"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

# ---- Refresh Launch Services so it shows in Spotlight/Launchpad immediately ----
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true

echo "✅ Built $APP"
echo "✅ Built $DMG"
echo "   Open $DMG and drag Neura → Applications, then launch it (native window, no browser)."

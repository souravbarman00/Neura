#!/usr/bin/env bash
# Build a FULLY STANDALONE "Neura.app" (+ Neura.dmg): bundles a relocatable Python
# with ALL packages pre-installed + the React build + source. On first launch the
# app unpacks its payload to ~/Library/Application Support/Neura (writable), so the
# DBs/memory/chroma auto-create there, then opens the native window. No browser, no
# terminal, no pip, no repo needed on the target machine.
#
#   Models (Kokoro/Whisper) download on first run.  Ad-hoc signed (local use).
#
# Run:  (cd frontend && npm run build) && bash scripts/build_standalone_app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Neura"
OUT="$ROOT/dist-standalone"
PAYLOAD="$OUT/payload"
APP="$OUT/$APP_NAME.app"
DMG="$ROOT/$APP_NAME.dmg"
VERSION="1.0.0"

echo "▸ Standalone build for $APP_NAME  (ROOT=$ROOT)"

# ---- Preconditions ----
command -v uv >/dev/null || { echo "✗ uv not found (needed to resolve/install deps)"; exit 1; }
[ -f "$ROOT/frontend/dist/index.html" ] || { echo "✗ frontend not built — run: (cd frontend && npm run build)"; exit 1; }
[ -f "$ROOT/desktop.py" ] || { echo "✗ desktop.py missing"; exit 1; }
# Relocatable base python (python-build-standalone that uv manages).
BASE_PY="$(sed -n 's/^executable = //p' "$ROOT/.venv/pyvenv.cfg" | head -1)"   # .../cpython-.../bin/python3.13
BASE_ROOT="$(cd "$(dirname "$BASE_PY")/.." && pwd)"
[ -x "$BASE_ROOT/bin/python3" ] || { echo "✗ base standalone python not found ($BASE_ROOT)"; exit 1; }
echo "  base python: $BASE_ROOT"

# ---- 1. Fresh payload: relocatable python with ALL deps installed into it ----
rm -rf "$OUT"; mkdir -p "$PAYLOAD"
echo "▸ Copying relocatable python → payload/.venv"
cp -R "$BASE_ROOT" "$PAYLOAD/.venv"
[ -e "$PAYLOAD/.venv/bin/python" ] || ln -sf python3 "$PAYLOAD/.venv/bin/python"
# The copy inherits uv's PEP-668 "externally managed" marker; strip it so we can
# install packages directly into this (now standalone, relocatable) python.
find "$PAYLOAD/.venv" -name EXTERNALLY-MANAGED -delete 2>/dev/null || true

echo "▸ Installing all packages into the bundled python (uv; may take a few minutes)"
uv pip install --python "$PAYLOAD/.venv/bin/python3" \
  -r "$ROOT/requirements.txt" \
  -r "$ROOT/backend/requirements.txt" \
  -r "$ROOT/services/tts/requirements.txt" \
  -r "$ROOT/services/stt/requirements.txt"

# ---- 2. App source + built UI into the payload (exclude personal/dev cruft) ----
echo "▸ Copying app source + built UI"
rsync -a \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'data' --exclude 'logs' --exclude '.env' \
  --exclude 'node_modules' --exclude 'dist-app' --exclude 'dist-standalone' \
  "$ROOT/backend" "$ROOT/coded_tools" "$ROOT/middleware" "$ROOT/registries" \
  "$ROOT/config" "$ROOT/services" "$ROOT/scripts" "$ROOT/desktop.py" \
  "$PAYLOAD/"
mkdir -p "$PAYLOAD/frontend"; rsync -a "$ROOT/frontend/dist" "$PAYLOAD/frontend/"
[ -f "$ROOT/.env.example" ] && cp "$ROOT/.env.example" "$PAYLOAD/.env.example" || true
echo "$VERSION" > "$PAYLOAD/.neura_version"
echo "  payload size: $(du -sh "$PAYLOAD" | cut -f1)"

# ---- 3. Compress payload (shipped inside the .app; extracted on first run) ----
echo "▸ Compressing payload"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
tar -C "$PAYLOAD" -czf "$APP/Contents/Resources/payload.tgz" .
echo "  payload.tgz: $(du -sh "$APP/Contents/Resources/payload.tgz" | cut -f1)"

# ---- 4. Info.plist ----
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.neura.app</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>neura</string>
  <key>CFBundleIconFile</key><string>neura</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# ---- 5. Launcher: extract payload to Application Support on first run, then run ----
cat > "$APP/Contents/MacOS/neura" <<'LAUNCHER'
#!/bin/bash
set -u
# IMPORTANT: extract to a SPACE-FREE path. neuro-san splits AGENT_MANIFEST_FILE on
# spaces (to allow multiple manifests), so a path like "…/Application Support/…"
# gets shredded into bogus entries and the manifest restore crashes.
APPSUP="$HOME/.neura"
DEST="$APPSUP/app"
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
LOGDIR="$HOME/Library/Logs/Neura"; mkdir -p "$LOGDIR" "$APPSUP"
LOG="$LOGDIR/neura.log"
# Re-extract when the bundled payload CONTENT changes (hash), not a version string,
# so every new build is picked up even if the version wasn't bumped.
HASH_BUNDLED="$(/usr/bin/shasum -a 1 "$RES/payload.tgz" | /usr/bin/cut -d' ' -f1)"
HASH_INSTALLED="$(cat "$DEST/.neura_payload_hash" 2>/dev/null || echo x)"

if [ ! -x "$DEST/.venv/bin/python3" ] || [ "$HASH_BUNDLED" != "$HASH_INSTALLED" ]; then
  echo "=== Neura: (re)installing payload $(date) ===" >> "$LOG"
  rm -rf "$DEST.new"; mkdir -p "$DEST.new"
  /usr/bin/tar -C "$DEST.new" -xzf "$RES/payload.tgz" >> "$LOG" 2>&1
  # preserve the user's data + API key across upgrades
  [ -d "$DEST/data" ] && { rm -rf "$DEST.new/data"; mv "$DEST/data" "$DEST.new/data"; }
  [ -f "$DEST/.env" ] && cp "$DEST/.env" "$DEST.new/.env"
  rm -rf "$DEST"; mv "$DEST.new" "$DEST"
  echo "$HASH_BUNDLED" > "$DEST/.neura_payload_hash"
  [ -f "$DEST/.env" ] || { [ -f "$DEST/.env.example" ] && cp "$DEST/.env.example" "$DEST/.env"; }
fi

echo "=== Neura start $(date) ===" >> "$LOG"
cd "$DEST" || exit 1
exec "$DEST/.venv/bin/python3" "$DEST/desktop.py" >> "$LOG" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/neura"

# ---- 6. Icon (best-effort) ----
for c in "$ROOT/frontend/public/icon.png" "$ROOT/frontend/public/logo.png"; do
  if [ -f "$c" ] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
    TMP="$(mktemp -d)/neura.iconset"; mkdir -p "$TMP"
    for s in 16 32 64 128 256 512; do
      sips -z $s $s "$c" --out "$TMP/icon_${s}x${s}.png" >/dev/null 2>&1 || true
      d=$((s*2)); sips -z $d $d "$c" --out "$TMP/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$TMP" -o "$APP/Contents/Resources/neura.icns" 2>/dev/null || true
    break
  fi
done

# ---- 7. Ad-hoc sign + package ----
codesign --force --deep -s - "$APP" 2>/dev/null && echo "  ✓ ad-hoc signed" || echo "  (codesign skipped)"
STAGE="$(mktemp -d)/$APP_NAME"; mkdir -p "$STAGE"; cp -R "$APP" "$STAGE/"; ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"; hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null; rm -rf "$STAGE"

echo "✅ Built $APP  ($(du -sh "$APP" | cut -f1))"
echo "✅ Built $DMG  ($(du -sh "$DMG" | cut -f1))"
echo "   First launch unpacks to ~/Library/Application Support/Neura and opens the app."

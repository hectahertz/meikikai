#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="MeikiKai"
BUILT_APP="dist/${APP_NAME}.app"
INSTALLED_APP="/Applications/${APP_NAME}.app"
ENTITLEMENTS_FILE="packaging/macos/entitlements.plist"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv/bin/python. Create/install the project virtualenv first." >&2
  exit 1
fi

echo "Chrome Screen AI is not bundled; use the in-app OCR Setup after launch."

echo "Building ${APP_NAME}.app..."
".venv/bin/python" -m PyInstaller -y meikikai.macos.spec

if [[ -n "${MEIKIKAI_CODESIGN_IDENTITY:-}" ]]; then
  echo "Signing ${BUILT_APP}..."
  codesign --force --deep --options runtime --entitlements "$ENTITLEMENTS_FILE" --sign "$MEIKIKAI_CODESIGN_IDENTITY" "$BUILT_APP"
else
  echo "Ad-hoc signing ${BUILT_APP}..."
  codesign --force --deep --options runtime --entitlements "$ENTITLEMENTS_FILE" --sign - "$BUILT_APP"
fi

echo "Installing ${INSTALLED_APP}..."
osascript -e "quit app \"${APP_NAME}\"" >/dev/null 2>&1 || true
sleep 1
rm -rf "$INSTALLED_APP"
ditto "$BUILT_APP" "$INSTALLED_APP"

echo "Opening ${INSTALLED_APP}..."
open "$INSTALLED_APP"

echo "Done."

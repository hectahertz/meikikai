#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEFAULT_DEST_DIR="$HOME/Library/Application Support/meikikai/screen_ai"
DEST_DIR="${1:-$DEFAULT_DEST_DIR}"
ARCH="$(uname -m)"

case "$ARCH" in
  arm64|aarch64)
    CIPD_PLATFORM="mac-arm64"
    ;;
  x86_64|amd64)
    CIPD_PLATFORM="mac-amd64"
    ;;
  *)
    echo "Unsupported macOS architecture: $ARCH" >&2
    exit 1
    ;;
esac

PACKAGE="chromium/third_party/screen-ai/${CIPD_PLATFORM}"
SOURCE="Google/Chromium public CIPD infrastructure"
STAMP_FILE="$DEST_DIR/.screen_ai_package"
CLIENT_URL="https://chrome-infra-packages.appspot.com/client?platform=${CIPD_PLATFORM}&version=latest"

if [[ -f "$DEST_DIR/libchromescreenai.so" ]] \
  && [[ -f "$STAMP_FILE" ]] \
  && grep -qx "package=$PACKAGE" "$STAMP_FILE" \
  && grep -qx "requested_version=latest" "$STAMP_FILE"; then
  echo "Chrome Screen AI already installed at $DEST_DIR"
  exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CIPD_BIN="$TMP_DIR/cipd"
PACKAGE_ROOT="$TMP_DIR/package"
ENSURE_FILE="$TMP_DIR/screen_ai.ensure"

curl -fsSL "$CLIENT_URL" -o "$CIPD_BIN"
chmod +x "$CIPD_BIN"
mkdir -p "$PACKAGE_ROOT"
printf '%s latest\n' "$PACKAGE" > "$ENSURE_FILE"
"$CIPD_BIN" export -root "$PACKAGE_ROOT" -ensure-file "$ENSURE_FILE"

if [[ ! -f "$PACKAGE_ROOT/resources/libchromescreenai.so" ]]; then
  echo "Chrome Screen AI package did not contain resources/libchromescreenai.so" >&2
  exit 1
fi

DESCRIBE_OUTPUT="$({ "$CIPD_BIN" describe "$PACKAGE" -version latest || true; } 2>/dev/null)"
VERSION_TAG="$(printf '%s\n' "$DESCRIBE_OUTPUT" | awk '/^[[:space:]]*version:/ {print $1; exit}')"
INSTANCE_ID="$(printf '%s\n' "$DESCRIBE_OUTPUT" | awk -F': ' '/^Instance ID:/ {print $2; exit}')"

rm -rf "$DEST_DIR"
mkdir -p "$(dirname "$DEST_DIR")"
ditto "$PACKAGE_ROOT/resources" "$DEST_DIR"
{
  printf 'source=%s\n' "$SOURCE"
  printf 'package=%s\n' "$PACKAGE"
  printf 'platform=%s\n' "$CIPD_PLATFORM"
  printf 'requested_version=latest\n'
  if [[ -n "$VERSION_TAG" ]]; then
    printf 'resolved_version=%s\n' "$VERSION_TAG"
  fi
  if [[ -n "$INSTANCE_ID" ]]; then
    printf 'instance_id=%s\n' "$INSTANCE_ID"
  fi
  printf 'cipd_client_url=%s\n' "$CLIENT_URL"
  printf 'installed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$STAMP_FILE"

echo "Chrome Screen AI installed at $DEST_DIR"

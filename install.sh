#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="${OPENCLAW_SKILL_DIR:-$HOME/.openclaw/skills}/seedance2-video-studio"
TARGET_DIR="$SKILL_DIR"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$TARGET_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude 'scripts/__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'runtime/.env.local' \
    --exclude 'runtime/downloads/' \
    --exclude '*.mp4' \
    --exclude '*.mov' \
    "$SRC_DIR/" "$TARGET_DIR/"
else
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R "$SRC_DIR"/* "$TARGET_DIR"/
  rm -rf "$TARGET_DIR/runtime/downloads" "$TARGET_DIR/scripts/__pycache__" || true
  find "$TARGET_DIR" -name '*.pyc' -delete || true
  rm -f "$TARGET_DIR/runtime/.env.local" || true
fi

chmod +x "$TARGET_DIR/scripts/seedance2_video.py" || true
chmod +x "$TARGET_DIR/install.sh" || true

echo "Installed seedance2-video-studio to: $TARGET_DIR"

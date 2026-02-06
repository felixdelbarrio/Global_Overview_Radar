#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${VISUAL_QA_URL:-http://localhost:3000}}"
OUT_DIR="${2:-${VISUAL_QA_OUT:-/tmp/visual-qa}}"
VIEWPORT="${VISUAL_QA_VIEWPORT:-390,844}"
DEVICE_SCALE="${VISUAL_QA_SCALE:-2}"
USER_AGENT="${VISUAL_QA_UA:-Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1}"

CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME_BIN" ]; then
  CHROME_BIN="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
fi
if [ -z "$CHROME_BIN" ]; then
  echo "Chrome not found. Set CHROME_BIN or install Chrome/Chromium."
  exit 1
fi

mkdir -p "$OUT_DIR"

PAGES=(
  "/"
  "/sentimiento"
)

echo "Visual QA (mobile)"
echo "- Base URL: $BASE_URL"
echo "- Output: $OUT_DIR"
echo "- Viewport: $VIEWPORT"

for page in "${PAGES[@]}"; do
  safe_name="$(echo "$page" | sed 's#[/ ]#_#g' | sed 's#^_##')"
  if [ -z "$safe_name" ]; then
    safe_name="home"
  fi
  url="${BASE_URL%/}$page"
  out="${OUT_DIR}/${safe_name}.png"
  "$CHROME_BIN" \
    --headless \
    --disable-gpu \
    --hide-scrollbars \
    --disable-background-networking \
    --window-size="$VIEWPORT" \
    --force-device-scale-factor="$DEVICE_SCALE" \
    --user-agent="$USER_AGENT" \
    --virtual-time-budget=4000 \
    --run-all-compositor-stages-before-draw \
    --screenshot="$out" \
    "$url" > /dev/null 2>&1
  echo "Saved: $out"
done

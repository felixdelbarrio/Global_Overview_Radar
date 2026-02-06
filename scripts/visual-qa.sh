#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTDIR="${FRONTDIR:-$ROOT_DIR/frontend/brr-frontend}"
HOST="${HOST:-127.0.0.1}"
FRONT_PORT="${FRONT_PORT:-3000}"
QA_ROUTE="${VISUAL_QA_ROUTE:-/}"
QA_LABEL="${VISUAL_QA_LABEL:-app}"
QA_DIR="${VISUAL_QA_DIR:-/tmp/visual-qa/${QA_LABEL}}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ ! -x "$CHROME" ]]; then
  echo "Chrome no encontrado en $CHROME"
  echo "Configura CHROME=/ruta/al/Google\\ Chrome"
  exit 1
fi

mkdir -p "$QA_DIR"

pushd "$FRONTDIR" >/dev/null
npm run dev -- --hostname "$HOST" --port "$FRONT_PORT" >"$QA_DIR/${QA_LABEL}-dev.log" 2>&1 &
DEV_PID=$!
popd >/dev/null

cleanup() {
  kill "$DEV_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

URL_BASE="http://${HOST}:${FRONT_PORT}${QA_ROUTE}"
if [[ "$QA_ROUTE" == *"?"* ]]; then
  SEP="&"
else
  SEP="?"
fi

for _ in {1..30}; do
  if curl -s --max-time 2 -o /dev/null "$URL_BASE"; then
    break
  fi
  sleep 1
done

take_shot() {
  local label="$1"
  local size="$2"
  local scale="$3"
  local theme="$4"

  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size="$size" --force-device-scale-factor="$scale" \
    --screenshot="$QA_DIR/${QA_LABEL}-${label}-${theme}.png" \
    "${URL_BASE}${SEP}theme=${theme}"
}

for theme in ambient-light ambient-dark; do
  take_shot "desktop" "1440,900" "1" "$theme"
  take_shot "mobile" "390,844" "2" "$theme"
done

echo "Visual QA listo: $QA_DIR"

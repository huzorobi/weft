#!/usr/bin/env bash
# Weft launcher. One click: ensure the venv, start the local Streamlit UI, open the browser.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
PORT="${WEFT_PORT:-8501}"
URL="http://127.0.0.1:${PORT}"
LOG="$HOME/.weft-ui.log"

if [ "${1:-}" = "--stop" ]; then
  pids=$(ss -ltnp 2>/dev/null | awk -v p=":${PORT} " '$0 ~ p' | grep -o "pid=[0-9]*" | cut -d= -f2 | sort -u)
  [ -n "$pids" ] && kill $pids && echo "stopped weft ($pids)" || echo "weft not running on ${PORT}"
  exit 0
fi

# first run: create the venv + install deps
if [ ! -x .venv/bin/streamlit ]; then
  echo "→ first run: setting up weft (venv + deps)…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -e . || ./.venv/bin/pip install --quiet -r requirements.txt
fi

# start the UI only if the port is free
if ! (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
  echo "→ starting weft on ${URL}"
  PYTHONPATH=src setsid ./.venv/bin/streamlit run src/weft/ui/app.py \
      --server.port "${PORT}" --server.address 127.0.0.1 \
      --server.headless true --browser.gatherUsageStats false \
      >"$LOG" 2>&1 </dev/null &
  for _ in $(seq 1 40); do
    (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null && break; sleep 0.5
  done
else
  echo "→ weft already running on ${URL}"
fi

# open the browser (best-effort across desktops)
( xdg-open "$URL" || sensible-browser "$URL" || firefox "$URL" || chromium "$URL" ) >/dev/null 2>&1 &
echo "→ opened ${URL}   UI log: ${LOG}"
echo "   Close this window any time; the UI keeps running. Stop it with:  $(readlink -f "$0") --stop"
# keep the window on the live log
tail -n +1 -f "$LOG" 2>/dev/null || true

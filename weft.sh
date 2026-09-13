#!/usr/bin/env bash
# Weft launcher — one click cold-starts the whole stack, then the UI.
#   Starts the self-hosted services (Neo4j, SearXNG, Tor) as Docker containers, waits for
#   Neo4j, then starts the Streamlit UI and opens the browser. No docker-compose needed.
#   ./weft.sh --stop   stops the UI and the stack.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
PORT="${WEFT_PORT:-8501}"
URL="http://127.0.0.1:${PORT}"
LOG="$HOME/.weft-ui.log"

# Reliable TCP reachability check (python3 is always present; bash /dev/tcp is flaky in some shells).
port_open() {
  python3 - "$1" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(2)
sys.exit(s.connect_ex(("127.0.0.1", int(sys.argv[1]))))
PY
}
have_docker() { command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; }

# Idempotent: keep a container that is already running with the right port published;
# otherwise (stopped, missing, or stale port mapping) recreate it fresh. A named volume
# preserves stateful data (Neo4j) across recreation, so ports are always correct.
ensure_container() {
  local name="$1" check_port="$2"; shift 2
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name" \
     && docker port "$name" "$check_port" >/dev/null 2>&1; then
    return 0
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --restart unless-stopped "$@" >/dev/null 2>&1 || true
}

start_stack() {
  echo "→ starting the stack (Neo4j, SearXNG, Tor)…"
  ensure_container weft-neo4j 7687 -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/change_me -e 'NEO4J_PLUGINS=["apoc"]' \
    -v weft_neo4j_data:/data neo4j:5-community
  ensure_container weft-searxng 8080 -p 8080:8080 \
    -v "$PWD/deploy/searxng:/etc/searxng" searxng/searxng:latest
  ensure_container weft-tor 9050 -p 9050:9050 osminogin/tor-simple
  printf "→ waiting for Neo4j"
  for _ in $(seq 1 90); do port_open 7687 && break; printf "."; sleep 1; done
  port_open 7687 && echo " ready" || echo " (not ready yet; UI still runs, persistence may be degraded)"
}

stop_stack() {
  echo "→ stopping the stack…"
  docker stop weft-neo4j weft-searxng weft-tor >/dev/null 2>&1 || true
  echo "stack stopped"
}

# Local AI (Ollama) powers the report narrative + identity assessment. Start it if it is
# installed but not already serving; leave a running instance (it may be a system service)
# untouched. Best-effort — Weft works without it (the AI sections just fall back).
OLLAMA_MODEL="${WEFT_OLLAMA_MODEL:-llama3.2:3b}"
ensure_ollama() {
  command -v ollama >/dev/null 2>&1 || { echo "  (Ollama not installed — AI narrative disabled; recon still runs)"; return; }
  if ! port_open 11434; then
    echo "→ starting Ollama…"
    setsid ollama serve >"$HOME/.weft-ollama.log" 2>&1 </dev/null &
    for _ in $(seq 1 30); do port_open 11434 && break; sleep 1; done
  fi
  if port_open 11434 && ! ollama list 2>/dev/null | grep -q "${OLLAMA_MODEL%%:*}"; then
    echo "→ pulling AI model ${OLLAMA_MODEL} (first run only)…"
    ollama pull "$OLLAMA_MODEL" >/dev/null 2>&1 &
  fi
  port_open 11434 && echo "→ Ollama ready (model ${OLLAMA_MODEL})" || echo "  (Ollama did not start; AI sections will fall back)"
}

if [ "${1:-}" = "--stop" ]; then
  pids=$(ss -ltnp 2>/dev/null | awk -v p=":${PORT} " '$0 ~ p' | grep -o "pid=[0-9]*" | cut -d= -f2 | sort -u)
  [ -n "$pids" ] && kill $pids 2>/dev/null && echo "stopped UI ($pids)" || echo "UI not running on ${PORT}"
  have_docker && stop_stack || true
  exit 0
fi

# first run: create the venv + install deps
if [ ! -x .venv/bin/streamlit ]; then
  echo "→ first run: setting up weft (venv + deps)…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -e . || ./.venv/bin/pip install --quiet -r requirements.txt
fi

# ---- bring up the self-hosted stack + local AI ----
if have_docker; then
  start_stack
else
  echo "⚠ Docker not available — starting the UI only. Install Docker for Neo4j/SearXNG/Tor-backed modules."
fi
ensure_ollama

# ---- start the UI ----
if ! port_open "${PORT}"; then
  echo "→ starting weft UI on ${URL}"
  PYTHONPATH=src setsid ./.venv/bin/streamlit run src/weft/ui/app.py \
      --server.port "${PORT}" --server.address 127.0.0.1 \
      --server.headless true --browser.gatherUsageStats false \
      >"$LOG" 2>&1 </dev/null &
  for _ in $(seq 1 40); do port_open "${PORT}" && break; sleep 0.5; done
else
  echo "→ weft UI already running on ${URL}"
fi

# open in a Chromium app window — a frameless standalone window, so Weft feels like a desktop
# app rather than a browser tab (falls back to a normal browser if no Chromium is present).
open_app_window() {
  local url="$1" br=""
  for b in chromium chromium-browser google-chrome google-chrome-stable brave-browser; do
    command -v "$b" >/dev/null 2>&1 && { br="$b"; break; }
  done
  if [ -n "$br" ]; then
    mkdir -p "$HOME/.weft/browser-profile"
    setsid "$br" --app="$url" --user-data-dir="$HOME/.weft/browser-profile" \
      --class=Weft --name=Weft --no-first-run --no-default-browser-check \
      --window-size=1500,950 >/dev/null 2>&1 </dev/null &
  else
    ( xdg-open "$url" || sensible-browser "$url" || firefox "$url" ) >/dev/null 2>&1 &
  fi
}
open_app_window "$URL"
echo "→ opened ${URL}   UI log: ${LOG}"
echo "   Close this window any time; Weft keeps running. Stop everything with:  $(readlink -f "$0") --stop"
tail -n +1 -f "$LOG" 2>/dev/null || true

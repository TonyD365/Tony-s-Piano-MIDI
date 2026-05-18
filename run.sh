#!/usr/bin/env bash
# Starts midi_bridge.py and a cloudflared quick tunnel, then prints/copies the
# resulting https://*.trycloudflare.com URL.
#
# Usage:  bash run.sh
# Stop:   Ctrl+C in this terminal (both processes will be killed)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${HERE}/.venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Python venv not found at ${VENV_PY}"
  echo "Run:  python3 -m venv ${HERE}/.venv && ${HERE}/.venv/bin/pip install -r ${HERE}/requirements.txt"
  exit 1
fi

if ! command -v cloudflared >/dev/null; then
  echo "cloudflared not installed. macOS:  brew install cloudflared"
  exit 1
fi

PIDS=()
trap 'echo; echo "[run] stopping..."; for p in "${PIDS[@]}"; do kill "${p}" 2>/dev/null || true; done; wait' INT TERM EXIT

# 1. Start the Python MIDI bridge.
echo "[run] starting midi_bridge.py..."
"${VENV_PY}" "${HERE}/midi_bridge.py" &
PIDS+=("$!")

# Wait briefly for the HTTP server to come up.
for _ in {1..20}; do
  if curl -s --max-time 1 http://127.0.0.1:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done
if ! curl -s --max-time 1 http://127.0.0.1:8080/health >/dev/null; then
  echo "[run] WARNING: localhost:8080 not responding yet; continuing anyway"
fi

# 2. Start cloudflared quick tunnel. It prints the URL on stderr.
echo "[run] starting cloudflared quick tunnel..."
TUNNEL_LOG="$(mktemp)"
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080 >"${TUNNEL_LOG}" 2>&1 &
PIDS+=("$!")

# Watch the log for the trycloudflare URL.
URL=""
for _ in {1..60}; do
  if URL="$(grep -Eo 'https://[A-Za-z0-9.-]+\.trycloudflare\.com' "${TUNNEL_LOG}" | head -1)"; then
    if [[ -n "${URL}" ]]; then
      break
    fi
  fi
  sleep 0.5
done

if [[ -z "${URL}" ]]; then
  echo "[run] FAILED to detect tunnel URL. cloudflared log so far:"
  cat "${TUNNEL_LOG}"
  exit 1
fi

echo
echo "================================================================"
echo "  Tunnel URL:  ${URL}"
echo "  Health:      ${URL}/health"
echo
echo "  In Roblox chat (as configured admin) run:"
echo "      /pianourl ${URL}"
echo "================================================================"
echo

# Copy to clipboard if available.
if command -v pbcopy >/dev/null; then
  printf '%s' "${URL}" | pbcopy
  echo "[run] copied to clipboard (paste with Cmd+V)"
fi

# Tail the tunnel log so the user can see ongoing requests.
tail -f "${TUNNEL_LOG}"
